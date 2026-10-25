"""Isolated serial worker. Parent enforces wall-clock timeout and single ownership.

Run only on a test board. Opening ROM mode interrupts the running firmware.
Only boot-selection sectors can be written; provisioning is deliberately separate.
"""

import argparse
import asyncio
import base64
import contextlib
import io
import hashlib
import json
import os
import signal
from pathlib import Path
import sys
import time
import uuid
import zlib
from . import diagnostics
from .diagnostics import phase

from .layout import (EXPECTED, FLASH_SIZE, NETWORKS, SECTOR, TABLE_OFFSET, OTA_OFFSET, OTA_SIZE,
                     LabError, digest, plan_selection, selected_slot, validate_table, verify_slot_projects)


class WorkerTerminated(LabError):
    pass


TERMINATION_REQUESTED = False
TERMINATION_RAISED = False
CLEANUP_ACTIVE = False


def raise_termination():
    global TERMINATION_RAISED
    if TERMINATION_REQUESTED and not TERMINATION_RAISED and not CLEANUP_ACTIVE:
        TERMINATION_RAISED = True
        exc = WorkerTerminated("Worker termination requested; cleanup attempted for any owned ROM/stub session")
        exc.lab_phase = diagnostics.LAST_PHASE
        raise exc


def install_signal_handlers():
    global TERMINATION_REQUESTED, TERMINATION_RAISED
    TERMINATION_REQUESTED = TERMINATION_RAISED = False
    def terminate(_number, _frame):
        global TERMINATION_REQUESTED
        TERMINATION_REQUESTED = True
        # A first TERM during reset/close must not interrupt either operation.
        # Repeated TERM during an existing unwind is deferred as well.
        raise_termination()
    signal.signal(signal.SIGTERM, terminate)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with private_open(temp) as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_open(path, binary=False):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    return os.fdopen(descriptor, "wb" if binary else "w")


def ports():
    from serial.tools import list_ports
    return [{"device": p.device, "serial": p.serial_number, "location": p.location,
             "description": p.description} for p in list_ports.comports()]


def resolve_port(configured, registry=None, wait=15):
    deadline = time.monotonic() + wait
    while True:
        found = ports()
        # Re-enumeration may change tty number and USB product/serial. Physical
        # USB location is a fallback only when exactly one serial interface matches.
        match = [p for p in found if os.path.realpath(p["device"]) == os.path.realpath(configured)]
        if not match and registry:
            usb = registry.get("usb", {})
            match = [p for p in found if usb.get("location") and p["location"] == usb["location"]]
        if len(match) == 1:
            return match[0]
        if len(match) > 1:
            raise LabError("Ambiguous USB interfaces; select the exact device")
        if time.monotonic() >= deadline:
            raise LabError("Configured USB device is absent; check passthrough and re-enumeration")
        time.sleep(0.5)


class Radio:
    def __init__(self, port, *, board_confirmed=False, allow_boot_selection_write=False):
        self.port = port
        self.esp = None
        self.psram_cap = None
        self.chip_features = []
        self.board_confirmed = board_confirmed
        self.allow_boot_selection_write = allow_boot_selection_write

    def __enter__(self):
        import esptool
        phase("inspect")
        try:
            self.esp = esptool.detect_chip(self.port, connect_attempts=3)
            if self.esp.CHIP_NAME != "ESP32-S3":
                raise LabError("Only ESP32-S3 is supported")
            if self.esp.get_secure_boot_enabled() or self.esp.get_flash_encryption_enabled():
                raise LabError("Secure boot/encrypted flash is unsupported")
            self.mac = ":".join(f"{x:02x}" for x in self.esp.read_mac())
            # Observe before loading the stub. Read-only diagnostics remain
            # available for unknown variants; writes require the documented cap.
            self.psram_cap = self.esp.get_psram_cap()
            self.chip_features = self.esp.get_chip_features()
            self.esp = self.esp.run_stub()
            flash_id = self.esp.flash_id()
            self.size = 1 << ((flash_id >> 16) & 0xFF)
            if self.size != FLASH_SIZE:
                raise LabError("The lab requires exactly 16 MB flash")
            return self
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise

    def __exit__(self, *_):
        global CLEANUP_ACTIVE
        previous_cleanup = CLEANUP_ACTIVE
        CLEANUP_ACTIVE = True
        try:
            if self.esp is not None:
                if len(_) > 1 and _[1] is not None:
                    _[1].lab_phase = diagnostics.LAST_PHASE
                phase("reset")
                try:
                    self.esp.hard_reset()
                finally:
                    self.esp._port.close()
        finally:
            CLEANUP_ACTIVE = previous_cleanup
        if not _ or len(_) < 2 or _[1] is None:
            raise_termination()

    def inspect(self, strict=True):
        phase("inspect")
        table = self.esp.read_flash(TABLE_OFFSET, SECTOR)
        result = {"mac": self.mac, "flash_size": self.size, "table_sha256": digest(table),
                  "psram_cap": self.psram_cap, "chip_features": self.chip_features,
                  "r2_candidate": self.psram_cap == 2, "variant_hardware_validated": False}
        try:
            validate_table(table)
        except LabError as exc:
            if strict:
                raise
            return {**result, "layout_supported": False, "reason": str(exc)}
        selection = self.esp.read_flash(OTA_OFFSET, OTA_SIZE)
        result.update(layout_supported=True, selected_slot=selected_slot(selection),
                      bootloader_md5=self.esp.flash_md5sum(0, TABLE_OFFSET),
                      selector_nvs_md5=self.esp.flash_md5sum(*next((r[3], r[4]) for r in EXPECTED if r[0] == "nvs_sel")),
                      app_md5={name: self.esp.flash_md5sum(address, size)
                               for name, kind, _, address, size in EXPECTED if kind == 0})
        return result

    def select(self, network, registry, data):
        require_closed_journal(data)
        if self.board_confirmed is not True or self.allow_boot_selection_write is not True:
            raise LabError("Explicit board confirmation and boot-selection write permission are required")
        if self.psram_cap != 2:
            raise LabError("Boot-selection write requires observed embedded PSRAM cap 2 (2MB)")
        current = self.inspect()
        require_same_device(current, registry)
        require_slot_attestations(current, registry)
        verify_slot_projects(self.esp.read_flash)
        previous = self.esp.read_flash(OTA_OFFSET, OTA_SIZE)
        plan = plan_selection(previous, network)
        if plan is None:
            return False
        sector, content = plan
        # Persist the old boot state BEFORE writing. This contains no app/profile data.
        save_json(data / "last-selection.json", {"mac": self.mac, "otadata_hex": previous.hex(),
                  "target": network, "time": time.time(), "status": "pending"})
        offset = OTA_OFFSET + sector * SECTOR
        # Compressed stub write has exact 4 KB erase/write extent, no padding
        # to the stub's potentially larger FLASH_WRITE_SIZE.
        packed = zlib.compress(content, 9)
        phase("write")
        self.esp.flash_defl_begin(len(content), len(packed), offset)
        for number, start in enumerate(range(0, len(packed), self.esp.FLASH_WRITE_SIZE)):
            self.esp.flash_defl_block(packed[start:start + self.esp.FLASH_WRITE_SIZE], number)
        self.esp.flash_defl_finish(reboot=False)
        mark_selection(data, "written")
        phase("readback")
        after = self.esp.read_flash(OTA_OFFSET, OTA_SIZE)
        expected = bytearray(previous)
        expected[sector * SECTOR:(sector + 1) * SECTOR] = content
        if after != bytes(expected) or selected_slot(after) != NETWORKS[network]:
            raise LabError("Boot-selection readback mismatch; stop and inspect recovery state")
        return True


def require_same_device(current, registry):
    for key in ("mac", "flash_size", "table_sha256", "app_md5", "bootloader_md5"):
        if current.get(key) != registry.get(key):
            raise LabError(f"Device/layout/build changed ({key}); keep old backup and re-enrol deliberately")

    if current.get("selector_nvs_md5") != registry.get("selector_nvs_md5"):
        diagnostics.warning("selector_nvs_changed_unvalidated")


def require_slot_attestations(current, registry):
    for network, slot in NETWORKS.items():
        record = registry.get("slot_attestation", {}).get(network, {})
        if (network not in registry.get("profiles", {}) or record.get("slot") != slot
                or not record.get("evidence") or not record.get("app_md5")
                or record["app_md5"] != current.get("app_md5", {}).get(f"ota_{slot}")):
            raise LabError(f"Missing or changed slot attestation ({network}); manually boot and capture both baselines")


async def probe_meshcore(port):
    from meshcore import MeshCore, EventType
    mc = await MeshCore.create_serial(port, default_timeout=4, auto_reconnect=False)
    try:
        event = await mc.commands.send_appstart()
        if event is None or event.type != EventType.SELF_INFO:
            raise LabError("No MeshCore USB SELF_INFO response; a BLE-only build is insufficient")
        info = event.payload
        public = info.get("public_key", "")
        if not isinstance(public, str) or len(public) != 64 or not any(bytes.fromhex(public)):
            raise LabError("MeshCore returned no usable public identity")
        stable = {k: info.get(k) for k in ("name", "radio_freq", "radio_bw", "radio_sf", "radio_cr", "tx_power")}
        capabilities = await mc.commands.send_device_query()
        if capabilities is None or capabilities.type != EventType.DEVICE_INFO:
            raise LabError("MeshCore channel capacity is unavailable")
        count = capabilities.payload.get("max_channels")
        if type(count) is not int or not 0 < count <= 64:
            raise LabError("MeshCore channel capacity is unsupported")
        channels = []
        for index in range(count):
            channel = await mc.commands.get_channel(index)
            if channel is None or channel.type != EventType.CHANNEL_INFO or channel.payload.get("channel_idx") != index:
                raise LabError("Incomplete MeshCore channel read")
            secret = channel.payload.get("channel_secret")
            if not isinstance(secret, bytes) or len(secret) != 16:
                raise LabError("MeshCore channel key cannot be fingerprinted")
            channels.append({"index": index, "name": channel.payload.get("channel_name", ""), "psk_sha256": digest(secret)})
        contacts = await mc.commands.get_contacts()
        if contacts is None or contacts.type != EventType.CONTACTS or not isinstance(contacts.payload, dict):
            raise LabError("Incomplete MeshCore contact read")
        peers = sorted([{k: peer.get(k) for k in ("public_key", "adv_name", "type", "flags")}
                        for peer in contacts.payload.values()], key=lambda peer: str(peer["public_key"]))
        contact_set = sorted({digest(json.dumps(peer, sort_keys=True).encode()) for peer in peers})
        if len(contact_set) != len(peers):
            raise LabError("Incomplete MeshCore contacts_set (duplicates)")
        return {"network": "meshcore", "identity_sha256": digest(bytes.fromhex(public)),
                "radio_sha256": digest(json.dumps(stable, sort_keys=True).encode()),
                "channels_sha256": digest(json.dumps(channels, sort_keys=True).encode()),
                "contacts_count": len(contact_set), "contacts_set": contact_set,
                "name": info.get("name", ""), "evidence": "USB SELF_INFO"}
    finally:
        await mc.disconnect()


def probe_meshtastic(port):
    from google.protobuf.json_format import MessageToDict
    from meshtastic.serial_interface import SerialInterface
    interface = None
    try:
        # Request the node database too: getMyNodeInfo depends on our own user
        # record, which a nodeless config stream need not include.
        interface = SerialInterface(devPath=port, noNodes=False, timeout=12)
        node = interface.getMyNodeInfo() or {}
        user = node.get("user", {})
        number = interface.myInfo.my_node_num if interface.myInfo else 0
        if not number or not user.get("id") or not interface.metadata:
            raise LabError("No complete Meshtastic USB identity/metadata response")
        public = user.get("publicKey", "")
        try:
            public_bytes = base64.b64decode(public, validate=True)
        except (ValueError, TypeError) as exc:
            raise LabError("Meshtastic returned no usable public key") from exc
        if len(public_bytes) != 32 or not any(public_bytes):
            raise LabError("Meshtastic returned no usable public key; node ID alone is insufficient")
        identity = {"node": number, "id": user["id"], "publicKey": public}
        stable = {"longName": user.get("longName"), "shortName": user.get("shortName"),
                  "lora": MessageToDict(interface.localNode.localConfig.lora)}
        channels = interface.localNode.channels
        if channels is None or not channels:
            raise LabError("Meshtastic channel configuration is incomplete")
        stable["channels"] = [{"index": c.index, "name": c.settings.name, "role": c.role,
                               "psk_sha256": digest(bytes(c.settings.psk))} for c in channels]
        return {"network": "meshtastic", "identity_sha256": digest(json.dumps(identity, sort_keys=True).encode()),
                "settings_sha256": digest(json.dumps(stable, sort_keys=True).encode()),
                "name": user.get("longName", ""), "version": interface.metadata.firmware_version,
                "evidence": "USB configuration completion, node identity and metadata"}
    finally:
        if interface is not None:
            interface.close()


def probe(network, configured, registry):
    # One explicit protocol only: do not spray commands from the other protocol.
    port = resolve_port(configured, registry)["device"]
    return asyncio.run(probe_meshcore(port)) if network == "meshcore" else probe_meshtastic(port)


def compare_profile(observed, baseline):
    keys = ["network", "identity_sha256"]
    if baseline.get("network") == "meshcore":
        required = ("radio_sha256", "channels_sha256", "contacts_count", "contacts_set")
        for record in (baseline, observed):
            if any(key not in record for key in required):
                raise LabError("Baseline neu erfassen: MeshCore component fingerprints missing")
            members = record["contacts_set"]
            if (not isinstance(members, list) or any(not isinstance(x, str) for x in members)
                    or type(record["contacts_count"]) is not int
                    or record["contacts_count"] != len(set(members)) or len(members) != len(set(members))):
                raise LabError("Profile changed (contacts_set): invalid component")
        keys += ["radio_sha256", "channels_sha256"]
        if not set(baseline["contacts_set"]).issubset(observed["contacts_set"]):
            raise LabError("Profile changed (contacts_set): baseline contact missing")
    else:
        keys += ["settings_sha256"]
    for key in keys:
        if observed.get(key) != baseline.get(key):
            raise LabError(f"Profile changed after reboot/switch ({key}); stop test")


def load_registry(data):
    path = data / "registry.json"
    if not path.exists():
        raise LabError("Enrol and back up the prepared dualboot board first")
    return json.loads(path.read_text())


ACK_REASONS = ("manual_recovery_checked", "abandoned_after_inspection")


def require_closed_journal(data):
    path = data / "last-selection.json"
    if path.exists():
        try:
            state = json.loads(path.read_text())
        except (ValueError, UnicodeError) as exc:
            raise LabError("Selection journal is unreadable; preserve and inspect it") from exc
        if state.get("status") not in ("verified", "acknowledged"):
            raise LabError("Open selection journal; verify the selected runtime or explicitly acknowledge after inspection")


def acknowledge_journal(data, reason):
    if reason not in ACK_REASONS:
        raise LabError("Choose an explicit journal acknowledgement reason")
    path = data / "last-selection.json"
    if not path.exists():
        raise LabError("No selection journal to acknowledge")
    state = json.loads(path.read_text())
    if state.get("status") not in ("pending", "written"):
        raise LabError("Only pending/written journals can be acknowledged")
    archive = "selection-ack-" + uuid.uuid4().hex + ".json"
    saved = {**state, "acknowledgement_reason": reason, "acknowledged_at": time.time()}
    save_json(data / archive, saved)
    save_json(path, {**saved, "status": "acknowledged", "archive": archive})
    return {"status": "journal_acknowledged", "reason": reason, "archive": archive,
            "hardware_validated": False}


def mark_selection(data, status):
    path = data / "last-selection.json"
    state = json.loads(path.read_text())
    required = "pending" if status == "written" else "written"
    if state.get("status") != required or status not in ("written", "verified"):
        raise LabError("Invalid boot-selection journal transition")
    save_json(path, {**state, "status": status, "updated_at": time.time()})


def recovery_point(registry):
    return {key: registry[key] for key in ("backup", "backup_sha256", "backup_flash_md5", "snapshot_at", "previous_backup")
            if key in registry}


def retention_candidates(registry):
    chain, point = [], recovery_point(registry)
    while point.get("backup"):
        chain.append(point["backup"])
        point = point.get("previous_backup") or {}
    protected = set(chain[:2]) | {registry.get("enrol_backup", {}).get("backup")}
    return sorted(set(chain) - protected)


def prune_snapshots(data, reason):
    if reason != "retention_reviewed":
        raise LabError("Explicit retention_reviewed acknowledgement required")
    registry = load_registry(data)
    candidates = retention_candidates(registry)
    # Commit an audit record before removal. Unknown/orphan files are untouched.
    save_json(data / ("snapshot-prune-" + uuid.uuid4().hex + ".json"),
              {"reason": reason, "time": time.time(), "candidates": candidates})
    deleted = []
    for name in candidates:
        if Path(name).name != name or not name.startswith("flash-") or not name.endswith(".bin"):
            raise LabError("Invalid snapshot reference; nothing further removed")
        path = data / name
        if path.is_file():
            path.unlink()
            deleted.append(name)
    return {"status": "snapshot_retention_acknowledged", "deleted": deleted}


def snapshot(radio, data, registry):
    """Read flash into a new recovery point; retain the old one on failure."""
    phase("snapshot")
    image = radio.esp.read_flash(0, FLASH_SIZE)
    if len(image) != FLASH_SIZE:
        raise LabError("Full flash backup is incomplete")
    validate_table(image[TABLE_OFFSET:TABLE_OFFSET + SECTOR])
    flash_md5 = radio.esp.flash_md5sum(0, FLASH_SIZE)
    if hashlib.md5(image).hexdigest() != flash_md5:
        raise LabError("Full flash backup differs from device flash MD5")
    path = data / ("flash-" + uuid.uuid4().hex + ".bin")
    with private_open(path, binary=True) as stream:
        stream.write(image)
        stream.flush()
        os.fsync(stream.fileno())
    if digest(path.read_bytes()) != digest(image):
        raise LabError("Backup readback failed")
    updated = {**registry, "backup": path.name, "backup_sha256": digest(image),
               "backup_flash_md5": flash_md5,
               "snapshot_at": time.time(), "snapshot_profiles": sorted(registry.get("profiles", {}))}
    previous = recovery_point(registry)
    updated["previous_backup"] = previous or None
    oldest = previous
    while oldest.get("previous_backup"):
        oldest = oldest["previous_backup"]
    updated["enrol_backup"] = registry.get("enrol_backup") or oldest or recovery_point(updated)
    updated["retention_pending"] = retention_candidates(updated)
    save_json(data / "registry.json", updated)
    return updated


def run(action, configured, data, network=None, *, board_confirmed=False, allow_boot_selection_write=False, reason=None):
    if action != "inspect" and board_confirmed is not True:
        raise LabError("Explicit board confirmation is required")
    if action == "switch" and allow_boot_selection_write is not True:
        raise LabError("Explicit boot-selection write permission is required")
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if action == "prune_snapshots":
        return prune_snapshots(data, reason)
    if action == "acknowledge_journal":
        return acknowledge_journal(data, reason)
    if action == "switch":
        require_closed_journal(data)
    if action == "verify_selection":
        journal = json.loads((data / "last-selection.json").read_text())
        if journal.get("status") != "written" or journal.get("target") != network:
            raise LabError("Verification requires a written journal for the requested target")
    registry = load_registry(data) if action in ("baseline", "switch", "resnapshot", "verify_selection") else None
    usb = resolve_port(configured, registry)
    if action == "resnapshot":
        if set(registry.get("profiles", {})) != set(NETWORKS):
            raise LabError("Both profile baselines are required before resnapshot")
        with Radio(usb["device"]) as radio:
            current = radio.inspect()
            require_same_device(current, registry)
            require_slot_attestations(current, registry)
        active = next((n for n, slot in NETWORKS.items() if slot == current["selected_slot"]), None)
        if active is None:
            raise LabError("Current boot selection is unconfirmed")
        time.sleep(3)
        phase("probe_before")
        compare_profile(probe(active, configured, registry), registry["profiles"][active])
        with Radio(usb["device"]) as radio:
            confirmed = radio.inspect()
            require_same_device(confirmed, registry)
            if confirmed["selected_slot"] != current["selected_slot"]:
                raise LabError("Boot selection changed before snapshot")
            updated = snapshot(radio, data, registry)
        return {"status": "snapshot_saved", "snapshot_at": updated["snapshot_at"],
                "snapshot_profiles": updated["snapshot_profiles"], "live_profile_verified": active,
                "retention_pending": updated["retention_pending"]}
    if action in ("inspect", "enrol"):
        with Radio(usb["device"]) as radio:
            info = radio.inspect(strict=action == "enrol")
            if action == "inspect":
                return info
            if (data / "registry.json").exists():
                raise LabError("Already enrolled. Archive the lab data before enrolling a different setup")
            if any(data.glob("flash-*.bin")):
                raise LabError("Unlinked flash snapshots found; archive and investigate before enrolment")
            if info["selected_slot"] is None:
                raise LabError("Select and boot one firmware manually before enrolment")
            registry = {**info, "usb": usb,
                        "profiles": {}, "enrolled_at": time.time()}
            snapshot(radio, data, registry)
            return {**info, "backup_saved": True}
    if network not in NETWORKS:
        raise LabError("Choose meshcore or meshtastic")
    backup = data / registry["backup"]
    phase("verify_backup")
    if not backup.is_file() or digest(backup.read_bytes()) != registry["backup_sha256"]:
        raise LabError("The enrolled full-flash backup is missing or damaged")
    with Radio(usb["device"]) as radio:
        current = radio.inspect()
        require_same_device(current, registry)
        if action in ("switch", "verify_selection"):
            require_slot_attestations(current, registry)
            verify_slot_projects(radio.esp.read_flash)
    active = next((n for n, slot in NETWORKS.items() if slot == current["selected_slot"]), None)
    if active is None:
        raise LabError("Current boot selection is unconfirmed")
    if action == "verify_selection" and active != network:
        raise LabError("Journal target is not currently selected; no write attempted")
    # The runtime handshake below, not selected_slot, establishes running firmware.
    time.sleep(3)
    phase("probe_before")
    before = probe(active, configured, registry)
    if action == "baseline":
        if network != active:
            raise LabError(f"Requested baseline is {network}; selected/running firmware is {active}")
        if network in registry["profiles"]:
            compare_profile(before, registry["profiles"][network])
        else:
            registry["profiles"][network] = before
        # Bind the successful protocol response to unchanged slot bytes and OTA
        # selection on both sides of that observation. A5 remains a hardware gate.
        with Radio(usb["device"]) as radio:
            confirmed = radio.inspect()
            require_same_device(confirmed, registry)
            if confirmed["selected_slot"] != current["selected_slot"]:
                raise LabError("Boot selection changed during baseline attestation")
        registry.setdefault("slot_attestation", {})[network] = {
            "slot": NETWORKS[network], "app_md5": confirmed["app_md5"][f"ota_{NETWORKS[network]}"],
            "evidence": {"protocol": before["evidence"], "identity_sha256": before["identity_sha256"],
                         "captured_at": time.time()}}
        save_json(data / "registry.json", registry)
        return {"status": "baseline_verified", **before}
    if active not in registry["profiles"]:
        raise LabError("Capture the current firmware baseline before the first switch")
    compare_profile(before, registry["profiles"][active])
    # A second current-runtime observation must agree before entering ROM for
    # a write. Later target probes cannot retroactively prevent that write.
    phase("probe_before")
    compare_profile(probe(active, configured, registry), before)
    if action == "verify_selection":
        mark_selection(data, "verified")
        return {"status": "already_selected_verified", "from": active, "to": network,
                "selection_written": False, "runtime_checks": 2, "profile_verified": True}
    usb = resolve_port(configured, registry)
    with Radio(usb["device"], board_confirmed=board_confirmed,
               allow_boot_selection_write=allow_boot_selection_write) as radio:
        changed = radio.select(network, registry, data)
    # Bound the verification phase in the parent process too. No automatic
    # rollback/reflash/reboot retries if target does not answer.
    time.sleep(5)
    phase("probe_after_1")
    observed = probe(network, configured, registry)
    compare_profile(observed, registry["profiles"][network])
    time.sleep(5)
    phase("probe_after_2")
    repeated = probe(network, configured, registry)
    compare_profile(repeated, observed)
    if changed:
        mark_selection(data, "verified")
    return {"status": "switch_verified" if changed else "already_selected_verified",
            "from": active, "to": network, "selection_written": changed,
            "runtime_checks": 2, "profile_verified": True, **repeated}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "enrol", "baseline", "switch", "resnapshot", "acknowledge_journal", "verify_selection", "prune_snapshots", "ports"))
    parser.add_argument("--reason", choices=ACK_REASONS + ("retention_reviewed",))
    parser.add_argument("--device", default="")
    parser.add_argument("--data", default="/data")
    parser.add_argument("--network", choices=tuple(NETWORKS))
    parser.add_argument("--board-confirmed", action="store_true")
    parser.add_argument("--allow-boot-selection-write", action="store_true")
    args = parser.parse_args()
    output = sys.stdout
    def emit(value):
        output.write(json.dumps(value) + "\n")
        output.flush()
    diagnostics.SINK = emit
    install_signal_handlers()
    # Third-party debug output may contain protocol data. Discard it; publish
    # only the explicitly selected, non-secret evidence fields above.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = ports() if args.action == "ports" else run(args.action, args.device, Path(args.data), args.network,
                    board_confirmed=args.board_confirmed, allow_boot_selection_write=args.allow_boot_selection_write, reason=args.reason)
        emit({"type": "result", "ok": True, "result": result})
    except Exception as exc:
        diagnostics.log_exception(Path(args.data), exc)
        message = str(exc) if isinstance(exc, LabError) else f"{type(exc).__name__}: USB/protocol operation failed; inspect device state"
        emit({"type": "result", "ok": False, "error": message,
              "error_phase": getattr(exc, "lab_phase", diagnostics.LAST_PHASE)})
        sys.exit(1)


if __name__ == "__main__":
    main()
