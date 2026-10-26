"""Round 3 regressions: simulated protocols/flash only, no serial ports."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from lab import diagnostics, worker
from lab.layout import LabError, digest
from test_run_orchestration import setup_run  # shared FakeRadio/run fixture


@pytest.fixture
def meshcore_contacts(monkeypatch):
    from meshcore import MeshCore, EventType
    contacts = {str(i): {"public_key": f"{i + 1:064x}", "adv_name": f"peer-{i}", "type": 1, "flags": 0}
                for i in range(350)}
    async def start():
        return SimpleNamespace(type=EventType.SELF_INFO, payload={"public_key": "ab" * 32, "name": "lab"})
    async def query():
        return SimpleNamespace(type=EventType.DEVICE_INFO, payload={"max_channels": 1})
    async def channel(index):
        return SimpleNamespace(type=EventType.CHANNEL_INFO,
            payload={"channel_idx": index, "channel_name": "lab", "channel_secret": b"s" * 16})
    async def read_contacts(*, timeout):
        assert timeout == 120
        return SimpleNamespace(type=EventType.CONTACTS, payload=contacts)
    async def close():
        pass
    async def connect(port, **_):
        assert port == "fake"
        return SimpleNamespace(commands=SimpleNamespace(send_appstart=start, send_device_query=query,
            get_channel=channel, get_contacts=read_contacts), disconnect=close)
    monkeypatch.setattr(MeshCore, "create_serial", connect)
    return contacts, lambda: asyncio.run(worker.probe_meshcore("fake"))


@pytest.mark.parametrize("field,value", [("adv_name", "advertised-new-name"), ("flags", 1), ("type", 2)])
def test_n1_metadata_changes_warn_without_losing_public_key_membership(meshcore_contacts, monkeypatch, field, value):
    contacts, probe = meshcore_contacts
    baseline = probe()
    contacts["349"][field] = value
    observed = probe()
    events = []
    monkeypatch.setattr(diagnostics, "SINK", events.append)
    worker.compare_profile(observed, baseline)
    assert len(baseline["contacts_set"]) == 350
    assert observed["contacts_set"] == baseline["contacts_set"]
    assert digest(bytes.fromhex(contacts["349"]["public_key"])) in observed["contacts_set"]
    assert events == [{"type": "warning", "code": "meshcore_contacts_meta_changed"}]


def test_n1_key_loss_blocks_and_growth_is_allowed(meshcore_contacts):
    contacts, probe = meshcore_contacts
    baseline = probe()
    removed = contacts.pop("349")
    with pytest.raises(LabError, match="contacts_set"):
        worker.compare_profile(probe(), baseline)
    contacts["349"] = removed
    contacts["extra"] = {"public_key": "cd" * 32, "adv_name": "new", "type": 1, "flags": 0}
    worker.compare_profile(probe(), baseline)


@pytest.mark.parametrize("damage", ["missing_schema", "old_schema", "missing_metadata"])
def test_n1_old_contact_fingerprint_baselines_demand_recapture(meshcore_contacts, damage):
    _, probe = meshcore_contacts
    observed = probe()
    baseline = copy.deepcopy(observed)
    if damage == "old_schema":
        baseline["contacts_schema"] = 1
    else:
        baseline.pop("contacts_schema" if damage == "missing_schema" else "contacts_meta_sha256")
    with pytest.raises(LabError, match="Baseline neu erfassen"):
        worker.compare_profile(observed, baseline)



def test_n2_reports_omit_contacts_but_registry_and_comparison_retain_them(setup_run, meshcore_contacts):
    s = setup_run
    _, probe = meshcore_contacts
    full = probe()
    s.registry["profiles"]["meshcore"] = full
    worker.save_json(s.data / "registry.json", s.registry)
    s.observations.append(full)
    baseline_result = s.run("meshcore", "baseline")
    stored = worker.load_registry(s.data)["profiles"]["meshcore"]
    assert len(stored["contacts_set"]) == 350
    worker.compare_profile(full, stored)
    s.observations.extend([full] * 4)
    switch_result = s.run("meshcore")
    for result in (baseline_result, switch_result):
        assert result["contacts_count"] == 350
        assert {k for k in result if k.startswith("contacts_")} == {"contacts_count"}
        assert "contacts_set" not in json.dumps(result)
        assert len(json.dumps(result)) < 1500


@pytest.mark.parametrize("mac", ["ff:ff:other-board", None])
def test_n3_foreign_or_missing_journal_mac_blocks_before_probe_and_preserves_bytes(setup_run, mac):
    s = setup_run
    journal = {"status": "written", "target": "meshcore", "otadata_hex": "preserve original"}
    if mac is not None:
        journal["mac"] = mac
    path = s.data / "last-selection.json"
    worker.save_json(path, journal)
    before = path.read_bytes()
    s.observations.append(AssertionError("probe must not be called after foreign journal"))
    with pytest.raises(LabError, match="journal MAC"):
        s.run("meshcore", "verify_selection")
    assert path.read_bytes() == before and not s.calls and len(s.observations) == 1


def test_n3_transition_rechecks_journal_mac_after_probes(setup_run, monkeypatch):
    from test_run_orchestration import profile
    s = setup_run
    path = s.data / "last-selection.json"
    worker.save_json(path, {"status": "written", "target": "meshcore", "mac": "mac"})
    calls = []
    def probe(*_):
        calls.append(True)
        if len(calls) == 2:
            worker.save_json(path, {"status": "written", "target": "meshcore", "mac": "other"})
        return profile("meshcore")
    monkeypatch.setattr(worker, "probe", probe)
    with pytest.raises(LabError, match="journal MAC"):
        s.run("meshcore", "verify_selection")
    assert json.loads(path.read_text()) == {"status": "written", "target": "meshcore", "mac": "other"}
    assert not s.calls



def test_n4_legacy_backup_links_are_flattened_on_load_and_next_save(tmp_path):
    chain = None
    for index in range(40):
        chain = {"backup": f"flash-{index}.bin", "backup_sha256": str(index), "previous_backup": chain}
    original = {"backup": "flash-0.bin", "previous_backup": None}
    worker.save_json(tmp_path / "registry.json", {"backup": "flash-current.bin", "previous_backup": chain,
                                                "enrol_backup": original})
    registry = worker.load_registry(tmp_path)
    assert "previous_backup" not in registry
    assert [p["backup"] for p in registry["previous_backups"]] == [f"flash-{i}.bin" for i in reversed(range(40))]
    assert all("previous_backup" not in p for p in registry["previous_backups"])
    assert registry["enrol_backup"] == {"backup": "flash-0.bin"}
    worker.save_json(tmp_path / "registry.json", registry)
    assert '"previous_backup":' not in (tmp_path / "registry.json").read_text()
    assert worker.load_registry(tmp_path) == registry


def test_n4_1200_real_snapshot_helpers_with_pruning_remain_flat_and_protect_recovery(tmp_path, monkeypatch):
    import hashlib
    from test_dualboot_lab import table
    image = b"\xff" * 0x8000 + table()
    monkeypatch.setattr(worker, "FLASH_SIZE", len(image))
    radio = SimpleNamespace(esp=SimpleNamespace(read_flash=lambda *_: image,
                            flash_md5sum=lambda *_: hashlib.md5(image).hexdigest()))
    registry = {"profiles": {}}
    names = []
    for index in range(1200):
        registry = worker.snapshot(radio, tmp_path, registry)
        names.append(registry["backup"])
        if index % 10 == 9:
            worker.prune_snapshots(tmp_path, "retention_reviewed")
            registry = worker.load_registry(tmp_path)
            protected = {names[0], *names[-2:]}
            assert {p.name for p in tmp_path.glob("flash-*.bin")} == protected
            assert registry["enrol_backup"]["backup"] == names[0]
            assert registry["previous_backups"][0]["backup"] == names[-2]
            assert len(registry["previous_backups"]) == 2
            assert not worker.retention_candidates(registry)
        assert "previous_backup" not in registry
        assert all("previous_backup" not in p for p in registry["previous_backups"])
    assert len((tmp_path / "registry.json").read_bytes()) < 2500
    assert len(json.loads((tmp_path / "registry.json").read_text())["previous_backups"]) == 2
