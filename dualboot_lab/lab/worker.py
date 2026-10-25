"""Isolated serial worker. Parent enforces wall-clock timeout and single ownership.

Run only on a test board. Opening ROM mode interrupts the running firmware.
Only boot-selection sectors can be written; provisioning is deliberately separate.
"""

import argparse
import asyncio
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import time
import uuid
import zlib
from . import diagnostics
from .diagnostics import phase

from .layout import (EXPECTED, FLASH_SIZE, NETWORKS, SECTOR, TABLE_OFFSET,
                     LabError, digest, plan_selection, selected_slot, validate_table, verify_slot_projects)


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


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
        if self.esp is not None:
            if len(_) > 1 and _[1] is not None:
                _[1].lab_phase = diagnostics.LAST_PHASE
            phase("reset")
            try:
                self.esp.hard_reset()
            finally:
                self.esp._port.close()

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
        selection = self.esp.read_flash(0x1C000, 2 * SECTOR)
        result.update(layout_supported=True, selected_slot=selected_slot(selection),
                      app_md5={name: self.esp.flash_md5sum(address, size)
                               for name, kind, _, address, size in EXPECTED if kind == 0})
        return result

    def select(self, network, registry, data):
        if self.board_confirmed is not True or self.allow_boot_selection_write is not True:
            raise LabError("Explicit board confirmation and boot-selection write permission are required")
        if self.psram_cap != 2:
            raise LabError("Boot-selection write requires observed embedded PSRAM cap 2 (2MB)")
        current = self.inspect()
        require_same_device(current, registry)
        verify_slot_projects(self.esp.read_flash)
        previous = self.esp.read_flash(0x1C000, 2 * SECTOR)
        plan = plan_selection(previous, network)
        if plan is None:
            return False
        sector, content = plan
        # Persist the old boot state BEFORE writing. This contains no app/profile data.
        save_json(data / "last-selection.json", {"mac": self.mac, "otadata_hex": previous.hex(),
                  "target": network, "time": time.time(), "status": "pending"})
        offset = 0x1C000 + sector * SECTOR
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
        after = self.esp.read_flash(0x1C000, 2 * SECTOR)
        expected = bytearray(previous)
        expected[sector * SECTOR:(sector + 1) * SECTOR] = content
        if after != bytes(expected) or selected_slot(after) != NETWORKS[network]:
            raise LabError("Boot-selection readback mismatch; stop and inspect recovery state")
        return True


def require_same_device(current, registry):
    for key in ("mac", "flash_size", "table_sha256", "app_md5"):
        if current.get(key) != registry.get(key):
            raise LabError(f"Device/layout/build changed ({key}); keep old backup and re-enrol deliberately")


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
        return {"network": "meshcore", "identity_sha256": digest(bytes.fromhex(public)),
                "settings_sha256": digest(json.dumps(stable, sort_keys=True).encode()),
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
    for key in ("network", "identity_sha256", "settings_sha256"):
        if observed.get(key) != baseline.get(key):
            raise LabError(f"Profile changed after reboot/switch ({key}); stop test")


def load_registry(data):
    path = data / "registry.json"
    if not path.exists():
        raise LabError("Enrol and back up the prepared dualboot board first")
    return json.loads(path.read_text())


def mark_selection(data, status):
    path = data / "last-selection.json"
    state = json.loads(path.read_text())
    required = "pending" if status == "written" else "written"
    if state.get("status") != required or status not in ("written", "verified"):
        raise LabError("Invalid boot-selection journal transition")
    save_json(path, {**state, "status": status, "updated_at": time.time()})


def snapshot(radio, data, registry):
    """Read flash into a new recovery point; retain the old one on failure."""
    phase("snapshot")
    image = radio.esp.read_flash(0, FLASH_SIZE)
    if len(image) != FLASH_SIZE:
        raise LabError("Full flash backup is incomplete")
    validate_table(image[TABLE_OFFSET:TABLE_OFFSET + SECTOR])
    path = data / ("flash-" + uuid.uuid4().hex + ".bin")
    with path.open("xb") as stream:
        os.chmod(path, 0o600)
        stream.write(image)
        stream.flush()
        os.fsync(stream.fileno())
    if digest(path.read_bytes()) != digest(image):
        raise LabError("Backup readback failed")
    updated = {**registry, "backup": path.name, "backup_sha256": digest(image),
               "snapshot_at": time.time(), "snapshot_profiles": sorted(registry.get("profiles", {}))}
    save_json(data / "registry.json", updated)
    return updated


def run(action, configured, data, network=None, *, board_confirmed=False, allow_boot_selection_write=False):
    if action != "inspect" and board_confirmed is not True:
        raise LabError("Explicit board confirmation is required")
    if action == "switch" and allow_boot_selection_write is not True:
        raise LabError("Explicit boot-selection write permission is required")
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    registry = load_registry(data) if action in ("baseline", "switch", "resnapshot") else None
    usb = resolve_port(configured, registry)
    if action == "resnapshot":
        if set(registry.get("profiles", {})) != set(NETWORKS):
            raise LabError("Both profile baselines are required before resnapshot")
        with Radio(usb["device"]) as radio:
            require_same_device(radio.inspect(), registry)
            updated = snapshot(radio, data, registry)
        return {"status": "snapshot_saved", "snapshot_at": updated["snapshot_at"],
                "snapshot_profiles": updated["snapshot_profiles"]}
    if action in ("inspect", "enrol"):
        with Radio(usb["device"]) as radio:
            info = radio.inspect(strict=action == "enrol")
            if action == "inspect":
                return info
            if (data / "registry.json").exists():
                raise LabError("Already enrolled. Archive the lab data before enrolling a different setup")
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
    active = next((n for n, slot in NETWORKS.items() if slot == current["selected_slot"]), None)
    if active is None:
        raise LabError("Current boot selection is unconfirmed")
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
            save_json(data / "registry.json", registry)
        return {"status": "baseline_verified", **before}
    if active not in registry["profiles"]:
        raise LabError("Capture the current firmware baseline before the first switch")
    compare_profile(before, registry["profiles"][active])
    usb = resolve_port(configured, registry)
    with Radio(usb["device"], board_confirmed=board_confirmed,
               allow_boot_selection_write=allow_boot_selection_write) as radio:
        changed = radio.select(network, registry, data)
    # Bound the verification phase in the parent process too. No automatic
    # rollback/reflash/reboot retries if target does not answer.
    time.sleep(5)
    phase("probe_after_1")
    observed = probe(network, configured, registry)
    first_observation = network not in registry["profiles"]
    if not first_observation:
        compare_profile(observed, registry["profiles"][network])
    time.sleep(5)
    phase("probe_after_2")
    repeated = probe(network, configured, registry)
    compare_profile(repeated, observed)
    if first_observation:
        registry["profiles"][network] = observed
        save_json(data / "registry.json", registry)
    if changed:
        mark_selection(data, "verified")
    return {"status": "first_boot_baseline" if first_observation else
            ("switch_verified" if changed else "already_selected_verified"),
            "from": active, "to": network, "selection_written": changed,
            "runtime_checks": 2, "profile_verified": not first_observation, **repeated}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("inspect", "enrol", "baseline", "switch", "resnapshot", "ports"))
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
    # Third-party debug output may contain protocol data. Discard it; publish
    # only the explicitly selected, non-secret evidence fields above.
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = ports() if args.action == "ports" else run(args.action, args.device, Path(args.data), args.network,
                    board_confirmed=args.board_confirmed, allow_boot_selection_write=args.allow_boot_selection_write)
        emit({"type": "result", "ok": True, "result": result})
    except Exception as exc:
        diagnostics.log_exception(Path(args.data), exc)
        message = str(exc) if isinstance(exc, LabError) else f"{type(exc).__name__}: USB/protocol operation failed; inspect device state"
        emit({"type": "result", "ok": False, "error": message,
              "error_phase": getattr(exc, "lab_phase", diagnostics.LAST_PHASE)})
        sys.exit(1)


if __name__ == "__main__":
    main()
