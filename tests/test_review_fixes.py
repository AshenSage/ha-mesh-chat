"""Review regressions. All flash, USB and protocol operations are fakes."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from lab.layout import LabError, NETWORKS, digest
from lab import worker
from lab.server import Lab
from test_dualboot_lab import table


def test_a1_snapshot_captures_both_profiles_and_retains_previous(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "FLASH_SIZE", 0x9000)
    image = b"\xff" * 0x8000 + table()
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: image))
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


@pytest.mark.parametrize("swapped,generic", [(True, False), (False, True)])
def test_a2_swapped_or_generic_slot_projects_prevent_write(tmp_path, swapped, generic):
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
    radio.inspect = lambda: {"mac": radio.mac}
    with pytest.raises(LabError, match="project does not identify"):
        radio.select("meshtastic", {"mac": radio.mac}, tmp_path)
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
    radio.inspect = lambda: {"mac": radio.mac}
    assert radio.select("meshtastic", {"mac": radio.mac}, tmp_path)
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
