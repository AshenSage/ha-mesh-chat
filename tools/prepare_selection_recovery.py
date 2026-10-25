#!/usr/bin/env python3
"""Prepare a recovery candidate from PRIVATE FILES only. Never opens USB or writes flash.

A pending journal means a write MAY HAVE BEGUN; it does not mean no flash write
occurred. Determine the actual state independently before any manual recovery.
"""
import argparse
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dualboot_lab"))
from lab.layout import NETWORKS, OTA_OFFSET, OTA_SIZE, SECTOR, LabError, digest, plan_selection, selected_slot
from lab.worker import private_open, save_json


def prepare(journal, current, expected_mac, output):
    if journal.get("mac") != expected_mac or journal.get("status") not in ("pending", "written", "verified"):
        raise LabError("Journal MAC/status does not match the operator's trusted record")
    caution = {"journal_status": journal["status"],
               "journal_caution": "pending means a write may have begun; verify actual device state independently"}
    previous = bytes.fromhex(journal["otadata_hex"])
    if len(previous) != OTA_SIZE or len(current) != OTA_SIZE:
        raise LabError("Both OTA files must have the exact partition length")
    slot = selected_slot(previous)
    if slot is None:
        raise LabError("Journal has no valid previous selection")
    target = next(name for name, number in NETWORKS.items() if number == slot)
    candidate = plan_selection(current, target)
    if candidate is None:
        return {"status": "already_selected", "hardware_validated": False, **caution}
    sector, content = candidate
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = output / "recovery-sector.bin"
    with private_open(path, binary=True) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    result = {"status": "manual_candidate_not_executed", "target": target, "mac": expected_mac,
              "offset": OTA_OFFSET + sector * SECTOR, "size": len(content), "sha256": digest(content),
              "source_current_sha256": digest(current), "hardware_validated": False, **caution}
    save_json(output / "recovery-plan.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path)
    parser.add_argument("current_otadata", type=Path, help="Fresh manual readback; not assumed current by this tool")
    parser.add_argument("--expect-mac", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(json.loads(args.journal.read_text()), args.current_otadata.read_bytes(),
                             args.expect_mac, args.output), indent=2))


if __name__ == "__main__":
    main()
