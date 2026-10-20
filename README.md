<div align="center">

# Mesh Chat

**One radio. Two networks. One Home Assistant interface.**

![Status: Requirements gathering](https://img.shields.io/badge/status-requirements_gathering-64748b?style=flat-square)
![Hardware: Heltec V4](https://img.shields.io/badge/hardware-Heltec_V4-0891b2?style=flat-square)
![Platform: Home Assistant](https://img.shields.io/badge/platform-Home_Assistant-18bcf2?style=flat-square)

</div>

> **Requirements gathering.** We are defining features, behaviour and interface requirements. This repository contains documentation only; implementation and hardware validation have not started.

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

- **Only hardware target:** Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB flash, with an 868 MHz antenna and USB-C data cable. Other boards and variants, including V4-R8, are outside the current development and test scope.
- **Device replacement:** restore to another unit of this same model and variant; cross-model migration is outside scope.
- **Headless operation:** intended to work without a display; still to be validated.
- **First environment:** Home Assistant OS on Proxmox with USB passthrough.

Planned distribution: **HACS**, with configuration in the HA UI. Each household uses its own radio and profiles; no fixed entity IDs, USB paths or server addresses.

## Before a release

Verify each firmware independently, then switching in both directions. Confirm identity, settings and complete recorded chat history survive repeated switches, HA restarts and power cycles. Test recovery from failed switches, complete restoration to a second Heltec V4 of the same variant, and installation on a second home system. Provide reproducible builds and backup/recovery instructions.

## Foundations

- [MeshCore HA](https://github.com/meshcore-dev/meshcore-ha) · [MeshCore chat cards](https://github.com/RikoDEV/ha-meshcore-cards) · [Meshtastic HA](https://github.com/meshtastic/home-assistant)
- [Heltec V4 dualboot reference](https://github.com/tkh1000/Meshtastic-Meshcore-Dualboot-Heltec-V4-) — supplied MeshCore image uses Bluetooth; remote USB switching is not established by this reference.
- [Hardware specifications](https://heltec.org/project/wifi-lora-32-v4/)

*Independent community project; not affiliated with Home Assistant, MeshCore, Meshtastic or Heltec.*
