# B4 — reset and filesystem durability investigation

**Software/source inspection only. Hardware results: NOT RUN.** Existing ROM entry resets the running application and may interrupt a profile write. SPIFFS isolation alone does not prove crash consistency or identity retention. The current source patch still uses `SPIFFS.begin(true, ...)`: format-on-mount-failure can erase data. Do not perform unattended rounds until this risk is resolved and tested.

Inspected the pinned MeshCore checkout `81dbae592ffad40b4212bc0b37e82b38da08f4bc` locally:

- `examples/companion_radio/MyMesh.cpp`, CMD_REBOOT branch: if contacts are dirty it calls `saveContacts()`, then `board.reboot()`.
- `src/helpers/ESP32Board.h`: `reboot()` calls `esp_restart()`.
- The pinned Python `meshcore` 2.2.5 exposes asynchronous device `reboot()` sending `0x13 + reboot`.
- The pinned Meshtastic Python 2.7.5 exposes `Node.reboot(secs=10)`. This is an API candidate, not proof about the exact reference firmware's persistence or acknowledgement semantics.

These APIs make a protocol-assisted path plausible. They do NOT establish a complete filesystem sync barrier, a durable acknowledgement, protection against newly arriving writes, or reliable ROM entry after reboot. No reboot command was sent, no new automatic quiesce/reboot step was enabled, and no claim is made that this replaces power-cut testing.

Future bench evidence must cover cuts during identity/settings/channel/contact writes in BOTH firmwares, mounts after interruption, no silent formatting or regenerated identities, and recovery from the current two-profile snapshot with the original board unavailable. Record the exact write workload, cut timing, build hashes and both profile fingerprints. Resolve format-on-fail policy and explicit first-filesystem initialisation before claiming preservation. See the added acceptance rows.


Shared-NVS boundary (N5, supersedes R2-4): the pinned upstream ESP32 factory-reset path calls shared `nvs_flash_erase` through `DataStore::formatFileSystem()`, reached by CMD_FACTORY_RESET and CLI erase. Decision **a**: our versioned lab patch removes that call and returns only the result of formatting the mounted `mc_spiffs` filesystem. Exact original/prepared DataStore hashes bind this change. The upstream erase line is allowlisted only to audit the original checkout before patching and after source-only reversal; it is absent in the prepared lab function. A factory reset still intentionally destroys MeshCore's own profile and must not be triggered during profile-preservation measurements. This change does not prove global shared-NVS isolation or Meshtastic behaviour; NVS/power-cut observations remain NOT RUN.

The audit also flags Update.begin/write, esp_ota calls and spi_flash/esp_flash erase/write families. The three known AsyncElegantOTA calls are explicitly allowlisted because ESP32Board includes that path only under ADMIN_PASSWORD and without DISABLE_WIFI_OTA, for Repeater/Room. The USB companion lab build must contain no `MeshCore-OTA` marker; the build script rejects such an image before publishing it. Passing this marker check is a build guard, not whole-program or hardware proof.


Audit coverage assumption (R2-P3-4): the storage-call audit reads only `git ls-files` paths ending in `.c`, `.cpp`, `.h`, or `.ino` within the pinned MeshCore checkout (including any tracked `lib/`). It excludes fetched/generated `.pio/libdeps`, PlatformIO frameworks/toolchains, other extensions, generated code and indirect calls hidden behind unrecognised wrappers. Exact dependency pins improve provenance but do not prove those components avoid shared-NVS/storage writes. No whole-program or transitive filesystem-isolation claim is made. A broader review and actual NVS/power-cut observations remain required.


Final P3 source check: Arduino ESP32 2.0.17 initArduino has an NVS recovery erase on NO_FREE_PAGES/NEW_VERSION_FOUND, outside this tracked-source audit. It targets the first NVS partition (shared nvs in this table). Removing DataStore's explicit factory-reset erase does not remove this framework path. Track it in the [B5 hardware comparison](dualboot-proof.md#arduino-core-nvs-auto-erase-assumption--not-run); occurrence/impact on the actual board remain NOT RUN. No additional firmware patch is introduced for this unmeasured risk.
