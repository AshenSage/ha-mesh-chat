<div align="center">

# Mesh Chat

**MeshCore & Meshtastic, together in Home Assistant.**

![Status: Planning](https://img.shields.io/badge/status-planning-64748b?style=flat-square)
![Hardware: Heltec V4](https://img.shields.io/badge/hardware-Heltec_V4-0891b2?style=flat-square)
![Platform: Home Assistant](https://img.shields.io/badge/platform-Home_Assistant-18bcf2?style=flat-square)

A shared chat interface with a firmware selector for one USB-connected LoRa radio.

</div>

> **Documentation only.** No installable release yet. Remote firmware switching and hardware compatibility still require implementation and testing.

## The idea

Choose **MeshCore** or **Meshtastic** at the top of the chat. The radio restarts into the selected firmware, reconnects, and opens the corresponding conversations.

Both firmware images would remain on the device. Only the active network can send and receive; traffic on the inactive network is missed.

## Planned features

| Feature | Goal |
| --- | --- |
| Chat | Channels, direct messages, timestamps and delivery status where available |
| Network selector | Switch firmware from Home Assistant without reflashing each time |
| Connection status | Show the confirmed active network, switching progress and errors |
| History | Keep each network's conversations separate |
| Mobile layout | Comfortable use in the Home Assistant app |

## Intended hardware

- **Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB flash.** V4-R8 is a different variant and is outside the initial target.
- **868 MHz antenna and compatible radio settings** for the initial European setup.
- **USB-C data cable** and USB access from Home Assistant.
- Display-free operation is a design goal; the headless dualboot setup needs validation.

The first test environment will be **Home Assistant OS on Proxmox**, using USB passthrough.

## Reuse on another home system

The goal is installation through **HACS**, followed by setup in the Home Assistant UI. Each household would select its own radio and network settings, with no fixed entity IDs, USB paths or server addresses in the code.

Reproducible firmware builds, backup/recovery instructions and a tested hardware list are required before sharing an installable release.

## Roadmap

1. Verify the board, USB communication and each firmware independently.
2. Validate headless dualboot, preserved settings and switching in both directions.
3. Add the Home Assistant selector and integrate the existing chat backends.
4. Test reconnection, failed switches and installation on a second home system.

## Foundations

Build on existing projects rather than replace their radio stacks:

- [MeshCore for Home Assistant](https://github.com/meshcore-dev/meshcore-ha) · [MeshCore chat cards](https://github.com/RikoDEV/ha-meshcore-cards)
- [Meshtastic for Home Assistant](https://github.com/meshtastic/home-assistant)
- [Heltec V4 dualboot reference](https://github.com/tkh1000/Meshtastic-Meshcore-Dualboot-Heltec-V4-) — its supplied MeshCore image uses Bluetooth; USB switching is not established by this reference.
- [Heltec hardware specifications](https://heltec.org/project/wifi-lora-32-v4/)

*Independent community project; not affiliated with Home Assistant, MeshCore, Meshtastic or Heltec.*
