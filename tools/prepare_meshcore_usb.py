#!/usr/bin/env python3
"""Prepare a pinned upstream checkout for the experimental USB lab build.

Never flashes hardware. Refuses unknown/dirty source. The local changes and
source/build metadata are deliberate; compilation is not hardware validation.
"""

import argparse
import hashlib
import importlib.metadata
import re
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

MESHCORE_REF = "81dbae592ffad40b4212bc0b37e82b38da08f4bc"
ENVIRONMENT = "heltec_v4_companion_radio_usb"


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "firmware/meshcore-usb-lab.patch"
FILES = ROOT / "firmware/meshcore-source-files.json"
AUDIT = ROOT / "firmware/meshcore-filesystem-allowlist.json"
FS_CALL = re.compile(r"(?:SPIFFS|LittleFS)\s*\.\s*begin\s*\(|\.\s*format\s*\(")


def audit_filesystems(source):
    allowed = {(r["path"], r["text"]) for r in json.loads(AUDIT.read_text())}
    names = subprocess.check_output(["git", "ls-files"], cwd=source, text=True).splitlines()
    for name in names:
        if Path(name).suffix.lower() not in (".cpp", ".h", ".c", ".ino"):
            continue
        for line in (source / name).read_text().splitlines():
            if FS_CALL.search(line) and (name, line.strip()) not in allowed:
                raise SystemExit(f"Unreviewed filesystem call in {name}; refusing all source changes")


def prepare(source, reset=False):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if head != MESHCORE_REF:
        raise SystemExit(f"Expected MeshCore commit {MESHCORE_REF}, found {head}")
    files = json.loads(FILES.read_text())
    original = prepared = True
    for name, expected in files.items():
        path = source / name
        value = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        original &= value == expected["original"]
        prepared &= value == expected["prepared"]
    if not original and not prepared:
        raise SystemExit("Unsupported/partially modified source or section layout; no files changed")
    changed = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=source, text=True).splitlines()
    untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=source, text=True).splitlines()
    if set(changed + untracked) - set(files):
        raise SystemExit("Unrelated local changes; preserve them in a different checkout")
    audit_filesystems(source)
    if prepared and not reset:
        return  # already exactly our prepared state; idempotent
    if original and reset:
        return
    command = ["git", "apply"] + (["--reverse"] if reset else [])
    checked = subprocess.run(command + ["--check", str(PATCH)], cwd=source, capture_output=True)
    if checked.returncode:
        raise SystemExit("Versioned patch does not apply atomically; no files changed")
    subprocess.run(command + [str(PATCH)], cwd=source, check=True)
    audit_filesystems(source)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--reset", action="store_true", help="Reverse only the exact known lab patch")
    parser.add_argument("--output", type=Path, default=Path("firmware-work/output"))
    args = parser.parse_args()
    source = args.source.resolve()
    if args.reset and args.build:
        parser.error("--reset and --build are mutually exclusive")
    prepare(source, reset=args.reset)
    if args.reset:
        return
    if args.build:
        args.output.mkdir(parents=True, exist_ok=True)
        log = args.output / "meshcore-build.log"
        started = datetime.now(timezone.utc).isoformat()
        with log.open("wb") as stream:
            result = subprocess.run([sys.executable, "-m", "platformio", "run", "-e", ENVIRONMENT],
                                    cwd=source, stdout=stream, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit(f"Build failed; inspect {log}")
        binary = source / ".pio/build" / ENVIRONMENT / "firmware.bin"
        image = binary.read_bytes()
        if not image or len(image) > 0x460000 or image[0] != 0xE9 or b"mc_spiffs\0" not in image:
            raise SystemExit("Unexpected or oversized app image")
        args.output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(binary, args.output / "meshcore-usb-lab.bin")
        for license_path in source.iterdir():
            if not license_path.is_file() or not license_path.name.lower().startswith(("license", "licence")):
                continue
            shutil.copyfile(license_path, args.output / ("MeshCore-" + license_path.name))
        metadata = {"source": "https://github.com/meshcore-dev/MeshCore", "commit": MESHCORE_REF,
                    "environment": ENVIRONMENT, "platformio_version": importlib.metadata.version("platformio"),
                    "platform": "platformio/espressif32@6.11.0", "build_started_utc": started,
                    "build_finished_utc": datetime.now(timezone.utc).isoformat(),
                    "build_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "sha256": hashlib.sha256(image).hexdigest(),
                    "size": len(image), "flash_offset": "0x220000", "hardware_validated": False,
                    "patches": ["isolated mc_spiffs mount", "lab partition table", "USB companion",
                                "headless: OLED UI omitted", "external sensors/GPS omitted for bench proof"]}
        (args.output / "meshcore-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Prepared experimental USB source. Hardware validation remains pending.")


if __name__ == "__main__":
    main()
