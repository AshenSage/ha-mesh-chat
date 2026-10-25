# Mesh Chat Dualboot Lab

An experimental Home Assistant OS app for proving USB-controlled MeshCore ↔ Meshtastic dualboot on one Heltec V4 (ESP32-S3R2, 16 MB, 868 MHz).

Inspect, back up, capture protocol/profile baselines, request a switch, and run bounded round trips with a persistent JSON report. No chat, schedules or automatic firmware installation. Boot-selection writes are disabled by default.

Read [DOCS.md](DOCS.md) before attaching hardware. No hardware stability claim has been established. Supported architecture targets are amd64 and aarch64; actual HAOS installation on both still needs validation.
