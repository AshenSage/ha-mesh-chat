# Mini-diff review after Round 3

Review only changes after `5d486609d094b460a272530b1d6d91ac7b822660` on PR #2. Confirm its current immutable head before citing lines. The downloadable packet provides the exact head, complete patch, changed-file hashes and per-point execution record. Do not reopen unrelated unchanged code.

Six separate commits follow the requested order N1, N5, N2, N3, N4, N6:

- N1: contacts_schema 2 requires hashes of decoded public keys only; name/type/flags have a separate warning-only hash. Old full-entry baselines require deliberate recapture. Test 350 contacts, metadata drift, removal and growth.
- N5: decision a removes shared NVS erase from the prepared ESP32 companion reset function; its return depends only on its mounted filesystem format. Original/prepared source hashes and the versioned patch bind this change. Original erase is allowlisted solely for pre-patch/reversal audit. Extended OTA/direct-flash audit and forbidden MeshCore-OTA image marker; verify compile and marker exclusion in CI. This is not whole-program storage-isolation proof.
- N2: full contacts remain in the private registry; step summaries export only contacts_count for contacts. Comparison still uses full internal profiles.
- N3: verification refuses absent/foreign journal MAC before probes and rechecks MAC/target on the final transition. No retry write is enabled.
- N4: flat previous_backups (newest first), iterative legacy migration on load, pruned file references removed from metadata. Original enrolment and latest two protected. A 1200-snapshot fake-flash test exercises actual snapshot/save_json/prune helpers.
- N6: protocol N answering with otadata=S is not proof that S ran; A5 remains mandatory. Empty/generic descriptor names add no independent slot evidence.

Run only isolated software tests/builds. Do not open serial/device paths, flash, reset or reboot. Report only new/remaining concrete findings with severity, current file:line, trigger, effect and minimal test; distinguish code from hardware assumptions. Independent mini-review is pending; implementer tests are not independent review or hardware validation.

Hardware remains NOT RUN: real R2 cap, external manual A5 without the lab, original-backup/hash checks on the actual board, physical bootloader readback, normal nvs_sel stability, power-cut/formatOnFail and quiesce in both firmwares, shared NVS including Meshtastic, USB reset/re-enumeration and probe-port side effects, actual stop latency with timeout 30, HAOS non-admin access and second-board recovery. No unattended-round clearance is claimed.
