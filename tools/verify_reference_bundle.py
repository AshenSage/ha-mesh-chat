#!/usr/bin/env python3
"""Offline allowlist and bootloader READBACK-file checker. Never opens a device."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

MANIFEST = Path(__file__).resolve().parents[1] / "firmware/reference-sha256.json"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bootloader_after_header_options(image):
    from esptool.cmds import _update_image_flash_params
    from esptool.targets.esp32s3 import ESP32S3ROM
    args = SimpleNamespace(chip="esp32s3", flash_mode="dio", flash_freq="80m", flash_size="16MB")
    with contextlib.redirect_stdout(io.StringIO()):
        return _update_image_flash_params(ESP32S3ROM, 0, args, image)


def verify(root, manifest, readback=None):
    checked = {}
    for name, expected in manifest["files"].items():
        data = (root / name).read_bytes()
        if len(data) != expected["size"] or sha(data) != expected["sha256"]:
            raise ValueError(f"Reference binary is missing, modified or not allowlisted: {name}")
        checked[name] = expected["sha256"]
    result = {"reference_commit": manifest["commit"], "source_sha256": checked,
              "hardware_validated": False, "bootloader_readback_verified": False}
    if readback is not None:
        source = (root / "prebuilt/bootloader.bin").read_bytes()
        expected = bootloader_after_header_options(source)
        actual = readback.read_bytes()
        if actual != expected:
            raise ValueError("Bootloader readback differs from the exact header-adjusted reference")
        result.update(bootloader_readback_verified=True, bootloader_readback_sha256=sha(actual),
                      bootloader_source_sha256=sha(source), source_header=source[:4].hex(),
                      written_header=actual[:4].hex(), bootloader_readback_size=len(actual))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--bootloader-readback", type=Path)
    args = parser.parse_args()
    result = verify(args.reference, json.loads(MANIFEST.read_text()), args.bootloader_readback)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
