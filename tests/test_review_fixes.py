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
        worker.run("resnapshot", "fake", tmp_path)


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
    radio = worker.Radio("fake")
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
    with worker.Radio("fake") as radio:
        assert radio.psram_cap == cap
        if cap != 2:
            with pytest.raises(LabError, match="PSRAM cap 2"):
                radio.select("meshcore", {}, tmp_path)
    assert closed == ["reset", "close"]
