# Feature requirements

**Stage: Requirements gathering · Accepted scope, implementation pending**

Accepted describes the desired product, not verified technical support. Firmware and hardware compatibility must be validated before release.

## Hardware scope

The sole development, support and test target is the **Heltec WiFi LoRa 32 V4, ESP32-S3R2, 16 MB flash**, for the planned 868 MHz setup. Other boards and variants, including V4-R8, are outside the current scope and will not be developed for or tested.

Device replacement means restoring to another unit of this same model and variant. Identity and data continuity remain release requirements to validate; narrowing the hardware scope does not make them proven capabilities.

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

## Firmware provisioning

- Accept only the Heltec V4 model and variant defined above. Confirm board variant, flash size, radio band and USB access; ask for identification when detection is inconclusive. Do not offer automatic flashing for unsupported hardware.
- Download a tested, versioned dual-boot bundle with matching boot components, partition layout and both compatible firmware builds. Verify downloaded artifacts and show installation progress.
- Offer to preserve existing device data before initial installation. Explain any required erase before the installation starts.
- Verify both profiles, USB control and switching after provisioning. Allow guided recovery or a documented boot-button step when unattended entry into flashing mode fails.
- Downloading arbitrary latest upstream images is insufficient: compatibility with our dual-boot layout and remote switching must be established.
- Packaging for HAOS, flashing permissions, USB passthrough and headless first-time setup remain engineering questions. HACS is the planned distribution entry point; additional components may be needed.

## Backup and recovery

A complete project backup includes both profiles' identity keys and identifiers, settings, channel keys, supported contacts/peer data, all recorded HA conversations, contact links, favourites, outbox, notification settings, schedules and firmware/backup version metadata. Protect private keys in storage and exports.

Ordinary firmware selection should retain isolated profile storage and commit HA state without reinstalling or restoring a full backup. Fault recovery and device replacement use a separate restore workflow.

For replacement, require another Heltec V4 of the same model and variant, validate its firmware, restore supported data, then read back and compare identity keys/identifiers. Reconcile queued and uncertain sends before resuming. Retire the old radio before activating its identity on the replacement.

Cross-model migration is outside scope. Export of every firmware field and full identity preservation across supported versions still require validation. Meshtastic provides documented [configuration and identity-key backup/restore](https://meshtastic.org/docs/configuration/radio/security/); MeshCore export/import support and completeness must be verified for our chosen builds.

## Release evidence

Demonstrate both-network onboarding, repeated switches with intact identities and histories, restart-safe outbox/snooze behaviour, interrupted-installation recovery and complete restoration to a second Heltec V4 of the same model and variant. Confirm installation on another household's HA system.
