# Round 3: focused diff review

Review only the changes after `71c4a02baa9ac93ba04f07d10a8a4788f56265f8` on PR #2. Confirm its current immutable head before citing lines. The downloadable review packet includes the exact head, ordered commits, complete unified diff and per-point execution record. Unchanged source is the already reviewed Round 2 packet/base.

Order implemented: R2-1, R2-5, R2-6, R2-2, R2-3, R2-7, R2-4, R2-8, R2-9, then six individual P3 commits. No full rewrite. Inspect these decision points:

- Slot attestations bind successful manual USB baselines to both unchanged app hashes; generic descriptors require these attestations, conflicting non-generic descriptors still fail. Missing target baseline never triggers a write. First inspect fails before probes/another ROM session.
- Contact growth is permitted through component comparison; retained baseline records are hashed and required as a subset. Lost/changed baseline contact records, radio and channel drift identify only the component. Old schemas require deliberate re-enrolment.
- Resnapshot validates the active live profile before reading flash and chains prior recovery points. Only explicit retention acknowledgement may remove older known snapshots; original/latest two are protected.
- Open journals block new writes. `verify_selection` is a dedicated observation-only retry that can close a matching written journal after two baseline probes; it never calls select. `acknowledge_journal` preserves the original in an archive with a bounded reason code. Pending never means no write occurred.
- The first SIGTERM during reset/close is deferred. Detection interrupted before loader ownership can leave ROM mode. Supervisor timeout is configured at 30 seconds, parent grace 15, HTTP shutdown 2; actual stop latency is NOT RUN.
- N5 now neutralises the known MeshCore shared-NVS factory-reset erase in the lab patch; original-source allowlisting exists solely for pre-patch/reversal audit. The audit is tracked-source-only. Selector NVS drift is a visible warning until normal-boot stability is measured.

Run only isolated software tests/builds; do not open any serial/device path, flash, reset or reboot. Report severity, exact current file:line, trigger, effect and a minimal regression test. Distinguish implemented, partial, hardware-only and new regressions; a passing fake does not prove physical behaviour. Specifically challenge the new journal/verification path and snapshot retention crash boundaries. Do not accept the implementer's claims as independent evidence.

Hardware gates remain NOT RUN: real R2 cap; A5 external-esptool manual bidirectional boot selection without the lab, after original backup/reference hash checks; bootloader readback; nvs_sel normal-boot hashes; both firmware power-cut/format-on-fail and graceful quiesce; shared NVS use (including Meshtastic); USB reset/re-enumeration and whether opening probe ports resets firmware; HAOS non-admin access; second-board recovery. No lab round-test clearance follows from software review alone.
