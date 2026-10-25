# Planning and open decisions

**Stage: Experimental dualboot proof · Hardware validation pending**

## Immediate milestone: USB dualboot in HA

Decision, 2026-10-25: make stable, reproducible dualboot the core of this repo first. Defer further product decisions and implementation until the foundation works in Home Assistant. This is an explicit staging decision; it does not discard the later product scope.

The [Dualboot Lab](../dualboot_lab/DOCS.md) provides the isolated test implementation. The [proof plan](dualboot-proof.md) defines the acceptance gate and hardware evidence. Start on Proxmox/HAOS, then reproduce on Raspberry Pi/HAOS before declaring both hosts supported.

- Current implementation: USB preflight, strict partition checks, private full-flash snapshot, protocol/profile baselines, experimental OTA boot-selection writes, bounded cycle runner and persistent reports.
- Current prerequisite: prepare compatible USB-capable firmware and provision explicitly. The reference BLE bundle alone does not satisfy the proof.
- Normal switching must be hands-off; buttons are allowed only for initial provisioning and recovery and must be recorded when used.
- No chat, outbox, schedules or automated message sending in this milestone. Do not run against a production radio carrying important messages.
- Unit tests or container builds are software evidence, not hardware evidence. No hardware acceptance row is passed yet.

The [feature requirements](requirements.md) and [automatic switching requirements](automatic-switching.md) contain the agreed later scope. Items under Open product decisions remain proposals, deferred until the dualboot gate passes; they do not add accepted features or remove existing ones.

## Recorded decisions

- **Backup:** capture profiles after setup/changes and before updates; daily complete project backups, retaining the latest 10 successful states per radio. Include HA backup support and protected downloads; show inactive-profile snapshot age without switching just for backup.
- **HA outage:** pause scheduled switching and retain the last firmware while powered. On return, retrieve and durably save available received messages before applying the current schedule. Defer automatic switching on synchronization/storage failure. See [recovery requirements](requirements.md#ha-outage-and-message-recovery).

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
| Internet outage | Earlier proposal 13: keep local chat/history and switching usable after setup without internet. Identify which optional features would still need connectivity. |
| Firmware updates | Earlier proposal 14: notify about tested bundles, let the user start the update, back up first and offer a validated recovery path. Automatic updates remain undecided. |
| Outbox expiry | Earlier proposal 15: choose how long an unsent message stays eligible for automatic sending. Consider confirmation after expiry rather than silently sending stale messages. |
| Users and permissions | Earlier proposal 16: decide who can chat, switch firmware, flash devices and restore/export identities. Clarify whether multiple HA users share one radio identity per network. |
| History and storage | Define storage limits and explicit export/deletion controls for chats and diagnostic trends. Resolve retention choices against the agreed persistence requirement. |
| Interface | Decide full chat panel, dashboard cards or both. Proposed: one main chat view plus a compact status card, HA theme support, mobile/desktop layouts and interface language choices. Review a wireframe for active/inactive chats, outbox, switching, errors and recovery. |
| HA automation actions | Earlier item 11 remains undecided: expose user-configurable send/switch actions, and define limits if accepted. |

Still to choose within agreed features: warning lead time, snooze duration, switch/acknowledgement and inbound-sync timeouts, bounded retry behaviour, fallback when message retrieval is unsupported, and default comparison blocks. Earlier examples such as four-hour blocks or a 24-hour outbox expiry are not fixed defaults.

## Release readiness

Use the [release evidence requirements](requirements.md#release-evidence) as the acceptance basis. Define milestone priorities, tested platform/version combinations and distribution details before announcing an installable release. The software license and firmware bundle sources/redistribution terms remain to be settled.
