<div align="center">

# Mesh Chat

**One radio. Two networks. One Home Assistant interface.**

![Status: Dualboot proof](https://img.shields.io/badge/status-experimental_dualboot_proof-d69e36?style=flat-square)
![Hardware: Heltec V4](https://img.shields.io/badge/hardware-Heltec_V4-0891b2?style=flat-square)
![Platform: Home Assistant](https://img.shields.io/badge/platform-Home_Assistant-18bcf2?style=flat-square)

</div>

> **Current focus: prove USB dualboot in Home Assistant.** An experimental HAOS app (add-on) and software tests are now included. Hardware stability is **not yet validated**. The full chat product is deferred until this foundation is reproducible.

> **Post-review readiness:** generic `arduino-lib-builder` descriptors now require both manually booted USB runtime baselines, bound to unchanged slot/app hashes. No switch creates a new baseline. The manual bootloader/OTA hypothesis, actual R2 cap observation, filesystem power-cut durability and HAOS access/USB checks are still NOT RUN. The independent software review is complete (2026-10-26, no remaining P1/P2). Hardware gates remain open: **not cleared for lab switches or unattended rounds**. See the [per-point fix/test record](docs/review-fixes.md).

## Start here: Dualboot Lab

The core of this repository is now the [Dualboot Lab](dualboot_lab/DOCS.md):

1. Inspect the Heltec V4's chip, 16 MB flash and actual partition table over USB.
2. Enrol the prepared dualboot board and save a complete private flash backup.
3. Manually boot both configured firmwares and capture both real USB profile baselines and slot attestations.
4. Request MeshCore → Meshtastic and Meshtastic → MeshCore from HA. Only boot-selection metadata is written; firmware apps and profile partitions are not reflashed during a switch.
5. Reconnect, check the target protocol twice and compare identity/selected settings with its baseline.
6. Run bounded round-trip tests and export a JSON report. Stop on the first failure; never silently retry or resume after a restart.

**Success gate:** ordinary switching must work from HA without touching the board, with repeatable results, preserved profiles, restart/reconnect handling and evidence on both target hosts. Initial provisioning or recovery may use buttons; needing a button during an ordinary switch fails the gate. See the [test plan and evidence template](docs/dualboot-proof.md).

Add this repository URL in the HA app/add-on store, then install **Mesh Chat Dualboot Lab**. It is an experimental Supervisor app, **not a HACS integration**. Start manually; write access is off by default. See [installation and firmware preparation](dualboot_lab/DOCS.md).

**Not turnkey firmware yet:** the upstream reference bundles MeshCore BLE, not the USB companion needed for runtime verification. It also contains conflicting source partition tables. A pinned [USB build preparation script](tools/prepare_meshcore_usb.py) and manually triggered build workflow are provided. Initial flashing remains a separate, explicit lab procedure. No tested firmware bundle is being advertised or automatically downloaded.

## Later product scope

Everything below describes the agreed later product, not features delivered by the lab. Chat, history/outbox, notifications, schedules, comparison reports, guided provisioning and complete replacement recovery remain deferred until the dualboot gate passes.

## How it should work

1. Connect a supported radio. A guided installer downloads and flashes a tested dual-firmware bundle, then helps configure both profiles once.
2. Select **MeshCore** or **Meshtastic** in Home Assistant. The radio restarts into the selected firmware.
3. Each firmware keeps its own profile. Later switches retain the existing identity, settings and conversations without repeating setup or reflashing.
4. Home Assistant confirms the active firmware and reconnects the matching chat backend.

Only the active network can send and receive. Messages transmitted while a network is inactive are not guaranteed to arrive later.

## Data that must survive

| Stored by | Required data |
| --- | --- |
| Radio, separately for each firmware | Identity keys and node ID/hash, display name, radio settings, channels and keys, plus contacts or peer data supported by that firmware |
| Home Assistant, separately for each network and radio identity | Recorded channel messages and private DMs, sent and received, with timestamps and available delivery status |

A display name is not the cryptographic identity. Switching must preserve both, never regenerate keys, and never format the other firmware's data.

**Chat history must persist in Home Assistant**, beyond browser sessions, radio restarts and HA restarts. Preserving radio settings alone is insufficient. Importing history from existing phone apps is a separate, unconfirmed capability.

## One chat experience

Use the same layout for both networks: channels, private DMs, message history, composer and firmware selector. Keep conversations separate when switching, but restore them when returning.

Browse either network's saved chats without switching the radio; mark the confirmed active network. For an inactive network, offer an outbox or an explicit switch-and-send action.

Expose network-specific features only where supported. Include a mobile layout, switching progress and clear connection errors. See the [accepted feature requirements](docs/requirements.md) for contacts, notifications, trends, onboarding and complete backup/recovery.

## Automatic switching and comparison

A planned feature alongside manual switching: configurable schedules, timers and an optional comparison mode. The UI should show the active network, next switch and a manual override.

Comparison mode must balance observation times, retain both profiles and histories, and distinguish network activity from confirmed communication success. See [automatic switching requirements](docs/automatic-switching.md).

## Target and installation

- **Only radio hardware target:** Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB flash, with an 868 MHz antenna and USB-C data cable. Other boards and variants, including V4-R8, are outside the current development and test scope.
- **Device replacement:** restore to another unit of this same model and variant; cross-model migration is outside scope.
- **Headless operation:** intended to work without a display; still to be validated.
- **Required host platforms:** Home Assistant OS in a Proxmox VM (amd64, USB passthrough) and directly on Raspberry Pi (aarch64, direct USB). Both must support the full feature set, including flashing and recovery.

Later product distribution: **HACS**, with configuration in the HA UI; a companion app may be needed. The current lab is installed through the Supervisor app store. Each household uses its own radio and profiles; no fixed entity IDs, USB paths or server addresses.

## Before a release

[Planning and open decisions](docs/planning.md) tracks pending product choices and prerequisite hardware checks.

Verify each firmware independently, then switching in both directions. Confirm identity, settings and complete recorded chat history survive repeated switches, HA restarts and power cycles. Test recovery from failed switches, complete restoration to a second Heltec V4 of the same variant, and installation on a second home system. Run the full acceptance flow on both Proxmox/HAOS and Raspberry Pi/HAOS. Provide reproducible builds and backup/recovery instructions.

## Foundations

- [MeshCore HA](https://github.com/meshcore-dev/meshcore-ha) · [MeshCore chat cards](https://github.com/RikoDEV/ha-meshcore-cards) · [Meshtastic HA](https://github.com/meshtastic/home-assistant)
- [Heltec V4 dualboot reference](https://github.com/tkh1000/Meshtastic-Meshcore-Dualboot-Heltec-V4-) — supplied MeshCore image uses Bluetooth; remote USB switching is not established by this reference.
- [Hardware specifications](https://heltec.org/project/wifi-lora-32-v4/)

*Independent community project; not affiliated with Home Assistant, MeshCore, Meshtastic or Heltec.*
