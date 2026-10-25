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
from test_dualboot_lab import attested, Stub


def profile(network):
    value = {"network": network, "identity_sha256": network + "-key",
             "settings_sha256": network + "-settings", "evidence": "fake protocol"}
    if network == "meshcore":
        value.update(radio_sha256="radio", channels_sha256="channels", contacts_count=1, contacts_set=["peer"])
    return value


@pytest.fixture
def setup_run(tmp_path, monkeypatch):
    info = {"mac": "mac", "flash_size": 0x1000000, "table_sha256": "table",
            "bootloader_md5": "boot", "selector_nvs_md5": "selector",
            "app_md5": {"ota_0": "mc", "ota_1": "mt"}, "selected_slot": 0}
    backup = tmp_path / "backup.bin"
    backup.write_bytes(b"snapshot")
    registry = {**attested(info), "backup": backup.name, "backup_sha256": digest(backup.read_bytes()),
                "profiles": {n: profile(n) for n in ("meshcore", "meshtastic")}}
    worker.save_json(tmp_path / "registry.json", registry)
    calls, observations, entered = [], [], []
    class FakeRadio:
        def __init__(self, port, **flags):
            self.flags = flags
            self.esp = Stub()
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


@pytest.mark.parametrize("key", ["mac", "table_sha256", "app_md5", "bootloader_md5", "selector_nvs_md5"])
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


def test_b1_missing_target_baseline_cannot_write_and_noop_is_verified(setup_run):
    s = setup_run
    del s.registry["profiles"]["meshtastic"]
    worker.save_json(s.data / "registry.json", s.registry)
    with pytest.raises(LabError, match="slot attestation"):
        s.run()
    assert not s.calls
    worker.save_json(s.data / "registry.json", {**s.registry, "profiles": {n: profile(n) for n in ("meshcore", "meshtastic")}})
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


@pytest.mark.parametrize("damage", ["missing", "swapped", "hash"])
def test_r2_1_attestation_failure_precedes_probes_and_select(setup_run, damage):
    s = setup_run
    record = s.registry["slot_attestation"]["meshtastic"]
    if damage == "missing":
        del s.registry["slot_attestation"]["meshtastic"]
    elif damage == "swapped":
        record["slot"] = 0
    else:
        record["app_md5"] = "changed"
    worker.save_json(s.data / "registry.json", s.registry)
    s.observations.append(AssertionError("probe must not run"))
    with pytest.raises(LabError, match="slot attestation"):
        s.run()
    assert not s.calls and len(s.entered) == 1 and len(s.observations) == 1


def test_r2_1_baseline_attests_only_manually_selected_runtime(setup_run):
    s = setup_run
    s.registry.pop("slot_attestation")
    worker.save_json(s.data / "registry.json", s.registry)
    assert s.run("meshcore", "baseline")["status"] == "baseline_verified"
    assert worker.load_registry(s.data)["slot_attestation"]["meshcore"]["app_md5"] == "mc"
    assert not s.calls


@pytest.mark.parametrize("status", ["pending", "written", "unknown"])
def test_r2_5_open_journal_blocks_worker_and_parent_before_device(setup_run, status):
    from lab.server import Lab
    s = setup_run
    worker.save_json(s.data / "last-selection.json", {"status": status, "otadata_hex": "original"})
    with pytest.raises(LabError, match="Open selection journal"):
        s.run()
    for action in ("switch", "cycle"):
        with pytest.raises(LabError, match="Open selection journal"):
            Lab(s.data).start(action, {"device": "fake", "board_confirmed": True,
                                      "allow_boot_selection_write": True}, "meshtastic")
    assert not s.entered and not s.calls
    assert json.loads((s.data / "last-selection.json").read_text())["otadata_hex"] == "original"


def test_r2_5_acknowledgement_preserves_original_without_device(tmp_path, monkeypatch):
    original = {"status": "written", "target": "meshtastic", "otadata_hex": "original"}
    worker.save_json(tmp_path / "last-selection.json", original)
    monkeypatch.setattr(worker, "resolve_port", lambda *_: pytest.fail("no device access"))
    with pytest.raises(LabError, match="reason"):
        worker.run("acknowledge_journal", "", tmp_path, board_confirmed=True)
    result = worker.run("acknowledge_journal", "", tmp_path, board_confirmed=True,
                        reason="manual_recovery_checked")
    worker.require_closed_journal(tmp_path)
    assert json.loads((tmp_path / result["archive"]).read_text())["otadata_hex"] == "original"
    assert json.loads((tmp_path / "last-selection.json").read_text())["status"] == "acknowledged"


@pytest.mark.parametrize("case", ["success", "probe_failure", "wrong_target", "pending"])
def test_r2_6_verification_retry_never_writes_and_closes_only_matching_written_journal(setup_run, case):
    s = setup_run
    state = {"status": "pending" if case == "pending" else "written", "target": "meshcore",
             "otadata_hex": "preserve"}
    if case == "wrong_target":
        state["target"] = "meshtastic"
    worker.save_json(s.data / "last-selection.json", state)
    if case == "probe_failure":
        s.observations.extend([profile("meshcore"), LabError("probe failed")])
    if case == "success":
        result = s.run("meshcore", "verify_selection")
        assert result["status"] == "already_selected_verified" and not result["selection_written"]
        assert json.loads((s.data / "last-selection.json").read_text())["status"] == "verified"
    else:
        with pytest.raises(LabError):
            s.run("meshcore", "verify_selection")
        assert json.loads((s.data / "last-selection.json").read_text()) == state
    assert not s.calls


@pytest.mark.parametrize("change,component", [("add", None), ("remove", "contacts_set"), ("key", "channels_sha256"), ("old", "Baseline neu erfassen")])
def test_r2_2_meshcore_components_allow_contact_growth_only(change, component):
    baseline = profile("meshcore")
    observed = dict(baseline)
    if change == "add":
        observed.update(contacts_set=["peer", "new"], contacts_count=2)
    elif change == "remove":
        observed.update(contacts_set=[], contacts_count=0)
    elif change == "key":
        observed["channels_sha256"] = "changed key hash"
    else:
        baseline.pop("radio_sha256")
    if component:
        with pytest.raises(LabError, match=component):
            worker.compare_profile(observed, baseline)
    else:
        worker.compare_profile(observed, baseline)


def test_r2_2_contact_loss_before_switch_prevents_select(setup_run):
    s = setup_run
    s.observations.append({**profile("meshcore"), "contacts_set": [], "contacts_count": 0})
    with pytest.raises(LabError, match="contacts_set"):
        s.run()
    assert not s.calls



def test_r2_3_resnapshot_profile_drift_preserves_pointer_and_skips_snapshot(setup_run, monkeypatch):
    s = setup_run
    original = (s.data / "registry.json").read_bytes()
    s.observations.append({**profile("meshcore"), "identity_sha256": "new key"})
    monkeypatch.setattr(worker, "snapshot", lambda *_: pytest.fail("no snapshot after profile drift"))
    with pytest.raises(LabError, match="identity_sha256"):
        s.run(action="resnapshot")
    assert (s.data / "registry.json").read_bytes() == original
    assert not s.calls


def test_r2_3_snapshot_happens_only_after_matching_live_probe(setup_run, monkeypatch):
    s = setup_run
    calls = []
    def snapshot(_radio, _data, registry):
        calls.append("snapshot")
        return {**registry, "snapshot_at": 1, "snapshot_profiles": sorted(registry["profiles"]), "retention_pending": []}
    monkeypatch.setattr(worker, "snapshot", snapshot)
    result = s.run(action="resnapshot")
    assert result["live_profile_verified"] == "meshcore" and calls == ["snapshot"]
    assert len(s.entered) == 2 and not s.calls
