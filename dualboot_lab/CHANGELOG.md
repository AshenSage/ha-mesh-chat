# Changelog

## 0.1.1

- Create a verified private 16 MB device backup from HA before dualboot provisioning, including boards with standalone MeshCore or Meshtastic. No flash writes, enrolment or restore is performed.
- Require a fresh verified, durably stored flash snapshot before every actual network transition, including individual switches and every round-test leg. A backup failure prevents boot-selection writes.
- Both profiles remain in isolated device storage; ordinary switches do not restore or reflash them. Preparation backups are retained separately and included in cold app backups.
- Hardware validation, message synchronization and complete project recovery remain pending.

## 0.1.0

- First experimental USB dualboot lab, separated from the later chat integration.
- Strict layout/device/build checks, private full-flash snapshot, two protocol probes and selected-profile baselines.
- Experimental single-sector OTA selection with readback; bounded round trips and restart-safe evidence reporting.
- Hardware, container and initial firmware provisioning validation remain pending.
