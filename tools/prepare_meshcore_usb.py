#!/usr/bin/env python3
"""Prepare a pinned upstream checkout for the experimental USB lab build.

Never flashes hardware. Refuses unknown/dirty source. The local changes and
source/build metadata are deliberate; compilation is not hardware validation.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

MESHCORE_REF = "81dbae592ffad40b4212bc0b37e82b38da08f4bc"
ENVIRONMENT = "heltec_v4_companion_radio_usb"


def prepare(source):
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
    if head != MESHCORE_REF:
        raise SystemExit(f"Expected MeshCore commit {MESHCORE_REF}, found {head}")
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True).strip():
        raise SystemExit("Use a clean MeshCore checkout; do not patch a working installation")
    main = source / "examples/companion_radio/main.cpp"
    text = main.read_text()
    if text.count("SPIFFS.begin(true);") != 1:
        raise SystemExit("SPIFFS mount changed; review isolation before building")
    ini = source / "variants/heltec_v4/platformio.ini"
    content = ini.read_text()
    section = f"[env:{ENVIRONMENT}]\n"
    if content.count(section) != 1:
        raise SystemExit("USB build environment changed")
    # This bench proof does not use external environmental sensors or GPS.
    for optional in ("  ${sensor_base.build_flags}\n", "  ${sensor_base.lib_deps}\n", "  -D ENV_INCLUDE_GPS=1\n"):
        if content.count(optional) != 1:
            raise SystemExit("Optional sensor configuration changed; review the lab build")
        content = content.replace(optional, "")
    prefix, usb_tail = content.split(section)
    usb_block, following = usb_tail.split("\n[", 1)
    # Build a headless image: no OLED UI or its display libraries in this
    # lab image. Preserve the board pin definitions inherited from oled base.
    for optional in ("  -I examples/companion_radio/ui-new\n", "  -D DISPLAY_CLASS=SSD1306Display\n",
                     "  +<helpers/ui/SSD1306Display.cpp>\n", "  +<helpers/ui/MomentaryButton.cpp>\n",
                     "  +<../examples/companion_radio/ui-new/*.cpp>\n"):
        if usb_block.count(optional) != 1:
            raise SystemExit("USB display configuration changed; review the headless lab build")
        usb_block = usb_block.replace(optional, "")
    content = prefix + section + usb_block + "\n[" + following
    main.write_text(text.replace("SPIFFS.begin(true);", 'SPIFFS.begin(true, "/spiffs", 10, "mc_spiffs");'))
    content = content.replace(section, section + "board_build.partitions = partitions_mesh_chat_lab.csv\n"
                              "board_upload.maximum_size = 4587520\n")
    ini.write_text(content)
    table = Path(__file__).resolve().parents[1] / "firmware/partitions_lab.csv"
    shutil.copyfile(table, source / "partitions_mesh_chat_lab.csv")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("firmware-work/output"))
    args = parser.parse_args()
    source = args.source.resolve()
    prepare(source)
    if args.build:
        subprocess.run([sys.executable, "-m", "platformio", "run", "-e", ENVIRONMENT], cwd=source, check=True)
        binary = source / ".pio/build" / ENVIRONMENT / "firmware.bin"
        image = binary.read_bytes()
        if not image or len(image) > 0x460000 or image[0] != 0xE9:
            raise SystemExit("Unexpected or oversized app image")
        args.output.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(binary, args.output / "meshcore-usb-lab.bin")
        for license_path in source.iterdir():
            if not license_path.is_file() or not license_path.name.lower().startswith(("license", "licence")):
                continue
            shutil.copyfile(license_path, args.output / ("MeshCore-" + license_path.name))
        metadata = {"source": "https://github.com/meshcore-dev/MeshCore", "commit": MESHCORE_REF,
                    "environment": ENVIRONMENT, "sha256": hashlib.sha256(image).hexdigest(),
                    "size": len(image), "flash_offset": "0x220000", "hardware_validated": False,
                    "patches": ["isolated mc_spiffs mount", "lab partition table", "USB companion",
                                "headless: OLED UI omitted", "external sensors/GPS omitted for bench proof"]}
        (args.output / "meshcore-build.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Prepared experimental USB source. Hardware validation remains pending.")


if __name__ == "__main__":
    main()
