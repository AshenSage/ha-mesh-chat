# Feature requirements

**Stage: Requirements gathering · Accepted scope, implementation pending**

Accepted describes the desired product, not verified technical support. Firmware and hardware compatibility must be validated before release. See [planning and open decisions](planning.md) for pending choices and technical prerequisites.

## Main workflows

1. **First installation:** connect a new target board, install the project firmware bundle and configure both profiles once. No previous backup is required.
2. **Everyday operation:** reconnect and switch networks using the existing profiles and HA history, without repeating setup or restoring a backup.
3. **Replacement after failure:** connect a new board of the same supported model and variant, select an existing project backup, install the compatible bundle and restore both profiles and application data. The old radio may be broken or unavailable; restoration must not depend on connecting it.

Replacement recovers the state captured by the last usable backup. Changes made after that backup cannot be assumed recoverable. The replacement's new hardware ID must not prevent selecting and validating the old radio's backup.

Conversion of an already configured standalone/third-party installation is a rare, lower-priority workflow. Its preservation requirements remain documented, but it should not drive the design of the primary installation and replacement flows.

## Hardware scope

The sole radio hardware development, support and test target is the **Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB flash**, for the planned 868 MHz setup. Other boards and variants, including V4-R8, are outside the current scope and will not be developed for or tested.

Device replacement means restoring to another unit of this same model and variant. Identity and data continuity remain release requirements to validate; narrowing the hardware scope does not make them proven capabilities.

## Host platforms

| Required target | Architecture | Radio connection |
| --- | --- | --- |
| Home Assistant OS in a Proxmox VM | amd64 | USB passthrough to the HAOS VM |
| Home Assistant OS directly on Raspberry Pi | aarch64 | USB connected to the Raspberry Pi |

Both targets must provide the complete feature set and the same interface: initial flashing of new or previously configured boards, both-profile setup, chat, manual/automatic switching, diagnostics, reporting, backup and same-model device replacement.

Package any flashing service and its dependencies for both architectures. Document platform-specific USB setup, handle device reconnection after boot-mode changes, and validate the complete workflow on each target. Tested Raspberry Pi models and HAOS versions must be listed with release evidence; host support is a requirement, not a claim of completed testing.

## Decisions

| # | Feature | Requirement |
| --- | --- | --- |
| 1 | Chat navigation | Browse either network's saved conversations without rebooting the radio. Mark only the confirmed active network as active. Radio transmission requires that network to be active. |
| 2 | Outbox | For the inactive network, offer "Send on next switch" or "Switch and send". Persist queued messages; allow review and cancellation. Never display a queued message as sent. |
| 3 | Switch warning | Warn before an automatic switch, show a countdown, and provide Snooze. Make the warning lead time and snooze duration configurable. See [automatic switching](automatic-switching.md). |
| 4 | Shared contacts | Let users manually link a person's MeshCore and Meshtastic identities under one contact. Keep network addresses and conversation histories distinct. |
| 5 | Delivery status | Show queued, accepted by the radio, confirmed transmission, recipient acknowledgement, timeout and failure only where supported and observed. Unknown stays unknown; acceptance is not proof of delivery or reading. |
| 6 | Notifications | Allow notification behaviour to be changed after installation through familiar HA configuration. Support per-contact/channel preferences and quiet hours where applicable; details remain to be designed. |
| 7 | Diagnostics and trends | Show connection health, last received traffic, failures and historical trends. Include RSSI/SNR, response times, delivery outcomes and radio statistics where exposed, with timestamps and measurement context. |
| 8 | Favourites and channel setup | Pin contacts/channels and select defaults per network. Support each protocol's native channel and routing-scope concepts; do not assume equivalent features. |
| 9 | Public guided installation | Anyone can download and install the project. Connecting a supported radio should lead into guided firmware download, flashing, verification and setup of both profiles. |
| 10 | Complete backup and replacement | Back up both identities and profiles plus application data. Restore onto another Heltec V4 of the same model and variant and verify identity continuity. See recovery requirements below. |
| 11 | HA automation actions | **Undecided.** User-defined actions such as sending messages or requesting switches are not accepted scope yet. |
| 12 | Comparison report | Provide a readable report over a configurable period, such as one month: actual observation time, selected-peer delivery/reply outcomes, response times and outages. Follow the fairness rules in [automatic switching](automatic-switching.md). |

Browsing a chat and switching the radio are separate actions. Users may prepare an inactive-network message through the outbox; only the active firmware can transmit it. Automatic retry and ambiguous delivery outcomes must not cause silent duplicate sends.

## Trends and protocol differences

- Keep observations separate by network, peer or radio link and firmware version where relevant.
- Show gaps during inactive periods and disconnections; do not interpret missing samples as zero signal.
- RSSI/SNR normally describe an observed radio reception, not the entire multi-hop route or a person's continuous availability.
- Distinguish chat channels, MeshCore routing scopes/regions and the radio's regulatory region. Confirm the user's local scope label before adding presets.
- Build a versioned capability matrix before designing advanced settings. Mark unavailable measurements/features explicitly.

Primary references: MeshCore documents [public, hashtag and private channels](https://docs.meshcore.io/companion_protocol/) and separate [region/scope controls](https://docs.meshcore.io/cli_commands/). Meshtastic documents [primary/secondary channels, names and shared keys](https://meshtastic.org/docs/configuration/radio/channels/). These concepts must not be mapped as identical.

## Device recognition and existing profiles

- Identify the physical radio using the ESP32-S3 factory eFuse MAC where accessible. Keep it separate from firmware-reported Wi-Fi/BLE addresses, mesh identity keys, display names and changing USB paths.
- Maintain a local device registry with first/last seen, model, installed layout/build, each network's identity and setup state, and linked backup records. Recognition means known to this HA installation or its imported registry, not proof of a device's entire usage history.
- Check backup existence, readability, integrity, age, identity and version compatibility separately. A known device does not imply that a usable or current backup exists.
- Inspect before writing. If identification needs a bootloader restart, explain that interruption; detection alone must not erase or flash the radio.

| Detected state | Required behaviour |
| --- | --- |
| Known device with validated project dual-boot layout and matching profiles | Reconnect and reuse the profiles; do not reinstall or restore solely because the device was reconnected. |
| Existing configured MeshCore or Meshtastic only | Read and back up the existing identity/settings through a supported interface. Offer migration to the project dual-boot layout, restore and verify the existing profile, then guide setup only for the missing profile. |
| No usable profile found | Offer initial installation and setup; absence of a readable profile does not prove the board is factory-new. |
| Known board with reset or changed identity/layout | Show the discrepancy and appropriate recovery choices; never overwrite current device data with an older backup merely because the hardware ID matches. |

Display device recognition, active firmware, each profile's setup state, dual-boot readiness and last usable backup as separate facts.

A working standalone MeshCore installation can be used through a compatible companion connection without repeating radio setup. MeshCore BLE and USB companion builds have different interfaces; USB power alone does not establish a usable chat or export connection.

Preserving an existing profile during the one-time dual-boot conversion is a required migration goal for supported builds, pending validation of key export/import and settings compatibility. If preservation cannot be verified, stop the preserving migration and explain what is missing before offering a separate fresh installation. Existing phone-app chat history is not automatically imported.

Normal network switches reuse isolated profile storage; backup restoration belongs to conversion, repair or replacement. A replacement radio has a new hardware ID even when its restored mesh identity stays the same; update the device/backup association and retain its history.

Technical references: Espressif documents the [factory eFuse MAC](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/espefuse/get-custom-mac-cmd.html) and [MAC/flash read commands](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html). MeshCore documents [companion interface types](https://github.com/meshcore-dev/MeshCore/blob/main/docs/faq.md); private-key export/import is [build-dependent](https://github.com/meshcore-dev/MeshCore/blob/main/examples/companion_radio/MyMesh.cpp).

## Firmware provisioning

- Accept only the Heltec V4 model and variant defined above. Confirm board variant, flash size, radio band and USB access; ask for identification when detection is inconclusive. Do not offer automatic flashing for unsupported hardware.
- Download a tested, versioned dual-boot bundle with matching boot components, partition layout and both compatible firmware builds. Verify downloaded artifacts and show installation progress.
- Support factory-new and previously configured boards of the target model. Offer to preserve readable existing device data before installation and explain any required erase before it starts. Importing arbitrary third-party firmware settings is not guaranteed.
- Verify both profiles, USB control and switching after provisioning. Allow guided recovery or a documented boot-button step when unattended entry into flashing mode fails.
- Downloading arbitrary latest upstream images is insufficient: compatibility with our dual-boot layout and remote switching must be established.
- Packaging for both HAOS host targets, flashing permissions, USB access and headless first-time setup remain engineering questions. HACS is the planned distribution entry point; additional components may be needed.

## Backup and recovery

A complete project backup includes both profiles' identity keys and identifiers, settings, channel keys, supported contacts/peer data, all recorded HA conversations, contact links, favourites, outbox, notification settings, schedules and firmware/backup version metadata. Protect private keys in storage and exports.

### Accepted backup policy

- Capture each profile after its first setup and after confirmed changes to identity, channels or settings; capture a verified recovery point before firmware updates.
- Create a complete project backup daily and retain the latest **10 successful complete backup states per radio**. Failed attempts must not displace usable backups.
- Include project data in regular HA backups and offer downloadable protected exports.
- Persist chat messages continuously in HA; periodic backups provide separate recovery points.
- Use the inactive profile's last confirmed snapshot without forcing a network switch just to back it up. Display the capture time and completeness for each profile, plus the last successful complete backup.

Ordinary firmware selection should retain isolated profile storage and commit HA state without reinstalling or restoring a full backup. Fault recovery and device replacement use a separate restore workflow.

For replacement, require another Heltec V4 of the same model and variant, validate its firmware, restore supported data, then read back and compare identity keys/identifiers. Reconcile queued and uncertain sends before resuming. Retire the old radio before activating its identity on the replacement.

Cross-model migration is outside scope. Export of every firmware field and full identity preservation across supported versions still require validation. Meshtastic provides documented [configuration and identity-key backup/restore](https://meshtastic.org/docs/configuration/radio/security/); MeshCore export/import support and completeness must be verified for our chosen builds.

## HA outage and message recovery

The accepted baseline is to pause scheduled switching while HA/the controlling service is unavailable. A powered radio should remain on the last selected firmware. An independent outage scheduler is outside this baseline. Full host power loss may also remove USB power; reception during that period must not be assumed.

On startup or reconnection:

1. Identify the actual running firmware and reconnect its backend before applying a different schedule target.
2. Attempt to retrieve all messages still available from that firmware's receive queue/history, using a bounded synchronization pass.
3. Commit retrieved messages durably to HA, retain original network/identity/timestamp information where available and deduplicate replays before considering the import complete.
4. Finish the recovery/synchronization phase, then apply the schedule appropriate to the current time. Do not replay missed switches.

Apply the same inbound synchronization step before ordinary firmware switches. On synchronization or HA storage failure, defer an automatic switch, use bounded retries and show the reason. Display progress such as "Recovering messages" and keep recovered history available.

Distinguish completed retrieval, no pending messages, unsupported retrieval and errors. Firmware buffering, retention across reboots, destructive queue reads and recoverable history must be validated per build; this feature cannot reconstruct messages the radio no longer holds or messages never received on the inactive network. Define the unsupported-retrieval fallback and exact time/retry limits before release.

## Release evidence

Demonstrate both-network onboarding, repeated switches with intact identities and histories, restart-safe outbox/snooze behaviour, interrupted-installation recovery and complete restoration to a second Heltec V4 of the same model and variant. Run the complete acceptance flow on both Proxmox/HAOS (amd64) and Raspberry Pi/HAOS (aarch64), including new-board installation, reinstallation over existing firmware and recovery. Also verify replacement with the old radio disconnected/unavailable, reconnect recognition, changed-identity detection, missing/stale backup handling and preservation of an existing single-firmware profile during dual-boot conversion. Verify the backup triggers, 10-state retention, HA-backup inclusion/export and per-profile snapshot age. Test restart/reconnect with an inbound backlog: import and durable storage must precede a schedule-driven reboot; exercise duplicate retrieval, continuous incoming traffic, read/storage failures and unsupported retrieval. Confirm installation on another household's HA system.
