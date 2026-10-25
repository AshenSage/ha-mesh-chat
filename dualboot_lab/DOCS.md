# Dualboot Lab: installation and first test

This is an experimental bench tool. The first goal is reproducible **USB switching from HA**, in both directions, without touching buttons during ordinary switches. Buttons during initial flashing/recovery are allowed and must be recorded. The lab does not send chat messages or provide message recovery. Keep the reference radio out of production use during these tests.

## 1. Install the HAOS app

1. HA Settings → Apps/Add-ons → Store → menu → Repositories: add `https://github.com/AshenSage/ha-mesh-chat`.
2. Refresh, install **Mesh Chat Dualboot Lab** and leave automatic startup off.
3. On Proxmox, pass through the Heltec USB device to the HAOS VM. Check that passthrough also survives bootloader/runtime USB re-enumeration; a physical USB-port mapping may be necessary. On Raspberry Pi, use direct USB.
4. Select the exact serial path in HA Settings → System → Hardware → All hardware. Prefer `/dev/serial/by-id/...`; the app also uses a uniquely matching physical USB location after re-enumeration. It never selects an arbitrary available port.
5. Configure `device` with that path. Leave `allow_boot_selection_write: false`. Confirm `board_confirmed: true` only after inspecting the physical model/variant, flash and radio band (Heltec V4 **ESP32-S3R2 / 16 MB / 868 MHz**, not R8).
6. Stop other integrations, serial terminals and apps using this port. Start the lab and open its web UI in HA. It is admin-only Ingress; no public/listening host port or HA token is required.

Example app options (replace the device path):

```yaml
device: /dev/serial/by-id/REPLACE_WITH_YOUR_DEVICE
board_confirmed: true
allow_boot_selection_write: false
```

The first read-only inspection reports esptool `get_psram_cap()` and chip features. Cap 2 means embedded PSRAM 2 MB in the pinned API; all other/unknown values block writes. Whether the actual Heltec V4-R2 reports cap 2 is NOT RUN and must be checked before relying on the candidate label. A checkbox is not chip evidence.

Run **USB und Layout prüfen**. This enters ROM/stub mode, reads the chip, JEDEC flash size, partition table and boot metadata, then resets the radio. It interrupts reception even though it does not write flash. A fresh/single-firmware board is expected to report an unsupported layout. No installation or erase happens automatically.

**Current A2 blocker:** the previously compiled MeshCore app and reference Meshtastic app both report `arduino-lib-builder` in their ESP application descriptor. The strict slot guard rejects these generic names. A build with an explicit protocol project name is required for each slot before lab writes; old successful compilation is not evidence of correct slot identity.

## 2. Prepare firmware once, before the lab switching test

**This prerequisite is not yet a validated turnkey bundle.** The app currently switches an explicitly prepared installation; it does not flash new boards. Stop at preflight if the build/provisioning checks below cannot be completed. Do not download arbitrary latest images.

Reference reviewed: `tkh1000/Meshtastic-Meshcore-Dualboot-Heltec-V4-` at commit `b889b895a9ef96a07c217cbc02460cf8e64b0739`.

- Its **root** table has isolated `spiffs` and `mc_spiffs` and matches this lab's allowlist. Its `selector/partitions_dualboot.csv` has a different layout and is rejected. The checked prebuilt table matches the root layout.
- Its MeshCore image is **BLE companion**. USB power does not make it a USB companion. Replace only that app image with a prepared USB companion build before the runtime verification test.
- Its custom bootloader/selector binaries lack a complete matching build provenance in that checkout. Treat them as experimental external inputs, not a project-certified bundle. They are not redistributed here.

Prepare the MeshCore source on a development computer (or use the manually triggered GitHub workflow **Build experimental MeshCore USB app**):

```sh
python -m pip install platformio==6.1.18 esptool==4.11.0
git clone https://github.com/meshcore-dev/MeshCore.git firmware-work/MeshCore
git -C firmware-work/MeshCore checkout 81dbae592ffad40b4212bc0b37e82b38da08f4bc
python tools/prepare_meshcore_usb.py firmware-work/MeshCore --build
```

The script requires a clean pinned checkout, patches the SPIFFS mount to `mc_spiffs`, applies the lab partition table to `heltec_v4_companion_radio_usb`, omits the OLED UI and optional external sensor/GPS support for this bench proof, and records the resulting binary hash. It never flashes a device. A local build has succeeded; complete bundle compatibility and headless runtime operation still require hardware evidence. See [software evidence](../docs/software-evidence.md). The source commit is fixed, but upstream transitive PlatformIO libraries are not fully locked yet; archive the actual build log and binary hashes used for each hardware test.

For a first bench installation, use the reference checkout at the pinned commit above, its prebuilt bootloader/table/OTA/selector and Meshtastic app, and the generated `meshcore-usb-lab.bin` instead of its BLE app. Before any first installation:

1. Confirm the exact board and 16 MB flash with esptool, and connect the matching antenna.
2. Read and preserve the **entire original 16 MB flash** with esptool `read_flash 0 0x1000000 ORIGINAL-BACKUP.bin`. Check the file size and record SHA-256. This is separate from the lab's later prepared-board snapshot. Never publish raw backups; they may contain private identities and channel keys.
3. Stop the HA lab while using external esptool. Validate the supplied binary partition table with `tools/check_lab_table.py` before writing it. A CSV alone is insufficient.
4. Only then explicitly flash the six components at these offsets. Use esptool 4.11.0, `--chip esp32s3`, the exact selected `--port`, `write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB`. Do not erase the whole flash or reuse an important standalone profile expecting automatic migration.

| Offset | Experimental component |
| --- | --- |
| `0x0000` | Reference `prebuilt/bootloader.bin` |
| `0x8000` | Verified reference `prebuilt/partition-table.bin` |
| `0x1C000` | Reference `prebuilt/ota_data_initial.bin` |
| `0x20000` | Reference `prebuilt/selector.bin` |
| `0x220000` | Our prepared `meshcore-usb-lab.bin` |
| `0x680000` | Reference `meshtastic/firmware.bin` |

Record all component SHA-256 hashes. First select and boot one firmware using the reference selector if needed. Finish its initial profile setup. Manually select and finish setup of BOTH profiles before enrolment; never rely on a first lab switch to create the second identity. Do not apply OTA updates or change profiles during a measured round-trip run. The lab is allowed to fail here: USB runtime/control incompatibility is a result to diagnose, not a reason to weaken verification.

## 3. Enrol and run individual switches

1. First finish both firmware profiles manually as described above. Start the lab, run preflight, then **Testgerät registrieren + sichern**. The exact layout is required. The app reads a complete 16 MB prepared-board snapshot, checks the stored hash and binds its registry to the factory MAC, table and app hashes. Raw flash stays in private `/data` and is included in cold app backups. There is no raw-backup download endpoint.
2. Select the currently running firmware and **Ausgangszustand … erfassen**. A real USB response is required. MeshCore uses `SELF_INFO`; Meshtastic uses completed USB configuration, own node and metadata.
3. Stop the app, enable `allow_boot_selection_write: true`, start it again. Choose the other firmware and **wechseln**. This is an explicit experimental lab action.
4. The first lab visit to the already configured other firmware records its baseline and is labelled `first_boot_baseline`; it cannot prove historical profile preservation yet. Return to the original firmware, then back again. Later visits must match the stored identity and selected settings.

After both baselines have been recorded, run the read-only `resnapshot` command to capture both configured profiles. Every round-test start automatically resnapshots before any switch; a snapshot failure stops the run. Earlier recovery points are retained.

A switch checks the existing snapshot and actual chip/layout/app fingerprints, checks the current runtime/profile, writes **one inactive 4 KB OTA selection sector**, reads it back while retaining the other valid copy, resets and checks the target protocol twice. Firmware application images, NVS and both profile filesystem partitions are not rewritten by the controller. The firmwares themselves can still write their own settings; persistence must be tested.

The controller does not press GPIO buttons, invoke the OLED selector, erase profiles or flash apps during switching. Its experimental method is a USB ROM/stub boot-selection update, not a firmware-native switch API. USB re-enumeration and reset/bootloader behaviour are precisely what the hardware test must establish.

## 4. Run the proof

Start with **3 complete rounds**. Once these pass, run **20 complete rounds** on each host. A round is A→B→A; a no-op never counts. The runner stops on the first error and never silently resumes a job after a restart. There is no automatic rollback, reflash or repeated reboot loop. A timeout or interrupted write leaves the running state unknown until checked again.

Use [the full acceptance plan](../docs/dualboot-proof.md), including restart, power-loss and dwell tests. Download the JSON report and attach the host/build details. These reports contain names and device identifiers but no private keys, channel keys or raw protocol dumps.

Automated profile comparison currently covers public identity plus name and selected radio configuration, **not every channel/contact/key or private-key export**. Check the remaining profile data separately before marking full persistence passed. No geographic radio coverage, chat delivery or message-buffer claim follows from a dualboot pass.

## Recovery and troubleshooting

- **Port missing/ambiguous:** stop, check the HA hardware list and Proxmox passthrough for both ROM and runtime modes. Do not guess another port. If native USB descriptors change, use a stable physical mapping.
- **No protocol response:** unknown running firmware; check the USB companion build and port ownership. A BLE-only MeshCore build does not pass. Inspect before trying another switch.
- **Profile/layout/build changed:** the lab refuses further switching. Preserve reports/backups, understand the change, and archive the app data before enrolling a deliberate new test setup. It never silently replaces a baseline.
- **Interrupted selection:** the untouched OTA copy is the first recovery mechanism. Inspect the actual board. If no app starts, ROM download mode may require PRG/RST and an explicit esptool recovery. Record any button use and fail the affected hands-off test.
- **Full restore:** retain the original complete flash dump and the exact component versions. A full-flash restore is an explicit, potentially destructive external recovery operation; this version does not offer a one-click restore. It is not the later complete replacement workflow.
- **Restarted app:** prior running jobs become `interrupted`; they do not continue automatically. Inspect, verify the active firmware, then start a new test.

## Local software checks

```sh
python -m pip install -r dualboot_lab/requirements.txt pytest==8.4.2
python -m pytest -q
```

For local UI development set `LAB_LOCAL=1`, `LAB_DATA` to a private test directory containing `options.json`, and run `PYTHONPATH=dualboot_lab python -m lab.server`. This binds to loopback only. Never expose the local development server to a network.
