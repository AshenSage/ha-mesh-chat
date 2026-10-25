#!/usr/bin/env python3
"""Validate a binary partition table before an explicit lab installation."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dualboot_lab"))
from lab.layout import SECTOR, validate_table


if __name__ == "__main__":
    raw = Path(sys.argv[1]).read_bytes()
    if len(raw) not in (0xC00, SECTOR):
        raise SystemExit("Expected a 3072- or 4096-byte binary partition table")
    print("Supported lab layout. SHA256 (4 KB padded):", validate_table(raw.ljust(SECTOR, b"\xff")))
