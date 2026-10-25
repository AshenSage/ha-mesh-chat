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
