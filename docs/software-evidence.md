# Dualboot lab software evidence

Recorded 2026-10-25. **No physical radio or Home Assistant instance was changed. Hardware acceptance is still NOT RUN.**

| Check | Observed result |
| --- | --- |
| Local tests, Python 3.12 | 14 passed, including OTA sector boundaries, interruption/failure guards, HTTP access and simulated USB protocol responses |
| Python compilation | `dualboot_lab/lab` and `tools` compile successfully |
| HAOS app container targets | GitHub Actions builds succeeded for `linux/amd64` and `linux/arm64`; this is not actual HAOS installation evidence |
| Reference binary partition table | Matches strict isolated layout, with valid MD5 |
| Generated MeshCore binary partition table | Matches the same strict isolated layout, with valid MD5 |
| MeshCore USB app compilation | Succeeded locally with PlatformIO 6.1.18, pinned source and the headless lab patches |

MeshCore source: `81dbae592ffad40b4212bc0b37e82b38da08f4bc`, environment `heltec_v4_companion_radio_usb`.

- Patches: isolated `mc_spiffs`, lab table, USB companion, OLED UI omitted, optional external sensors/GPS omitted.
- App image size: **558352 bytes**, within the `ota_0` partition.
- Observed app SHA-256: `618595e4f69e3febf84bfdb32c71869168a33394202d443961e304f4352577eb`.
- Binary table SHA-256, padded to 4096 bytes: `82166a8602bdbe75c93f4cfcac5eac5f78f5e295891ab117987d758a1b3b6579`.
- PlatformIO platform: espressif32 6.11.0; Arduino ESP32 framework 3.20017.241212; Xtensa ESP32-S3 toolchain 8.4.0+2021r2-patch5.
- Resolved libraries included RadioLib commit `6d8934836678d8894e3d556550475b37dce3e2b6`, Crypto 0.4.0, RTClib 2.1.4, Melopero RV3028 1.2.0, CayenneLPP 1.6.1, ArduinoJson 7.4.3 and base64 1.4.0.

This is an observed build hash, not a promise of byte-identical future rebuilds. Upstream transitive dependencies and build timestamps are not fully locked. Archive the actual binary hashes for each board test.

The first attempt with the upstream OLED UI failed due to an undeclared Adafruit GFX dependency. The final lab image removes that UI and successfully compiles as a headless USB companion. The source-only builder now prepares that tested configuration.

Still unproven: initial bundle provisioning, the external custom bootloader's USB/reset behaviour, both runtime protocols on the physical board, hands-off switching in both directions, complete profile retention, host installation/re-enumeration and recovery. See the [hardware acceptance matrix](dualboot-proof.md).
