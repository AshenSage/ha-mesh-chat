"""Backup failures must prevent transitions; no real USB or flash writes."""
import asyncio
import hashlib
import json
import stat
from types import SimpleNamespace

import pytest

from lab import worker
from lab.layout import FLASH_SIZE, LabError, digest
from lab.server import Lab
from test_run_orchestration import setup_run


def test_every_actual_transition_has_a_new_durable_verified_backup(setup_run):
    s = setup_run
    for target in ("meshtastic", "meshcore", "meshtastic"):
        previous = worker.load_registry(s.data)
        result = s.run(target)
        stored = worker.load_registry(s.data)
        used = s.selected_registries[-1]
        assert result["selection_written"] is True
        assert used == stored  # the writer receives the newly committed record
        assert stored["backup"] != previous["backup"]
        assert (s.data / stored["backup"]).read_bytes() == s.image
        assert stored["previous_backups"][0]["backup"] == previous["backup"]
        assert result["pre_switch_backup"]["backup_sha256"] == digest(s.image)
    assert len(list(s.data.glob("flash-*.bin"))) == 3
    assert s.backup.read_bytes() == b"snapshot"


@pytest.mark.parametrize("failure", ["read", "hash", "storage", "registry_commit"])
def test_failed_fresh_backup_keeps_old_recovery_point_and_never_selects(setup_run, monkeypatch, failure):
    s = setup_run
    original = (s.data / "registry.json").read_bytes()
    if failure in ("read", "hash"):
        radio_class = worker.Radio
        original_enter = radio_class.__enter__
        def enter(radio):
            result = original_enter(radio)
            if failure == "read":
                original_read = radio.esp.read_flash
                def read(offset, size):
                    return b"incomplete" if offset == 0 else original_read(offset, size)
                radio.esp.read_flash = read
            else:
                radio.esp.flash_md5sum = lambda *_: "invalid"
            return result
        monkeypatch.setattr(radio_class, "__enter__", enter)
    elif failure == "storage":
        def full_disk(*_args, **_kwargs):
            raise OSError("disk full")
        monkeypatch.setattr(worker, "private_open", full_disk)
    else:
        original_save = worker.save_json
        def save(path, value):
            if path.name == "registry.json":
                raise OSError("registry commit failed")
            return original_save(path, value)
        monkeypatch.setattr(worker, "save_json", save)
    with pytest.raises((LabError, OSError)):
        s.run()
    assert not s.calls
    assert not (s.data / "last-selection.json").exists()
    assert (s.data / "registry.json").read_bytes() == original
    assert s.backup.read_bytes() == b"snapshot"


def test_already_active_target_does_not_take_a_redundant_backup(setup_run):
    s = setup_run
    original = (s.data / "registry.json").read_bytes()
    result = s.run("meshcore")
    assert result["pre_switch_backup"] is None
    assert result["selection_written"] is False
    assert (s.data / "registry.json").read_bytes() == original
    assert not list(s.data.glob("flash-*.bin"))


def test_selection_drift_before_final_rom_session_prevents_noop_becoming_an_unbacked_write(setup_run, monkeypatch):
    s = setup_run
    original_enter = worker.Radio.__enter__
    def enter(radio):
        result = original_enter(radio)
        if len(s.entered) == 2:
            s.info["selected_slot"] = 1
        return result
    monkeypatch.setattr(worker.Radio, "__enter__", enter)
    with pytest.raises(LabError, match="Boot selection changed"):
        s.run("meshcore")
    assert not s.calls and not list(s.data.glob("flash-*.bin"))


def test_standalone_backup_requires_no_layout_registry_or_write_permission(tmp_path, monkeypatch):
    image = b"standalone identity and settings".ljust(FLASH_SIZE, b"\xff")
    flags, resets = [], []
    class ReadOnlyRadio:
        def __init__(self, _device, **options):
            flags.append(options)
            self.esp = SimpleNamespace(read_flash=lambda *_: image,
                                       flash_md5sum=lambda *_: hashlib.md5(image).hexdigest())
        def __enter__(self):
            return self
        def __exit__(self, *_):
            resets.append(True)
        def inspect(self, strict=True):
            assert strict is False
            return {"layout_supported": False, "mac": "00:11:22:33:44:55", "flash_size": FLASH_SIZE,
                    "reason": "Standalone layout", "psram_cap": 2}
        def select(self, *_):
            pytest.fail("read-only backup must never select or write")
    monkeypatch.setattr(worker, "Radio", ReadOnlyRadio)
    monkeypatch.setattr(worker, "resolve_port", lambda *_: {"device": "fake"})
    results = [worker.run("backup_current", "fake", tmp_path) for _ in range(2)]
    assert results[0]["backup"] != results[1]["backup"]
    for result in results:
        path = tmp_path / result["backup"]
        assert path.stat().st_size == 16777216
        assert path.read_bytes() == image
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        manifest = json.loads(path.with_suffix(".json").read_text())
        assert manifest["backup_sha256"] == digest(image)
        assert manifest["restore_hardware_validated"] is False
        assert stat.S_IMODE(path.with_suffix(".json").stat().st_mode) == 0o600
        assert "standalone identity" not in json.dumps(result)
    assert flags == [{}, {}] and resets == [True, True]
    assert not (tmp_path / "registry.json").exists()
    assert not (tmp_path / "last-selection.json").exists()


def test_ha_can_start_standalone_backup_with_writes_and_confirmation_off(tmp_path):
    async def scenario():
        lab = Lab(tmp_path)
        calls = []
        async def read_only(action, config, network=None):
            calls.append((action, config))
            return {"status": "preparation_backup_saved"}
        lab.worker = read_only
        config = {"device": "fake", "board_confirmed": False, "allow_boot_selection_write": False}
        lab.start("backup_current", config)
        await lab.task
        assert calls == [("backup_current", config)]
        assert lab.state["runs"][-1]["status"] == "completed"
    asyncio.run(scenario())
