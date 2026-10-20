# Planning and open decisions

**Stage: Requirements gathering · No implementation started**

The [feature requirements](requirements.md) and [automatic switching requirements](automatic-switching.md) contain the agreed scope. The options below are proposals awaiting a decision; they do not add accepted features or remove existing ones.

## Prove the foundation

Before building the full interface, validate these engineering prerequisites on the sole supported Heltec V4 variant:

| Check | Evidence needed |
| --- | --- |
| Dual-boot control | Both compatible firmware builds fit the layout; USB selection works in both directions without a display or button press during ordinary switching. Confirm the running firmware after reconnecting. |
| Profile persistence | Keys, identifiers, settings and supported peer data remain intact across switches, restarts and power loss. Validate the chosen builds' export/import capabilities. |
| Recovery | Restore a complete project backup to a second matching board with the original unavailable; confirm both identities and HA conversations. |
| Host packaging | Run guided installation, flashing, reconnection and recovery on Proxmox/HAOS amd64 and Raspberry Pi/HAOS aarch64. |

**Current evidence status: not yet validated by this project.** Track exact board revision, firmware/build versions, HAOS version and host model when testing. Keep the first-release boundary explicit; any deferral of an agreed feature needs a scope decision.

## Open product decisions

| Topic | Decision to make / proposed direction |
| --- | --- |
| Backup policy | When to capture backups, where to keep them and how many to retain. Consider profile-change snapshots plus periodic backups, a visible last-successful-backup status and downloadable protected exports. |
| HA outage | Should automatic switching pause with the last firmware active, or continue through a separate scheduler while HA Core is unavailable? Decide the behaviour for Core downtime versus complete host power loss. |
| Internet outage | Earlier proposal 13: keep local chat/history and switching usable after setup without internet. Identify which optional features would still need connectivity. |
| Firmware updates | Earlier proposal 14: notify about tested bundles, let the user start the update, back up first and offer a validated recovery path. Automatic updates remain undecided. |
| Outbox expiry | Earlier proposal 15: choose how long an unsent message stays eligible for automatic sending. Consider confirmation after expiry rather than silently sending stale messages. |
| Users and permissions | Earlier proposal 16: decide who can chat, switch firmware, flash devices and restore/export identities. Clarify whether multiple HA users share one radio identity per network. |
| History and storage | Define storage limits and explicit export/deletion controls for chats and diagnostic trends. Resolve retention choices against the agreed persistence requirement. |
| Interface | Decide full chat panel, dashboard cards or both. Proposed: one main chat view plus a compact status card, HA theme support, mobile/desktop layouts and interface language choices. Review a wireframe for active/inactive chats, outbox, switching, errors and recovery. |
| HA automation actions | Earlier item 11 remains undecided: expose user-configurable send/switch actions, and define limits if accepted. |

Still to choose within agreed features: warning lead time, snooze duration, switch/acknowledgement timeout, bounded retry behaviour and default comparison blocks. Earlier examples such as four-hour blocks or a 24-hour outbox expiry are not fixed defaults.

## Release readiness

Use the [release evidence requirements](requirements.md#release-evidence) as the acceptance basis. Define milestone priorities, tested platform/version combinations and distribution details before announcing an installable release. The software license and firmware bundle sources/redistribution terms remain to be settled.
