"""Strict, fail-closed partition and boot-selection validation.

Format references: Espressif gen_esp32part.py, bootloader_common.c and
components/app_update/otatool.py. No application or profile writes live here.
"""

import binascii
import hashlib
import struct
from dataclasses import dataclass

SECTOR = 0x1000
FLASH_SIZE = 0x1000000
TABLE_OFFSET = 0x8000
NETWORKS = {"meshcore": 0, "meshtastic": 1}

# Reference repository ROOT table, not its conflicting selector/ table.
EXPECTED = (
    ("nvs", 1, 2, 0x9000, 0x10000),
    ("nvs_sel", 1, 2, 0x19000, 0x3000),
    ("otadata", 1, 0, 0x1C000, 0x2000),
    ("factory", 0, 0, 0x20000, 0x200000),
    ("ota_0", 0, 0x10, 0x220000, 0x460000),
    ("ota_1", 0, 0x11, 0x680000, 0x570000),
    ("spiffs", 1, 0x82, 0xBF0000, 0x200000),
    ("mc_spiffs", 1, 0x82, 0xDF0000, 0x200000),
    ("coredump", 1, 3, 0xFF0000, 0x10000),
)
OTA_OFFSET, OTA_SIZE = next((row[3], row[4]) for row in EXPECTED if row[0] == "otadata")


class LabError(Exception):
    """A blocked or failed lab operation."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def app_project(header):
    """ESP image header (24), first segment header (8), esp_app_desc_t."""
    if len(header) < 288 or header[0] != 0xE9 or header[32:36] != b"\x32\x54\xcd\xab":
        raise LabError("Missing ESP application descriptor")
    try:
        return header[80:112].split(b"\0", 1)[0].decode("ascii").lower()
    except UnicodeError as exc:
        raise LabError("Invalid application project name") from exc


def verify_slot_projects(read_flash):
    projects = {}
    for network, slot in NETWORKS.items():
        address = next(row[3] for row in EXPECTED if row[0] == f"ota_{slot}")
        project = app_project(read_flash(address, 288))
        if project != network and not project.startswith(network + "-"):
            raise LabError(f"ota_{slot} project does not identify {network}; refuse boot-selection write")
        projects[network] = project
    return projects


def validate_table(raw):
    if len(raw) != SECTOR:
        raise LabError("Partition table read is incomplete")
    entries = []
    md5_seen = False
    for offset in range(0, 0xC00, 32):
        row = raw[offset:offset + 32]
        if row == b"\xff" * 32:
            break
        if row[:2] == b"\xeb\xeb":
            if row[2:16] != b"\xff" * 14 or row[16:] != hashlib.md5(raw[:offset]).digest():
                raise LabError("Partition table MD5 is invalid")
            md5_seen = True
            if raw[offset + 32:0xC00] != b"\xff" * (0xC00 - offset - 32):
                raise LabError("Unexpected partition entries after checksum")
            break
        if row[:2] != b"\xaa\x50":
            raise LabError("Unknown partition table entry")
        _, kind, subtype, address, size, label, flags = struct.unpack("<HBBII16sI", row)
        if flags:
            raise LabError("Encrypted/flagged partitions are unsupported in this lab")
        try:
            name = label.rstrip(b"\x00").decode("ascii")
        except UnicodeError as exc:
            raise LabError("Invalid partition label") from exc
        entries.append((name, kind, subtype, address, size))
    if not md5_seen or tuple(entries) != EXPECTED:
        raise LabError("Unsupported layout: expected the isolated 16 MB lab table, with MD5")
    return digest(raw)


@dataclass(frozen=True)
class BootEntry:
    sector: int
    seq: int
    state: int


def boot_entries(raw):
    if len(raw) != 2 * SECTOR:
        raise LabError("Incomplete OTA selection read")
    result = []
    for sector in (0, 1):
        row = raw[sector * SECTOR:sector * SECTOR + 32]
        seq = struct.unpack_from("<I", row)[0]
        state, crc = struct.unpack_from("<II", row, 24)
        expected_crc = binascii.crc32(row[:4], 0xFFFFFFFF) & 0xFFFFFFFF
        if seq == 0 and crc == expected_crc:
            raise LabError("CRC-valid OTA sequence zero requires explicit investigation")
        if seq != 0xFFFFFFFF and crc == expected_crc:
            # NEW/PENDING/INVALID/ABORTED need firmware rollback handling.
            if state not in (2, 0xFFFFFFFF):
                raise LabError("Unsupported OTA rollback state; do not override it")
            result.append(BootEntry(sector, seq, state))
    return result


def selected_slot(raw):
    entries = boot_entries(raw)
    return (max(entries, key=lambda x: x.seq).seq - 1) % 2 if entries else None


def plan_selection(raw, network):
    """Return ONE inactive OTA sector to write, retaining the other recovery copy."""
    if network not in NETWORKS:
        raise LabError("Unknown target firmware")
    entries = boot_entries(raw)
    if not entries:
        raise LabError("No valid OTA selection. Establish a manual baseline first")
    base = max(entries, key=lambda x: x.seq)
    if len(entries) == 2 and entries[0].seq == entries[1].seq:
        raise LabError("Ambiguous equal OTA sequences")
    target = NETWORKS[network]
    if (base.seq - 1) % 2 == target:
        return None
    seq = base.seq + 1
    if (seq - 1) % 2 != target:
        seq += 1
    if seq >= 0xFFFFFFFF:
        raise LabError("OTA sequence rollover requires separate recovery")
    updated = bytearray(b"\xff" * SECTOR)
    struct.pack_into("<I", updated, 0, seq)
    # Match ESP-IDF without rollback: erased/UNDEFINED state, not an assertion
    # that this image has passed an application self-test (ESP_OTA_IMG_VALID).
    struct.pack_into("<I", updated, 24, 0xFFFFFFFF)
    struct.pack_into("<I", updated, 28, binascii.crc32(updated[:4], 0xFFFFFFFF) & 0xFFFFFFFF)
    return 1 - base.sector, bytes(updated)
