# Review fixes

Base: fe123bd5c7ef4c2d87e8ac59836c3314833d14f7. All checks below are software-only; no device/flash operations were executed. Hardware acceptance remains NOT RUN.

## A1 — snapshot timing

Inspected worker.py original 219–243 and current snapshot/run paths, server cycle path and DOCS setup order. Both profiles must be configured before enrolment. Added read-only resnapshot after both baselines; every cycle captures a fresh snapshot before switching and stops if it fails. Recovery now requires a current snapshot restored to a second board (NOT RUN).

Executed: `python -m pytest -q` — 18 passed; `git diff --check` passed. New tests exercise two-profile capture, incomplete snapshot, missing baseline and pre-cycle snapshot failure.
