# B4 — reset and filesystem durability investigation

**Software/source inspection only. Hardware results: NOT RUN.** Existing ROM entry resets the running application and may interrupt a profile write. SPIFFS isolation alone does not prove crash consistency or identity retention. The current source patch still uses `SPIFFS.begin(true, ...)`: format-on-mount-failure can erase data. Do not perform unattended rounds until this risk is resolved and tested.

Inspected the pinned MeshCore checkout `81dbae592ffad40b4212bc0b37e82b38da08f4bc` locally:

- `examples/companion_radio/MyMesh.cpp`, CMD_REBOOT branch: if contacts are dirty it calls `saveContacts()`, then `board.reboot()`.
- `src/helpers/ESP32Board.h`: `reboot()` calls `esp_restart()`.
- The pinned Python `meshcore` 2.2.5 exposes asynchronous device `reboot()` sending `0x13 + reboot`.
- The pinned Meshtastic Python 2.7.5 exposes `Node.reboot(secs=10)`. This is an API candidate, not proof about the exact reference firmware's persistence or acknowledgement semantics.

These APIs make a protocol-assisted path plausible. They do NOT establish a complete filesystem sync barrier, a durable acknowledgement, protection against newly arriving writes, or reliable ROM entry after reboot. No reboot command was sent, no new automatic quiesce/reboot step was enabled, and no claim is made that this replaces power-cut testing.

Future bench evidence must cover cuts during identity/settings/channel/contact writes in BOTH firmwares, mounts after interruption, no silent formatting or regenerated identities, and recovery from the current two-profile snapshot with the original board unavailable. Record the exact write workload, cut timing, build hashes and both profile fingerprints. Resolve format-on-fail policy and explicit first-filesystem initialisation before claiming preservation. See the added acceptance rows.


Shared-NVS boundary (R2-4): pinned MeshCore `examples/companion_radio/DataStore.cpp:177` calls `nvs_flash_erase()` in `formatFileSystem()`, reached by CMD_FACTORY_RESET and CLI `erase`. This erases the common `nvs` partition, beyond the isolated SPIFFS labels. Decision: retain this known upstream behaviour and explicitly allowlist its exact source line with a risk annotation, rather than silently changing reset semantics. Factory reset/CLI erase are outside the lab protocol and forbidden during persistence measurements. The expanded audit flags NVS erase, partition erase/write, VFS registration and native SPIFFS/LittleFS format calls. An allowlist entry means reviewed visibility, not safe isolation. Meshtastic's shared-NVS use/reset behaviour is unreviewed; cross-firmware namespace and power-cut tests remain NOT RUN.


Audit coverage assumption (R2-P3-4): the storage-call audit reads only `git ls-files` paths ending in `.c`, `.cpp`, `.h`, or `.ino` within the pinned MeshCore checkout (including any tracked `lib/`). It excludes fetched/generated `.pio/libdeps`, PlatformIO frameworks/toolchains, other extensions, generated code and indirect calls hidden behind unrecognised wrappers. Exact dependency pins improve provenance but do not prove those components avoid shared-NVS/storage writes. No whole-program or transitive filesystem-isolation claim is made. A broader review and actual NVS/power-cut observations remain required.
