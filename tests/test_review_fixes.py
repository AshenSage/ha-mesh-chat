"""Review regressions. All flash, USB and protocol operations are fakes."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from lab.layout import LabError, NETWORKS, digest
from lab import worker
from lab.server import Lab
from test_dualboot_lab import table, attested


def test_a1_snapshot_captures_both_profiles_and_retains_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "FLASH_SIZE", 0x9000)
    image = b"\xff" * 0x8000 + table()
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: image, flash_md5sum=lambda *_: __import__("hashlib").md5(image).hexdigest()))
    old = tmp_path / "old.bin"
    old.write_bytes(b"old recovery point")
    registry = {"backup": old.name, "profiles": {n: {"identity_sha256": n} for n in NETWORKS}}
    updated = worker.snapshot(radio, tmp_path, registry)
    assert updated["snapshot_profiles"] == sorted(NETWORKS)
    assert (tmp_path / updated["backup"]).read_bytes() == image
    assert old.read_bytes() == b"old recovery point"


def test_a1_incomplete_snapshot_does_not_replace_registry(tmp_path, monkeypatch):
    worker.save_json(tmp_path / "registry.json", {"backup": "old.bin"})
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: b"short"))
    with pytest.raises(LabError, match="incomplete"):
        worker.snapshot(radio, tmp_path, {})
    assert json.loads((tmp_path / "registry.json").read_text()) == {"backup": "old.bin"}


def test_a1_resnapshot_requires_both_baselines(tmp_path, monkeypatch):
    worker.save_json(tmp_path / "registry.json", {"profiles": {"meshcore": {}}})
    monkeypatch.setattr(worker, "resolve_port", lambda *_: {"device": "fake"})
    with pytest.raises(LabError, match="Both profile"):
        worker.run("resnapshot", "fake", tmp_path, board_confirmed=True)


def test_a1_cycle_stops_before_switch_when_resnapshot_fails(tmp_path):
    async def scenario():
        lab = Lab(tmp_path)
        calls = []
        async def fake(action, *_):
            calls.append(action)
            raise LabError("snapshot read failed")
        lab.worker = fake
        run = {"action": "cycle", "target": "meshcore", "cycles": 1, "steps": []}
        await lab.execute(run, {})
        assert run["status"] == "failed"
        assert calls == ["resnapshot"]
    asyncio.run(scenario())


@pytest.mark.parametrize("swapped,generic", [(True, False)])
def test_a2_conflicting_slot_projects_prevent_write(tmp_path, swapped, generic):
    from test_dualboot_lab import Stub
    radio = worker.Radio("fake", board_confirmed=True, allow_boot_selection_write=True)
    radio.mac = "00:11"
    radio.psram_cap = 2
    stub = Stub()
    original_read = stub.read_flash
    def read(offset, size):
        if size == 288:
            if generic:
                raw = bytearray(original_read(offset, size))
                raw[80:112] = b"arduino-lib-builder".ljust(32, b"\0")
                return bytes(raw)
            offset = 0x680000 if offset == 0x220000 else 0x220000
        return original_read(offset, size)
    stub.read_flash = read
    radio.esp = stub
    record = attested({"mac": radio.mac})
    radio.inspect = lambda: record
    with pytest.raises(LabError, match="project does not identify"):
        radio.select("meshtastic", record, tmp_path)
    assert stub.writes == []


@pytest.mark.parametrize("cap", [0, 1, 2, 3])
def test_a3_read_only_cap_observation_and_write_gate(cap, tmp_path, monkeypatch):
    import esptool
    closed = []
    chip = SimpleNamespace(CHIP_NAME="ESP32-S3", get_secure_boot_enabled=lambda: False,
            get_flash_encryption_enabled=lambda: False, read_mac=lambda: (0, 1, 2, 3, 4, 5),
            get_psram_cap=lambda: cap, get_chip_features=lambda: [f"test cap {cap}"],
            flash_id=lambda: 0x180000, hard_reset=lambda: closed.append("reset"),
            _port=SimpleNamespace(close=lambda: closed.append("close")))
    chip.run_stub = lambda: chip
    monkeypatch.setattr(esptool, "detect_chip", lambda *_, **__: chip)
    with worker.Radio("fake", board_confirmed=True, allow_boot_selection_write=True) as radio:
        assert radio.psram_cap == cap
        if cap != 2:
            with pytest.raises(LabError, match="PSRAM cap 2"):
                radio.select("meshcore", {}, tmp_path)
    assert closed == ["reset", "close"]


def test_a4_allowlist_and_readback_hashes(tmp_path, monkeypatch):
    import verify_reference_bundle as checker
    path = tmp_path / "prebuilt/bootloader.bin"
    path.parent.mkdir()
    path.write_bytes(b"source bootloader")
    manifest = {"commit": "pinned", "files": {"prebuilt/bootloader.bin": {
        "size": path.stat().st_size, "sha256": checker.sha(path.read_bytes())}}}
    assert not checker.verify(tmp_path, manifest)["bootloader_readback_verified"]
    monkeypatch.setattr(checker, "bootloader_after_header_options", lambda _: b"header-adjusted")
    readback = tmp_path / "readback.bin"
    readback.write_bytes(b"header-adjusted")
    report = checker.verify(tmp_path, manifest, readback)
    assert report["bootloader_source_sha256"] != report["bootloader_readback_sha256"]
    assert not report["hardware_validated"]
    readback.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="readback differs"):
        checker.verify(tmp_path, manifest, readback)
    path.write_bytes(b"wrong source")
    with pytest.raises(ValueError, match="not allowlisted"):
        checker.verify(tmp_path, manifest)


def test_b2_phase_journal_and_private_sanitized_debug(tmp_path, monkeypatch):
    from lab import diagnostics
    from test_dualboot_lab import Stub
    events = []
    monkeypatch.setattr(diagnostics, "SINK", events.append)
    radio = worker.Radio("fake", board_confirmed=True, allow_boot_selection_write=True)
    radio.mac, radio.psram_cap, radio.esp = "00:11", 2, Stub()
    record = attested({"mac": radio.mac})
    radio.inspect = lambda: record
    assert radio.select("meshtastic", record, tmp_path)
    path = tmp_path / "last-selection.json"
    assert json.loads(path.read_text())["status"] == "written"
    worker.mark_selection(tmp_path, "verified")
    assert json.loads(path.read_text())["status"] == "verified"
    assert [x["phase"] for x in events] == ["write", "readback"]
    diagnostics.log_exception(tmp_path, RuntimeError("Failed to connect secret-payload-123 key=private"))
    log = (tmp_path / "debug.jsonl").read_text()
    assert "RuntimeError" in log and "Failed to connect" in log
    assert "secret" not in log and "private" not in log
    assert (tmp_path / "debug.jsonl").stat().st_mode & 0o777 == 0o600


def test_b2_parent_retains_last_phase_on_error(tmp_path, monkeypatch):
    import lab.server as server
    async def scenario():
        stream = asyncio.StreamReader()
        stream.feed_data(b'{"type":"phase","phase":"write"}\n')
        stream.feed_data(b'{"type":"result","ok":false,"error":"failed","error_phase":"write"}\n')
        stream.feed_eof()
        class Process:
            stdout, returncode = stream, None
            async def wait(self):
                self.returncode = 1
                return 1
        async def create(*_, **__):
            return Process()
        monkeypatch.setattr(server.asyncio, "create_subprocess_exec", create)
        lab = Lab(tmp_path)
        run = {"status": "running"}
        lab.state["runs"].append(run)
        lab.active_run = run
        with pytest.raises(LabError, match="failed"):
            await lab.worker("switch", {"device": "fake"}, "meshcore")
        assert run["last_phase"] == run["error_phase"] == "write"
        saved = json.loads((tmp_path / "report.json").read_text())["runs"][0]
        assert saved["last_phase"] == "write"
    asyncio.run(scenario())


@pytest.mark.parametrize("board,allowed", [(False, False), (True, False), (False, True)])
def test_b6_flags_are_required_in_worker_and_writer(board, allowed, tmp_path, monkeypatch):
    from test_dualboot_lab import Stub
    def forbidden(*_, **__):
        pytest.fail("device resolution must not run before CLI gates")
    monkeypatch.setattr(worker, "resolve_port", forbidden)
    with pytest.raises(LabError, match="Explicit"):
        worker.run("switch", "fake", tmp_path, "meshcore", board_confirmed=board,
                   allow_boot_selection_write=allowed)
    radio = worker.Radio("fake", board_confirmed=board, allow_boot_selection_write=allowed)
    radio.esp, radio.psram_cap = Stub(), 2
    with pytest.raises(LabError, match="Explicit"):
        radio.select("meshcore", {}, tmp_path)
    assert radio.esp.writes == []


def test_b3_sigterm_unwinds_radio_context_and_preserves_failure_phase(monkeypatch):
    from lab import diagnostics
    handlers, cleanup = {}, []
    monkeypatch.setattr(worker.signal, "signal", lambda n, fn: handlers.update({n: fn}))
    worker.install_signal_handlers()
    class OpenRadio(worker.Radio):
        def __enter__(self):
            self.esp = SimpleNamespace(hard_reset=lambda: cleanup.append("reset"),
                                      _port=SimpleNamespace(close=lambda: cleanup.append("close")))
            return self
    with pytest.raises(worker.WorkerTerminated) as raised:
        with OpenRadio("fake"):
            diagnostics.phase("write")
            handlers[worker.signal.SIGTERM](None, None)
    assert raised.value.lab_phase == "write"
    assert cleanup == ["reset", "close"]
    handlers[worker.signal.SIGTERM](None, None)  # second TERM does not interrupt cleanup


@pytest.mark.parametrize("stuck", [False, True])
def test_b3_parent_terminates_before_kill_and_collects_cleanup_phase(tmp_path, monkeypatch, stuck):
    import lab.server as server
    monkeypatch.setattr(server, "TERMINATION_GRACE", 0.01)
    async def scenario():
        calls = []
        class Process:
            returncode = None
            def terminate(self):
                calls.append("terminate")
            def kill(self):
                calls.append("kill")
            async def communicate(self):
                if stuck:
                    await asyncio.Future()
                self.returncode = -15
                return b'{"type":"phase","phase":"reset"}\n', None
            async def wait(self):
                self.returncode = -9
        lab = Lab(tmp_path)
        lab.active_run = {"last_phase": "write"}
        await lab.stop_worker(Process(), "switch")
        assert calls == (["terminate", "kill"] if stuck else ["terminate"])
        assert lab.active_run.get("forced_kill", False) == stuck
        if not stuck:
            assert lab.active_run["last_phase"] == "reset"
    asyncio.run(scenario())


def test_b3_phase_timeout_preserves_cause_and_requests_cleanup(tmp_path, monkeypatch):
    import lab.server as server
    monkeypatch.setitem(server.PHASE_TIMEOUTS, "write", 0.01)
    async def scenario():
        stream = asyncio.StreamReader()
        stream.feed_data(b'{"type":"phase","phase":"write"}\n')
        class Process:
            stdout, returncode = stream, None
            def terminate(self):
                pass
            async def communicate(self):
                self.returncode = -15
                return b'{"type":"phase","phase":"reset"}\n', None
        async def create(*_, **__):
            return Process()
        monkeypatch.setattr(server.asyncio, "create_subprocess_exec", create)
        lab = Lab(tmp_path)
        lab.active_run = {"status": "running"}
        with pytest.raises(LabError, match="phase timed out"):
            await lab.worker("switch", {"device": "fake"}, "meshcore")
        assert lab.active_run["error_phase"] == "write"
        assert lab.active_run["last_phase"] == "reset"
        assert lab.active_run["termination_requested"]
    asyncio.run(scenario())


def test_b4_candidate_reboot_apis_exist_without_executing_them():
    import inspect
    from meshcore.commands.device import DeviceCommands
    from meshtastic.node import Node
    assert inspect.iscoroutinefunction(DeviceCommands.reboot)
    inspect.signature(Node.reboot).bind(object(), secs=10)


def test_b7_channel_loss_or_psk_change_changes_fingerprint_without_exposing_key(monkeypatch):
    from meshtastic.protobuf import config_pb2
    import meshtastic.serial_interface
    import base64
    channels = [SimpleNamespace(index=0, role=1, settings=SimpleNamespace(name="lab", psk=b"private-channel-key"))]
    interface = SimpleNamespace(myInfo=SimpleNamespace(my_node_num=1),
        metadata=SimpleNamespace(firmware_version="fake"),
        getMyNodeInfo=lambda: {"user": {"id": "!00000001", "publicKey": base64.b64encode(b"k"*32).decode()}},
        localNode=SimpleNamespace(channels=channels, localConfig=SimpleNamespace(lora=config_pb2.Config.LoRaConfig())),
        close=lambda: None)
    monkeypatch.setattr(meshtastic.serial_interface, "SerialInterface", lambda **_: interface)
    first = worker.probe_meshtastic("fake")
    assert "private-channel-key" not in json.dumps(first)
    channels[0].settings.psk = b"changed"
    second = worker.probe_meshtastic("fake")
    with pytest.raises(LabError, match="Profile changed"):
        worker.compare_profile(first, second)
    channels.clear()
    with pytest.raises(LabError, match="channel configuration is incomplete"):
        worker.probe_meshtastic("fake")


def test_b7_meshcore_contacts_and_channel_keys_are_checked(monkeypatch):
    from meshcore import MeshCore, EventType
    state = {"secret": b"private-key-1234", "contacts": {"peer": {"public_key": "ab" * 32, "adv_name": "peer"}}}
    async def start():
        return SimpleNamespace(type=EventType.SELF_INFO, payload={"public_key": "cd" * 32})
    async def query():
        return SimpleNamespace(type=EventType.DEVICE_INFO, payload={"max_channels": 1})
    async def channel(index):
        return SimpleNamespace(type=EventType.CHANNEL_INFO, payload={"channel_idx": index,
            "channel_name": "lab", "channel_secret": state["secret"]})
    async def contacts(*, timeout):
        assert timeout == worker.CONTACTS_TIMEOUT
        return None if state.get("timeout") else SimpleNamespace(type=EventType.CONTACTS, payload=state["contacts"])
    async def close():
        pass
    async def connect(*_, **__):
        return SimpleNamespace(commands=SimpleNamespace(send_appstart=start, send_device_query=query,
            get_channel=channel, get_contacts=contacts), disconnect=close)
    monkeypatch.setattr(MeshCore, "create_serial", connect)
    first = asyncio.run(worker.probe_meshcore("fake"))
    assert "private-key-1234" not in json.dumps(first)
    state["contacts"] = {}
    second = asyncio.run(worker.probe_meshcore("fake"))
    with pytest.raises(LabError, match="contacts_set"):
        worker.compare_profile(second, first)
    state["secret"] = b"different-secret"
    third = asyncio.run(worker.probe_meshcore("fake"))
    with pytest.raises(LabError, match="channels_sha256"):
        worker.compare_profile(third, second)
    state["timeout"] = True
    with pytest.raises(LabError, match="Incomplete MeshCore contact read"):
        asyncio.run(worker.probe_meshcore("fake"))


def test_c3_fixed_crc_reference_zero_refusal_and_no_rollback_state():
    import struct
    from lab.layout import boot_entries, plan_selection, SECTOR
    from test_dualboot_lab import otadata, apply
    golden = bytearray(b"\xff" * (2 * SECTOR))
    golden[:4] = b"\x01\x00\x00\x00"
    golden[28:32] = b"\x9a\x98\x43\x47"  # ESP-IDF seq 1 CRC 0x4743989A, independent literal
    assert boot_entries(bytes(golden))[0].seq == 1
    with pytest.raises(LabError, match="sequence zero"):
        boot_entries(otadata(first=0))
    sector, content = plan_selection(bytes(golden), "meshtastic")
    assert struct.unpack_from("<I", content, 24)[0] == 0xFFFFFFFF
    assert len(boot_entries(apply(bytes(golden), (sector, content)))) == 2


@pytest.mark.parametrize("peer,expected", [("172.30.32.2", 200), ("127.0.0.1", 403)])
def test_c4_ingress_proxy_positive_and_forwarded_header_cannot_spoof_peer(peer, expected, monkeypatch):
    from aiohttp.test_utils import make_mocked_request
    from aiohttp import web
    import lab.server as server
    monkeypatch.setattr(server, "LOCAL", False)
    transport = SimpleNamespace(get_extra_info=lambda name, default=None: (peer, 1234) if name == "peername" else default)
    request = make_mocked_request("GET", "/", headers={"X-Forwarded-For": "172.30.32.2"}, transport=transport)
    async def handler(_):
        return web.Response(text="allowed")
    async def scenario():
        if expected == 200:
            assert (await server.ingress_only(request, handler)).status == 200
        else:
            with pytest.raises(web.HTTPForbidden):
                await server.ingress_only(request, handler)
    asyncio.run(scenario())


@pytest.mark.parametrize("usb", [False, True])
def test_c4_pinned_s3_reset_derives_usb_mode_internally(usb, monkeypatch):
    from esptool.targets.esp32s3 import ESP32S3ROM
    from esptool.loader import ESPLoader
    observed = []
    monkeypatch.setattr(ESPLoader, "hard_reset", lambda self, uses_usb=False: observed.append(uses_usb))
    esp = object.__new__(ESP32S3ROM)
    esp.write_reg = lambda *args: None
    esp.uses_usb_otg = lambda: usb
    esp.read_reg = lambda addr: esp.GPIO_STRAP_SPI_BOOT_MASK if addr == esp.GPIO_STRAP_REG else 0
    esp.hard_reset()  # no constructor or serial transport
    assert observed == [usb]


def test_c5_corrupt_report_is_quarantined_and_rotation_is_bounded(tmp_path, monkeypatch):
    import lab.server as server
    (tmp_path / "report.json").write_text("{broken")
    lab = Lab(tmp_path)
    assert lab.state["report_recovery"]["status"] == "quarantined"
    assert list(tmp_path.glob("report-corrupt-*.json"))[0].read_text() == "{broken"
    monkeypatch.setattr(server, "MAX_RUNS", 2)
    monkeypatch.setattr(server, "MAX_REPORT_ARCHIVES", 2)
    for index in range(8):
        lab.state["runs"].append({"status": "completed", "id": index})
        lab.persist()
    assert [run["id"] for run in lab.state["runs"]] == [6, 7]
    assert len(list(tmp_path.glob("report-archive-*.json"))) == 2


def test_c5_private_file_mode_and_failed_backup_md5(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "FLASH_SIZE", 0x9000)
    path = tmp_path / "private.bin"
    with worker.private_open(path, binary=True) as stream:
        assert path.stat().st_mode & 0o777 == 0o600  # already private before any write
        stream.write(b"test")
    with pytest.raises(FileExistsError):
        worker.private_open(path)
    image = b"\xff" * 0x8000 + table()
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: image, flash_md5sum=lambda *_: "bad"))
    with pytest.raises(LabError, match="differs from device flash MD5"):
        worker.snapshot(radio, tmp_path, {})
    assert not list(tmp_path.glob("flash-*.bin"))


def test_c5_recovery_prepares_only_offline_single_sector_candidate(tmp_path):
    from prepare_selection_recovery import prepare
    from test_dualboot_lab import otadata
    from lab.layout import OTA_OFFSET, SECTOR
    journal = {"mac": "trusted", "status": "written", "otadata_hex": otadata(1).hex()}
    result = prepare(journal, otadata(1, 2), "trusted", tmp_path / "candidate")
    assert result["status"] == "manual_candidate_not_executed"
    assert result["offset"] in (OTA_OFFSET, OTA_OFFSET + SECTOR)
    assert result["size"] == SECTOR and result["hardware_validated"] is False
    assert (tmp_path / "candidate/recovery-sector.bin").stat().st_size == SECTOR
    with pytest.raises(LabError, match="MAC/status"):
        prepare(journal, otadata(1, 2), "other-device", tmp_path / "wrong")


def test_c5_unlinked_snapshot_blocks_enrolment(tmp_path, monkeypatch):
    (tmp_path / "flash-orphan.bin").write_bytes(b"retain for investigation")
    class FakeRadio:
        def __init__(self, *_):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def inspect(self, **_):
            return {"selected_slot": 0}
    monkeypatch.setattr(worker, "Radio", FakeRadio)
    monkeypatch.setattr(worker, "resolve_port", lambda *_: {"device": "fake"})
    monkeypatch.setattr(worker, "snapshot", lambda *_: pytest.fail("must not create a second enrolment snapshot"))
    with pytest.raises(LabError, match="Unlinked flash snapshots"):
        worker.run("enrol", "fake", tmp_path, board_confirmed=True)
    assert (tmp_path / "flash-orphan.bin").read_bytes() == b"retain for investigation"


def test_r2_1_generic_projects_require_valid_runtime_attestations(tmp_path):
    from test_dualboot_lab import Stub
    radio = worker.Radio("fake", board_confirmed=True, allow_boot_selection_write=True)
    radio.mac, radio.psram_cap, radio.esp = "00:11", 2, Stub()
    original = radio.esp.read_flash
    def read(offset, size):
        raw = original(offset, size)
        if size == 288:
            raw = bytearray(raw)
            raw[80:112] = b"arduino-lib-builder".ljust(32, b"\0")
            raw = bytes(raw)
        return raw
    radio.esp.read_flash = read
    record = attested({"mac": radio.mac})
    radio.inspect = lambda: record
    assert radio.select("meshtastic", record, tmp_path)
    assert radio.esp.writes == [(0x1D000, 4096)]



def test_r2_3_snapshot_chain_retention_never_automatically_deletes(tmp_path, monkeypatch):
    import hashlib
    monkeypatch.setattr(worker, "FLASH_SIZE", 0x9000)
    image = b"\xff" * 0x8000 + table()
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: image,
                            flash_md5sum=lambda *_: hashlib.md5(image).hexdigest()))
    registry = {"profiles": {}}
    names = []
    for _ in range(5):
        previous = registry.get("backup")
        registry = worker.snapshot(radio, tmp_path, registry)
        names.append(registry["backup"])
        if previous:
            assert registry["previous_backups"][0]["backup"] == previous
    assert all((tmp_path / name).exists() for name in names)
    assert set(worker.retention_candidates(registry)) == set(names[1:3])
    assert registry["enrol_backup"]["backup"] == names[0]
    with pytest.raises(LabError, match="acknowledgement"):
        worker.prune_snapshots(tmp_path, None)
    result = worker.prune_snapshots(tmp_path, "retention_reviewed")
    assert set(result["deleted"]) == set(names[1:3])
    assert all((tmp_path / name).exists() for name in (names[0], *names[-2:]))



def test_r2_7_first_sigterm_inside_reset_is_deferred_until_reset_and_close_finish(monkeypatch):
    handlers, calls = {}, []
    monkeypatch.setattr(worker.signal, "signal", lambda n, fn: handlers.update({n: fn}))
    worker.install_signal_handlers()
    def reset():
        calls.append("reset-start")
        handlers[worker.signal.SIGTERM](None, None)
        handlers[worker.signal.SIGTERM](None, None)
        calls.append("reset-finished")
    radio = worker.Radio("fake")
    radio.esp = SimpleNamespace(hard_reset=reset, _port=SimpleNamespace(close=lambda: calls.append("close")))
    try:
        with pytest.raises(worker.WorkerTerminated):
            radio.__exit__(None, None, None)
        assert calls == ["reset-start", "reset-finished", "close"]
        assert not worker.CLEANUP_ACTIVE and worker.TERMINATION_REQUESTED
    finally:
        worker.install_signal_handlers()


def test_r2_7_sigterm_during_detect_before_ownership_has_no_fake_reset_claim(monkeypatch):
    import esptool
    handlers = {}
    monkeypatch.setattr(worker.signal, "signal", lambda n, fn: handlers.update({n: fn}))
    worker.install_signal_handlers()
    def detect(*_, **__):
        handlers[worker.signal.SIGTERM](None, None)
    monkeypatch.setattr(esptool, "detect_chip", detect)
    radio = worker.Radio("fake")
    try:
        with pytest.raises(worker.WorkerTerminated):
            radio.__enter__()
        assert radio.esp is None and not worker.CLEANUP_ACTIVE
    finally:
        worker.install_signal_handlers()



def test_r2_p3_debug_rotation_is_bounded_private_and_sanitized(tmp_path, monkeypatch):
    from lab import diagnostics
    monkeypatch.setattr(diagnostics, "DEBUG_MAX_BYTES", 1)
    monkeypatch.setattr(diagnostics, "DEBUG_ARCHIVES", 2)
    for _ in range(8):
        diagnostics.log_exception(tmp_path, RuntimeError("do not record this private key"))
    files = sorted(tmp_path.glob("debug.jsonl*"))
    assert len(files) == 3
    for path in files:
        assert path.stat().st_mode & 0o777 == 0o600
        assert "private key" not in path.read_text()
        assert json.loads(path.read_text())["exception_type"] == "RuntimeError"


@pytest.mark.parametrize("changed", [False, True])
def test_r2_p3_pending_recovery_plan_never_implies_no_write(tmp_path, changed):
    from prepare_selection_recovery import prepare
    from test_dualboot_lab import otadata
    journal = {"mac": "trusted", "status": "pending", "otadata_hex": otadata(1).hex()}
    result = prepare(journal, otadata(1, 2) if changed else otadata(1), "trusted", tmp_path / "output")
    assert result["journal_status"] == "pending"
    assert "write may have begun" in result["journal_caution"]
    assert result["hardware_validated"] is False
