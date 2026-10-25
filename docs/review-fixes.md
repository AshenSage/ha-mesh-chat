# Review fixes

Base: fe123bd5c7ef4c2d87e8ac59836c3314833d14f7. All checks below are software-only; no device/flash operations were executed. Hardware acceptance remains NOT RUN.

## A1 — snapshot timing

Inspected worker.py original 219–243 and current snapshot/run paths, server cycle path and DOCS setup order. Both profiles must be configured before enrolment. Added read-only resnapshot after both baselines; every cycle captures a fresh snapshot before switching and stops if it fails. Recovery now requires a current snapshot restored to a second board (NOT RUN).

Executed: `python -m pytest -q` — 18 passed; `git diff --check` passed. New tests exercise two-profile capture, incomplete snapshot, missing baseline and pre-cycle snapshot failure.

## A2 — reject swapped or unidentified firmware slots before writes

Rechecked current worker.py select/inspect (97–136) and ESP app descriptor bytes in the cached binary files, without devices. verify_slot_projects reads both descriptors before the OTA write. Fake swapped slots and generic descriptors are rejected. Both existing real app files identify as arduino-lib-builder: they remain INCOMPATIBLE with this guard until explicit project names are supplied; no runtime/hardware claim.

Executed: `python -m pytest -q` — 20 passed in 0.36s; `git diff --check` passed. No device operations.

## A3 — observe embedded PSRAM capacity and refuse non-R2 candidate writes

Rechecked Radio.__enter__/select lines 71–115 and inspected esptool 4.11.0 ESP32S3ROM get_psram_cap/get_chip_features source. Read-only inspection records cap/features; select requires cap 2. Fake ROM contexts cover caps 0/1/2/3 and cleanup. Real V4-R2 cap correspondence is NOT RUN.

Executed: `python -m pytest -q` — 24 passed in 0.41s; `git diff --check` passed. No device operations.

## A4 — allowlist pinned reference binaries and check offline bootloader readback

Rechecked current DOCS first-flash steps 49–65 and esptool 4.11 _update_image_flash_params. Committed exact SHA-256/size provenance for all five pinned reference files. Offline checker validates input files and an optionally supplied readback against the header-adjusted expected bytes. Executed the checker against the cached reference files, without device access. Tests reject corrupt source/readback and distinguish source/written hashes. Hardware readback remains NOT RUN.

Executed: `python -m pytest -q` — 25 passed in 0.48s; `git diff --check` passed. No device operations.

## A5 — record manual OTA bootloader hypothesis as an unresolved hardware gate

Rechecked current proof sequence and the external selector/NVS assumption. Added a separate manual, bidirectional procedure with before/after OTA and nvs_sel evidence, independent runtime observation, immutable builds and power-cycle checks. No manual test was executed and no hardware result was invented. Documentation-only point: existing regression suite was run; the required physical proof remains NOT RUN and blocks lab automation.

Executed: `python -m pytest -q` — 25 passed in 0.34s; `git diff --check` passed. No device operations.

## B2 — persist JSONL phases and boot-selection transaction status

Rechecked current select journal/write/readback, worker main and parent subprocess reader. Added allowlisted inspect/probe/write/readback/reset phases, streamed and persisted by the parent; pending -> written -> verified journal transitions; and a private debug JSONL containing phase/type and safe esptool failure categories, never arbitrary exception/protocol text. Tests cover journal transitions, secret redaction and persisted parent phase on failure. Timeout cleanup is addressed separately in B3.

Executed: `python -m pytest -q` — 27 passed in 0.39s; `git diff --check` passed. No device operations.

## B6 — enforce explicit write permission at CLI orchestration and Radio.select

Rechecked worker Radio constructor/select/run/main and parent command construction after B2. The server forwards explicit board/write CLI flags from options; direct CLI run and Radio.select both default to denial. Tests cover all missing-flag combinations and prove device resolution/write methods are not entered. Explicit flags express permission, not hardware validation.

Executed: `python -m pytest -q` — 30 passed in 0.58s; `git diff --check` passed. No device operations.

## B3 — unwind ROM sessions on SIGTERM and bound individual phases

Rechecked subprocess timeout/kill and Radio.__exit__ after B2/B6. Worker SIGTERM raises through the context manager to attempt hard_reset/close; repeated TERM does not interrupt cleanup. Parent sends TERM and allows 15 seconds before recording a forced kill. Replaced total 120-second deadline with per-phase budgets (inspect 180s, snapshot 1800s, probes/write/readback 90s, reset/startup 30s). Tests simulate signal unwind, cleanup success/failure, timeout cause and phase preservation without devices. Reset success on real USB is NOT RUN.

Executed: `python -m pytest -q` — 34 passed in 0.51s; `git diff --check` passed. No device operations.

## B1 — exercise complete run guards and pinned esptool write contracts

Rechecked current run (287–368) after phase/permission/cleanup changes. Added full fake-radio orchestration for damaged/missing backups, MAC/table/app drift, both pre-write probes, both target probes, first_boot_baseline and no-op. Added a second current-profile observation before select. Pre-write failures assert zero select calls; post-write failures assert one attempt, unverified journal and no retry (a completed write cannot be retroactively prevented). Contract test actually invokes 4.11.0 decorated compressed-write/read/hash methods on an uninitialised fake-transport object, with no serial port, and checks closure signatures.

Executed: `python -m pytest -q` — 45 passed in 0.56s; `git diff --check` passed. No device operations.

## B4 — record power-cut and graceful-quiesce evidence still required

Rechecked source patch line 51, proof matrix and pinned MeshCore CMD_REBOOT/ESP32Board source plus both Python reboot APIs. Added profile-write power-cut and quiesce acceptance rows. API-availability test executes no commands. Source inspection finds a MeshCore dirty-contact save before esp_restart, but does not prove a full durable barrier. Format-on-fail risk and real power-cut/quiesce tests remain explicit blockers, NOT RUN; no new reboot automation was enabled.

Executed: `python -m pytest -q` — 46 passed in 0.56s; `git diff --check` passed. No device operations.

## B5 — bind bootloader and selector NVS fingerprints to the registry

Rechecked current inspect and require_same_device. Added bootloader 0..0x8000 and table-derived nvs_sel MD5 observations/comparison. Full run tests now reject either changed fingerprint before select. Shared NVS is not falsely required to remain byte-identical: added a private, read-only namespace/type/value-hash comparison procedure for both directions, decoder provenance and investigation of legitimate writes. This physical comparison remains NOT RUN.

Executed: `python -m pytest -q` — 48 passed in 0.58s; `git diff --check` passed. No device operations.

## B7 — include channel-key hashes and MeshCore contacts in profile comparisons

Rechecked both probe functions and pinned protocol/library channel APIs. MeshCore reads explicit bounded capacity, every channel and contacts; Meshtastic requires completed local channels. Hash inputs include index/name/PSK digest and role, without returning raw keys. Missing/incomplete reads block verification. Tests mutate PSK/remove channels and check no raw secret appears. Probe budgets increased to 300 seconds for bounded 64-channel reads. Old baseline migration is explicit, not silently overwritten.

Executed: `python -m pytest -q` — 50 passed in 0.56s; `git diff --check` passed. No device operations.

## C1 — prepare firmware using an atomic checked versioned patch and filesystem audit

Rechecked prepare_meshcore_usb.py full current string replacement path. Replaced global ini mutation with a versioned patch that changes only the USB environment, preserving other environments. Exact original/prepared file hashes, repo-wide filesystem-call allowlist, git apply --check, idempotence and --reset prevent partial/unknown edits. Missing/changed/last-section input gets an explicit refusal rather than ValueError. Build checks mc_spiffs in the image and records PlatformIO/platform/timestamps/build-log hash. Synthetic git tests cover prepare/reset, unexpected calls and changed layout; no source build or device action executed in this point.

Executed: `python -m pytest -q` — 53 passed in 0.61s; `git diff --check` passed. No device operations.

## C2 — lock Python and PlatformIO dependencies and pin least-privilege CI actions

Rechecked Dockerfile, direct requirements, source patch and both workflows. Generated Linux Python 3.12 runtime (37), dev/build (54) and bootstrap (2) locks with exact versions and SHA-256 hashes from official PyPI release metadata. Install uses require-hashes/no-build-isolation with locked bootstrap. Platform/external libraries/toolchains are exactly pinned in USB-only patch. Resolved six action tags through GitHub and pinned their commit SHAs; workflows use contents:read and checkout persist-credentials:false. Every architecture build now executes import lab.server inside the container. Tests enforce action/lock/pin/smoke policies; actual fresh multiarch builds remain CI evidence, not HAOS/hardware evidence.

Executed: `python -m pytest -q` — 57 passed in 0.68s; `git diff --check` passed. No device operations.

## C3 — refuse CRC-valid sequence zero and match undefined no-rollback OTA state

Rechecked current layout.py boot_entries/plan_selection. CRC-valid seq 0 now fails explicitly. New selection records write UNDEFINED 0xFFFFFFFF instead of claiming VALID=2; accepted read states and rollback refusal remain conservative. Added independent literal seq-1 CRC 0x4743989A, zero and emitted-state tests. Documented ESP-IDF no-rollback policy and required actual otatool/bootloader comparison in A5, still NOT RUN.

Executed: `python -m pytest -q` — 58 passed in 0.80s; `git diff --check` passed. No device operations.

## C4 — test trusted Ingress peer and document unproved HAOS access/reset assumptions

Rechecked middleware, config usb/uart/udev and hard_reset call. Added positive trusted-peer test and rejection of forwarded-header spoofing. Inspected/called pinned S3 reset control flow on an uninitialised fake object: 4.11 derives USB mode internally; adding uses_usb to its override would be invalid. Actual non-admin direct-URL rejection, native USB reset and re-enumerated /dev visibility are new NOT RUN acceptance rows; docs no longer assert backend admin protection based on panel_admin alone.

Executed: `python -m pytest -q` — 62 passed in 1.22s; `git diff --check` passed. No device operations.

## C5 — harden private storage report recovery and offline OTA recovery planning

Rechecked current snapshot/save_json, report startup/persist and all hardcoded OTA offsets. Private files now use exclusive os.open mode 0600 before writes; unique JSON temps are cleaned on errors. Unlinked pre-registry snapshots are detected and preserved. Snapshot bytes cross-check flash_md5sum(0, FLASH_SIZE). Corrupt reports are quarantined and reports rotate (100 live runs, five archives). OTA constants derive from EXPECTED. Added a file-only single-sector recovery planner, never a second device-write path. Tests cover mode at open, hash mismatch, orphan detection, corrupt/rotated reports, candidate sizing/MAC refusal; no physical restore executed.

Executed: `python -m pytest -q` — 66 passed in 0.70s; `git diff --check` passed. No device operations.

## Final software-only verification

A fresh Python 3.12 virtual environment installed the 2-package bootstrap and all 54 dev/build/runtime distributions using `--require-hashes` and `--no-build-isolation`. In that environment: `python -m pytest -q` — 66 passed; `python -m compileall -q dualboot_lab/lab tools` passed; `PYTHONPATH=dualboot_lab python -c 'import lab.server'` passed; `pip check` reported no broken requirements. The first manual import from repository root without PYTHONPATH failed due to that invocation's search path; the corrected invocation above and Docker's /app working directory include the lab package.

The exact versioned source patch was reset/reapplied successfully against the pinned cached checkout, without compiling or accessing hardware. The offline A4 header transformation was evaluated on the allowlisted cached bootloader: source/written header both e903024f and length 15040; the selected dio/80m/16MB options already match this reference, so its expected hash is unchanged. No physical readback was performed. Actual fresh multiarchitecture builds belong to CI; actual HAOS/device results remain NOT RUN.

Open gates: A2 generic descriptors require explicitly identifying firmware builds; A3 real V4-R2 cap correspondence; A5 manual OTA/selector boot hypothesis; B4 filesystem format-on-fail/power-cut/quiesce; B5 shared-NVS namespace comparison; C4 real Ingress non-admin/USB/reset; second-board recovery. No checker or operator template is labelled hardware-validated.

## R2-1 — bind slot identity to manual runtime attestations before switching

Rechecked layout.py verify_slot_projects and worker.py inspect/baseline/select at reviewed head. Both manually booted runtimes must be baselined and bound to slot/app MD5. The first switch inspect refuses missing, swapped or changed attestations before any probe; the writer repeats it. Non-generic descriptor conflicts remain blocked, generic Arduino descriptors now work with attestation. Removed first_boot_baseline writes; docs/UI require both manual baselines. Tests include generic images, swapped names/attestations, changed hashes, early refusal and baseline attestation. Executed test commands use ../mesh-lab-venv/bin/python (Python 3.12); no USB, real flash, reset or reboot. A5 and all hardware assumptions remain NOT RUN.

Executed: `python -m pytest -q` — 70 passed in 0.90s; `git diff --check` passed. No device operations.

## R2-5 — block writes on open journals and require explicit acknowledgement

Rechecked current select/mark_selection/run and server start/execute. Pending, written and unknown states block switch/cycle before device access and again inside Radio.select. File-only acknowledge_journal requires an explicit bounded reason code, archives the complete original pre-state before marking acknowledged, and records the reason in the report. Added UI/CLI/API route and tests for all gates and archive preservation. Exact commands: ../mesh-lab-venv/bin/python -m pytest -q; git diff --check. No physical operations; no recovery claim.

Executed: `python -m pytest -q` — 74 passed in 0.96s; `git diff --check` passed. No device operations.

## R2-6 — close matching written journals through write-free verification retries

Rechecked current run and journal transition after R2-5. Added verify_selection for the already selected target: both baseline probes must succeed; then only a matching written journal becomes verified. Pending, other-target and failed probes leave journal/pre-state unchanged. This explicitly resolves the tension with R2-5: switch remains blocked; retry is observation-only and never calls select. UI/API/CLI expose it. Executed ../mesh-lab-venv/bin/python -m pytest -q and git diff --check; all transport/protocol fixtures fake, no device operations.

Executed: `python -m pytest -q` — 78 passed in 0.98s; `git diff --check` passed. No device operations.

## R2-2 — separate MeshCore profile components and permit contact growth

Rechecked current MeshCore probe/compare_profile and related tests. Radio and channel hashes are separate; contacts_count and a set of hashed stable contact records replace the monolithic settings hash. Baseline contact membership is a subset requirement; growth is allowed, losses/channel-key drift fail with the component name. Missing old component fields demand Baseline neu erfassen. Tests cover growth, loss, key drift, old schema and run-level no-select on contact loss. Exact commands: ../mesh-lab-venv/bin/python -m pytest -q; git diff --check. No device, flash, reset or reboot operations.

Executed: `python -m pytest -q` — 83 passed in 6.70s; `git diff --check` passed. No device operations.

## R2-3 — check live profile before resnapshot and retain chained recovery points

Rechecked resnapshot/snapshot at current lines. Live active profile must match baseline before snapshot; a second inspect checks unchanged device/selection. Drift never snapshots or changes the registry pointer. previous_backup chains recovery metadata; enrol_backup and latest two snapshots are protected. Older snapshots are candidates only, deleted only after explicit file-only prune_snapshots --reason retention_reviewed with an audit record. Tests cover drift, ordering, five linked snapshots, no automatic deletion and protected retention. Exact commands: ../mesh-lab-venv/bin/python -m pytest -q; git diff --check. No device operations; inactive live verification and actual recovery remain NOT RUN.

Executed: `python -m pytest -q` — 86 passed in 0.97s; `git diff --check` passed. No device operations.

## R2-7 — defer SIGTERM through reset and port cleanup

Rechecked install_signal_handlers, detect_chip ownership and Radio.__exit__. Handler always records a flag and raises only outside the cleanup section; first and repeated signals during reset/close are deferred until completion. Existing failure phase is retained. Added fake hard_reset that invokes SIGTERM twice and must finish reset/close; detection-before-ownership is tested without asserting cleanup it cannot perform. Docs explicitly state the possible ROM-mode remainder during detect_chip. Exact commands: ../mesh-lab-venv/bin/python -m pytest -q; git diff --check. No actual signal sent to device/process, USB/reset/reboot or flash operation.

Executed: `python -m pytest -q` — 88 passed in 1.25s; `git diff --check` passed. No device operations.

## R2-4 — audit NVS partition and VFS calls and expose shared-reset risk

Rechecked FS_CALL/audit and downloaded pinned upstream 81dbae5 read-only. The newly detected exact DataStore.cpp:177 nvs_flash_erase line is consciously allowlisted with its destructive shared-NVS decision; factory-reset semantics are unchanged and such commands are excluded from persistence experiments. Expanded detection includes NVS erase/erase_partition, esp_partition erase/write families, VFS registration and native FS format. Docs state SPIFFS labels do not isolate shared NVS and Meshtastic side is unreviewed. Executed git clone of upstream, git checkout pinned ref, prepare_meshcore_usb.py /tmp/mesh-r2-source twice and --reset (all source-only, successful); ../mesh-lab-venv/bin/python -m pytest -q; git diff --check. No PlatformIO compile, device, flash, reset or reboot operation (script --reset reverses source patch only).

Executed: `python -m pytest -q` — 95 passed in 1.08s; `git diff --check` passed. No device operations.
