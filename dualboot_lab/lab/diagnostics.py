"""Allowlisted progress records; never forward third-party protocol output."""
import json
import os
import time

PHASES = {"inspect", "verify_backup", "snapshot", "probe_before", "write", "readback", "reset",
          "probe_after_1", "probe_after_2"}
PHASE_TIMEOUTS = {"inspect": 180, "verify_backup": 120, "snapshot": 1800,
                  "probe_before": 300, "write": 90, "readback": 90, "reset": 30,
                  "probe_after_1": 300, "probe_after_2": 300}
DEBUG_MAX_BYTES = 1024 * 1024
DEBUG_ARCHIVES = 3
LAST_PHASE = None
SINK = None


def phase(name):
    global LAST_PHASE
    if name not in PHASES:
        raise ValueError("Unknown diagnostic phase")
    LAST_PHASE = name
    if SINK is not None:
        SINK({"type": "phase", "phase": name})


WARNINGS = {"selector_nvs_changed_unvalidated"}


def warning(code):
    if code not in WARNINGS:
        raise ValueError("Unknown warning")
    if SINK is not None:
        SINK({"type": "warning", "code": code})


def log_exception(data, exc):
    # No traceback, exception payload, protocol buffer or arbitrary message.
    # Keep known esptool failure categories useful without copying packet data.
    message = "operation failed; arbitrary exception text omitted"
    for prefix in ("Failed to connect", "Timed out waiting for packet header", "No serial data received",
                   "Serial data stream stopped", "MD5 of file does not match", "Invalid head of packet"):
        if str(exc).startswith(prefix):
            message = prefix
            break
    path = data / "debug.jsonl"
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and path.stat().st_size >= DEBUG_MAX_BYTES:
        for number in range(DEBUG_ARCHIVES, 0, -1):
            old = data / ("debug.jsonl." + str(number))
            if number == DEBUG_ARCHIVES:
                old.unlink(missing_ok=True)
            elif old.exists():
                old.replace(data / ("debug.jsonl." + str(number + 1)))
        path.replace(data / "debug.jsonl.1")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "a") as stream:
        stream.write(json.dumps({"time": time.time(), "exception_type": type(exc).__name__,
                    "phase": getattr(exc, "lab_phase", LAST_PHASE), "esptool_message": message}) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
