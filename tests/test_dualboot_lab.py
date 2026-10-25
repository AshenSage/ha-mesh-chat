import asyncio
import binascii
import hashlib
import json
import struct

import pytest

from lab.layout import (EXPECTED, SECTOR, LabError, boot_entries, plan_selection,
                        selected_slot, validate_table)
from lab.server import Lab
from lab.worker import Radio, compare_profile, require_same_device, save_json


def attested(info):
    return {**info, "app_md5": info.get("app_md5") or {"ota_0": "mc", "ota_1": "mt"},
            "profiles": {n: {} for n in ("meshcore", "meshtastic")},
            "slot_attestation": {n: {"slot": slot, "app_md5": (info.get("app_md5") or
                {"ota_0": "mc", "ota_1": "mt"})[f"ota_{slot}"], "evidence": "fake USB protocol"}
                for n, slot in (("meshcore", 0), ("meshtastic", 1))}}


def table(entries=EXPECTED):
    raw = b"".join(struct.pack("<HBBII16sI", 0x50AA, kind, subtype, address, size,
                               name.encode().ljust(16, b"\x00"), 0)
                   for name, kind, subtype, address, size in entries)
    return (raw + b"\xeb\xeb" + b"\xff" * 14 + hashlib.md5(raw).digest()).ljust(SECTOR, b"\xff")


def otadata(first=1, second=None, state=2):
    raw = bytearray(b"\xff" * (2 * SECTOR))
    for sector, seq in enumerate((first, second)):
        if seq is None:
            continue
        offset = sector * SECTOR
        struct.pack_into("<I", raw, offset, seq)
        struct.pack_into("<I", raw, offset + 24, state)
        struct.pack_into("<I", raw, offset + 28, binascii.crc32(struct.pack("<I", seq), 0xFFFFFFFF) & 0xFFFFFFFF)
    return bytes(raw)


def apply(raw, plan):
    sector, content = plan
    return raw[:sector * SECTOR] + content + raw[(sector + 1) * SECTOR:]


def test_accept_exact_table_and_reject_checksum_or_wrong_isolation():
    assert len(validate_table(table())) == 64
    corrupt = bytearray(table())
    corrupt[12] ^= 1
    with pytest.raises(LabError, match="MD5"):
        validate_table(bytes(corrupt))
    with pytest.raises(LabError, match="Unsupported layout"):
        validate_table(table(EXPECTED[:-2] + EXPECTED[-1:]))
    with pytest.raises(LabError, match="incomplete"):
        validate_table(table()[:100])


def test_forty_switches_preserve_other_sector_and_select_target():
    raw = otadata()
    for index in range(40):
        target = "meshtastic" if index % 2 == 0 else "meshcore"
        sector, content = plan_selection(raw, target)
        old = raw
        raw = apply(raw, (sector, content))
        assert raw[(1 - sector) * SECTOR:(2 - sector) * SECTOR] == old[(1 - sector) * SECTOR:(2 - sector) * SECTOR]
        assert selected_slot(raw) == (1 if target == "meshtastic" else 0)
        assert len(raw) == 2 * SECTOR
        assert len(boot_entries(raw)) == 2


def test_boot_selection_guardrails():
    assert plan_selection(otadata(), "meshcore") is None
    with pytest.raises(LabError, match="No valid"):
        plan_selection(b"\xff" * (2 * SECTOR), "meshcore")
    with pytest.raises(LabError, match="rollback"):
        plan_selection(otadata(state=1), "meshtastic")
    with pytest.raises(LabError, match="rollover"):
        plan_selection(otadata(0xFFFFFFFE), "meshcore")
    with pytest.raises(LabError, match="Ambiguous"):
        plan_selection(otadata(1, 1), "meshtastic")
    assert selected_slot(otadata(1, 2)) == 1
    raw = bytearray(otadata(1, 2))
    raw[SECTOR + 28] ^= 1
    assert selected_slot(bytes(raw)) == 0  # surviving, valid recovery copy


def test_never_accept_changed_board_build_or_profile():
    record = {"mac": "00:11", "flash_size": 0x1000000, "table_sha256": "abc", "app_md5": {"ota_0": "def"}}
    require_same_device(record, record)
    for key in record:
        with pytest.raises(LabError, match="changed"):
            require_same_device({**record, key: "other"}, record)
    baseline = {"network": "meshcore", "identity_sha256": "key", "settings_sha256": "radio"}
    compare_profile(baseline, baseline)
    for key in baseline:
        with pytest.raises(LabError, match="Profile changed"):
            compare_profile({**baseline, key: "other"}, baseline)


class Stub:
    FLASH_WRITE_SIZE = 0x4000

    def __init__(self):
        self.raw = otadata()
        self.writes = []

    def read_flash(self, offset, size):
        if size == 288:
            header = bytearray(288)
            header[0] = 0xE9
            header[32:36] = b"\x32\x54\xcd\xab"
            name = b"meshcore" if offset == 0x220000 else b"meshtastic"
            header[80:80 + len(name)] = name
            return bytes(header)
        assert (offset, size) == (0x1C000, 2 * SECTOR)
        return self.raw

    def flash_defl_begin(self, size, packed_size, offset):
        assert size == SECTOR
        assert offset == 0x1D000
        self.writes.append((offset, size))

    def flash_defl_block(self, packed, number):
        import zlib
        assert number == 0
        content = zlib.decompress(packed)
        assert len(content) == SECTOR
        self.raw = self.raw[:SECTOR] + content

    def flash_defl_finish(self, reboot):
        assert reboot is False


def test_hardware_writer_only_modifies_inactive_ota_sector(tmp_path):
    radio = Radio("fake", board_confirmed=True, allow_boot_selection_write=True)
    radio.mac = "00:11"
    radio.psram_cap = 2
    radio.esp = Stub()
    info = {"mac": radio.mac, "flash_size": 0x1000000, "table_sha256": "abc", "app_md5": {}}
    info = attested(info)
    radio.inspect = lambda: info
    assert radio.select("meshtastic", info, tmp_path)
    assert radio.esp.writes == [(0x1D000, SECTOR)]
    saved = json.loads((tmp_path / "last-selection.json").read_text())
    assert saved["otadata_hex"] == otadata().hex()


def test_storage_failure_prevents_write(tmp_path, monkeypatch):
    radio = Radio("fake", board_confirmed=True, allow_boot_selection_write=True)
    radio.mac = "00:11"
    radio.psram_cap = 2
    radio.esp = Stub()
    info = {"mac": "00:11"}
    info = attested(info)
    radio.inspect = lambda: info
    def fail(*_):
        raise OSError("disk full")
    monkeypatch.setattr("lab.worker.save_json", fail)
    with pytest.raises(OSError):
        radio.select("meshtastic", info, tmp_path)
    assert radio.esp.writes == []


def test_restart_marks_running_job_interrupted(tmp_path):
    save_json(tmp_path / "report.json", {"runs": [{"status": "running", "action": "switch"}]})
    lab = Lab(tmp_path)
    assert lab.state["runs"][0]["status"] == "interrupted"
    assert lab.task is None


def test_write_requires_explicit_lab_configuration(tmp_path):
    lab = Lab(tmp_path)
    with pytest.raises(LabError, match="Select a USB"):
        lab.start("switch", {}, "meshcore")
    with pytest.raises(LabError, match="Confirm Heltec"):
        lab.start("switch", {"device": "/dev/test"}, "meshcore")
    with pytest.raises(LabError, match="Enable experimental"):
        lab.start("switch", {"device": "/dev/test", "board_confirmed": True}, "meshcore")


def test_cycle_counts_real_transitions_and_stops_on_first_failure(tmp_path):
    async def scenario(fail=False):
        lab = Lab(tmp_path)
        calls = []
        async def fake(action, config, network=None):
            if action == "resnapshot":
                return {"status": "snapshot_saved"}
            calls.append(network)
            if fail and len(calls) == 3:
                raise LabError("target failed to reply")
            return {"status": "switch_verified", "selection_written": True}
        lab.worker = fake
        run = {"action": "cycle", "target": "meshcore", "cycles": 3, "status": "running", "steps": []}
        lab.state["runs"].append(run)
        await lab.execute(run, {})
        return run, calls
    run, calls = asyncio.run(scenario())
    assert run["status"] == "completed"
    assert calls == ["meshcore", "meshtastic", "meshcore", "meshtastic", "meshcore", "meshtastic", "meshcore"]
    assert len([x for x in run["steps"] if "cycle" in x]) == 6
    run, calls = asyncio.run(scenario(fail=True))
    assert run["status"] == "failed"
    assert len(calls) == 3


def test_noop_cannot_pass_a_cycle(tmp_path):
    async def scenario():
        lab = Lab(tmp_path)
        async def fake(*_):
            return {"status": "already_selected_verified", "selection_written": False}
        lab.worker = fake
        run = {"action": "cycle", "target": "meshcore", "cycles": 1, "status": "running", "steps": []}
        lab.state["runs"].append(run)
        await lab.execute(run, {})
        return run
    assert asyncio.run(scenario())["status"] == "failed"


def test_ingress_ui_api_and_no_secret_backup_endpoint(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    import lab.server as server
    monkeypatch.setattr(server, "LOCAL", True)
    async def scenario():
        async with TestClient(TestServer(server.create_app(tmp_path))) as client:
            response = await client.get("/")
            assert response.status == 200
            assert "Dualboot Lab" in await response.text()
            response = await client.get("/api/status")
            assert response.status == 200
            assert (await response.json())["busy"] is False
            response = await client.post("/api/start", json={"action": "switch", "network": "meshcore"})
            assert response.status == 400
            response = await client.post("/api/start", data='{"action":"inspect"}')
            assert response.status == 415
            response = await client.get("/api/report")
            assert response.status == 200
            assert "attachment" in response.headers["Content-Disposition"]
            response = await client.get("/registry.json")
            assert response.status == 404
            response = await client.get("/flash-backup.bin")
            assert response.status == 404
    asyncio.run(scenario())


def test_direct_access_is_denied(tmp_path, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    import lab.server as server
    monkeypatch.setattr(server, "LOCAL", False)
    async def scenario():
        async with TestClient(TestServer(server.create_app(tmp_path))) as client:
            response = await client.get("/api/status")
            assert response.status == 403
    asyncio.run(scenario())


def test_meshtastic_runtime_requires_public_key_and_closes_transport(monkeypatch):
    import base64
    from types import SimpleNamespace
    from meshtastic.protobuf import config_pb2
    import meshtastic.serial_interface
    from lab.worker import probe_meshtastic
    user = {"id": "!12345678", "longName": "Lab", "shortName": "LAB",
            "publicKey": base64.b64encode(b"k" * 32).decode()}
    closed = []
    interface = SimpleNamespace(getMyNodeInfo=lambda: {"user": user},
                myInfo=SimpleNamespace(my_node_num=0x12345678),
                metadata=SimpleNamespace(firmware_version="test-build"),
                localNode=SimpleNamespace(localConfig=SimpleNamespace(lora=config_pb2.Config.LoRaConfig()),
                     channels=[SimpleNamespace(index=0, role=1, settings=SimpleNamespace(name="test", psk=b"secret"))]),
                close=lambda: closed.append(True))
    monkeypatch.setattr(meshtastic.serial_interface, "SerialInterface", lambda **_: interface)
    result = probe_meshtastic("fake")
    assert result["network"] == "meshtastic"
    assert len(result["identity_sha256"]) == 64
    assert closed == [True]
    user.pop("publicKey")
    with pytest.raises(LabError, match="node ID alone"):
        probe_meshtastic("fake")
    assert closed == [True, True]


def test_meshcore_runtime_requires_self_info_and_closes_transport(monkeypatch):
    from types import SimpleNamespace
    from meshcore import MeshCore, EventType
    from lab.worker import probe_meshcore
    closed = []
    event = SimpleNamespace(type=EventType.SELF_INFO, payload={"public_key": "ab" * 32, "name": "Lab"})
    async def appstart():
        return event
    async def disconnect():
        closed.append(True)
    async def connect(*_, **__):
        async def query():
            return SimpleNamespace(type=EventType.DEVICE_INFO, payload={"max_channels": 1})
        async def channel(index):
            return SimpleNamespace(type=EventType.CHANNEL_INFO, payload={"channel_idx": index,
                                   "channel_name": "test", "channel_secret": b"x" * 16})
        async def contacts():
            return SimpleNamespace(type=EventType.CONTACTS, payload={})
        return SimpleNamespace(commands=SimpleNamespace(send_appstart=appstart, send_device_query=query,
                               get_channel=channel, get_contacts=contacts), disconnect=disconnect)
    monkeypatch.setattr(MeshCore, "create_serial", connect)
    result = asyncio.run(probe_meshcore("fake"))
    assert result["network"] == "meshcore"
    assert closed == [True]
    event.type = EventType.ERROR
    with pytest.raises(LabError, match="SELF_INFO"):
        asyncio.run(probe_meshcore("fake"))
    assert closed == [True, True]
