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
