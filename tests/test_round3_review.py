"""Round 3 regressions: simulated protocols/flash only, no serial ports."""
import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from lab import diagnostics, worker
from lab.layout import LabError, digest


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
