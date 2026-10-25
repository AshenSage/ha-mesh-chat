"""Complete worker.run orchestration with fake radios/probes, never USB."""
import hashlib
import importlib.metadata
import inspect
import json
import struct
import zlib
from types import SimpleNamespace

import pytest

from lab import worker
from lab.layout import LabError, digest


def profile(network):
    return {"network": network, "identity_sha256": network + "-key", "settings_sha256": network + "-settings"}


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    info = {"mac": "mac", "flash_size": 0x1000000, "table_sha256": "table",
            "app_md5": {"ota_0": "mc", "ota_1": "mt"}, "selected_slot": 0}
    backup = tmp_path / "backup.bin"
    backup.write_bytes(b"snapshot")
    registry = {**info, "backup": backup.name, "backup_sha256": digest(backup.read_bytes()),
                "profiles": {n: profile(n) for n in ("meshcore", "meshtastic")}}
    worker.save_json(tmp_path / "registry.json", registry)
    calls, observations, entered = [], [], []
    class FakeRadio:
        def __init__(self, port, **flags):
            self.flags = flags
        def __enter__(self):
            entered.append(True)
            return self
        def __exit__(self, *_):
            pass
        def inspect(self, **_):
            return dict(info)
        def select(self, network, record, data):
            assert self.flags == {"board_confirmed": True, "allow_boot_selection_write": True}
            calls.append(network)
            changed = network != "meshcore"
            if changed:
                worker.save_json(data / "last-selection.json", {"status": "written", "target": network})
            return changed
    def probe(network, *_):
        value = observations.pop(0) if observations else profile(network)
        if isinstance(value, Exception):
            raise value
        return value
    monkeypatch.setattr(worker, "Radio", FakeRadio)
    monkeypatch.setattr(worker, "probe", probe)
    monkeypatch.setattr(worker, "resolve_port", lambda *_: {"device": "fake"})
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)
    def run(target="meshtastic", action="switch"):
        return worker.run(action, "fake", tmp_path, target, board_confirmed=True,
                          allow_boot_selection_write=True)
    return SimpleNamespace(run=run, calls=calls, observations=observations, entered=entered,
                           info=info, registry=registry, backup=backup, data=tmp_path)


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_b1_backup_failure_prevents_select(setup_run, damage):
    s = setup_run
    s.backup.unlink() if damage == "missing" else s.backup.write_bytes(b"bad")
    with pytest.raises(LabError, match="backup is missing or damaged"):
        s.run()
    assert not s.calls and not s.entered


@pytest.mark.parametrize("key", ["mac", "table_sha256", "app_md5"])
def test_b1_changed_device_blocks_select(setup_run, key):
    s = setup_run
    s.info[key] = "changed"
    with pytest.raises(LabError, match="changed"):
        s.run()
    assert not s.calls


@pytest.mark.parametrize("probe_index", [0, 1])
def test_b1_either_current_probe_mismatch_prevents_select(setup_run, probe_index):
    s = setup_run
    s.observations.extend([profile("meshcore")] * probe_index + [{**profile("meshcore"), "identity_sha256": "changed"}])
    with pytest.raises(LabError, match="Profile changed"):
        s.run()
    assert not s.calls


@pytest.mark.parametrize("target_probe", [0, 1])
def test_b1_target_probe_failure_cannot_verify_or_retry(setup_run, target_probe):
    s = setup_run
    s.observations.extend([profile("meshcore"), profile("meshcore")] +
                          [profile("meshtastic")] * target_probe + [LabError("target probe failed")])
    with pytest.raises(LabError, match="target probe failed"):
        s.run()
    assert s.calls == ["meshtastic"]
    assert json.loads((s.data / "last-selection.json").read_text())["status"] == "written"


def test_b1_first_baseline_and_noop_are_not_claimed_as_preservation_or_transition(setup_run):
    s = setup_run
    del s.registry["profiles"]["meshtastic"]
    worker.save_json(s.data / "registry.json", s.registry)
    result = s.run()
    assert result["status"] == "first_boot_baseline" and result["profile_verified"] is False
    assert "meshtastic" in worker.load_registry(s.data)["profiles"]
    result = s.run("meshcore")
    assert result["status"] == "already_selected_verified" and not result["selection_written"]


def test_b1_pinned_esptool_contract_invokes_real_decorated_methods_without_port():
    from esptool.targets.esp32s3 import ESP32S3StubLoader
    assert importlib.metadata.version("esptool") == "4.11.0"
    esp = object.__new__(ESP32S3StubLoader)  # no serial constructor
    commands = []
    def command(*args, **kwargs):
        commands.append((args, kwargs))
        return b"\0" * 16
    esp.check_command = command
    packed = zlib.compress(b"\xff" * 4096)
    esp.flash_defl_begin(4096, len(packed), 0x1D000)
    esp.flash_defl_block(packed, 0)
    esp.flash_defl_finish(reboot=False)
    assert struct.unpack("<IIII", commands[0][0][2])[0] == 4096
    assert struct.unpack("<IIII", commands[0][0][2])[3] == 0x1D000
    assert esp.flash_md5sum(0, 4096) == "00" * 16
    frames = iter([b"x" * 288, hashlib.md5(b"x" * 288).digest()])
    esp.read = lambda: next(frames)
    esp.write = lambda data: None
    assert esp.read_flash(0x220000, 288) == b"x" * 288
    # These wrappers omit functools.wraps in 4.11. Inspect their func closure,
    # and bind exactly the argument shape actually used by our writer.
    for name, args, kwargs in [("flash_defl_begin", (esp, 4096, len(packed), 0x1D000), {}),
                               ("flash_defl_block", (esp, packed, 0), {}),
                               ("flash_defl_finish", (esp,), {"reboot": False})]:
        function = getattr(ESP32S3StubLoader, name)
        while "func" in inspect.getclosurevars(function).nonlocals:
            function = inspect.getclosurevars(function).nonlocals["func"]
        inspect.signature(function).bind(*args, **kwargs)
