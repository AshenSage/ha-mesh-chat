"""Home Assistant Ingress-only lab UI. Serial work runs in a killable subprocess."""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

from aiohttp import web

from .layout import LabError, NETWORKS
from .worker import save_json, require_closed_journal, ACK_REASONS
from .diagnostics import PHASES, PHASE_TIMEOUTS

DATA = Path(os.environ.get("LAB_DATA", "/data"))
LOCAL = os.environ.get("LAB_LOCAL") == "1"
STARTUP_TIMEOUT = 30
TERMINATION_GRACE = 15
MAX_RUNS = 100
MAX_REPORT_ARCHIVES = 5


def now():
    return datetime.now(timezone.utc).isoformat()


def options(data=DATA):
    path = data / "options.json"
    return json.loads(path.read_text()) if path.exists() else {}


@web.middleware
async def ingress_only(request, handler):
    allowed = {"127.0.0.1", "::1"} if LOCAL else {"172.30.32.2"}
    if request.remote not in allowed:
        raise web.HTTPForbidden(text="Use Home Assistant Ingress")
    if request.method == "POST" and request.content_type != "application/json":
        raise web.HTTPUnsupportedMediaType()
    return await handler(request)


class Lab:
    def __init__(self, data=DATA):
        self.data = data
        self.path = data / "report.json"
        self.task = None
        self.process = None
        self.active_run = None
        try:
            self.state = json.loads(self.path.read_text()) if self.path.exists() else {"runs": []}
            if not isinstance(self.state, dict) or not isinstance(self.state.get("runs"), list) or any(
                    not isinstance(run, dict) or "status" not in run for run in self.state["runs"]):
                raise ValueError("Invalid report structure")
        except (ValueError, UnicodeError):
            quarantined = self.path.with_name("report-corrupt-" + uuid.uuid4().hex + ".json")
            self.path.replace(quarantined)
            self.state = {"runs": [], "report_recovery": {"status": "quarantined", "file": quarantined.name}}
        # Never silently resume a switch/cycle after a host/add-on restart.
        for run in self.state["runs"]:
            if run["status"] == "running":
                run.update(status="interrupted", finished=now(),
                           error="Host/app restarted. Running firmware unknown; inspect before continuing")
        self.persist()

    def persist(self):
        completed = [run for run in self.state["runs"] if run.get("status") != "running"]
        count = max(0, len(self.state["runs"]) - MAX_RUNS)
        expired = completed[:count]
        if expired:
            archive = self.data / ("report-archive-" + str(time.time_ns()) + ".json")
            save_json(archive, {"runs": expired})
            expired_ids = {id(run) for run in expired}
            self.state["runs"] = [run for run in self.state["runs"] if id(run) not in expired_ids]
            for old in sorted(self.data.glob("report-archive-*.json"))[:-MAX_REPORT_ARCHIVES]:
                old.unlink()
        save_json(self.path, self.state)

    def record_phase(self, event, action):
        if event.get("type") == "phase" and event.get("phase") in PHASES and self.active_run is not None:
            self.active_run["last_phase"] = event["phase"]
            self.active_run.setdefault("phase_events", []).append({"time": now(), "action": action,
                                                                 "phase": event["phase"]})
            self.persist()

    async def stop_worker(self, process, action):
        if process.returncode is not None:
            return
        if self.active_run is not None:
            self.active_run["termination_requested"] = True
            self.persist()
        try:
            process.terminate()
        except ProcessLookupError:
            return
        try:
            output, _ = await asyncio.wait_for(process.communicate(), TERMINATION_GRACE)
            for line in output.splitlines():
                try:
                    self.record_phase(json.loads(line), action)
                except (ValueError, TypeError):
                    continue
        except asyncio.TimeoutError:
            if self.active_run is not None:
                self.active_run["forced_kill"] = True
                self.persist()
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def worker(self, action, config, network=None, reason=None):
        started = time.monotonic()
        command = [sys.executable, "-m", "lab.worker", action, "--device", config.get("device", ""),
                   "--data", str(self.data)]
        if reason:
            command.extend(["--reason", reason])
        if network:
            command.extend(["--network", network])
        if config.get("board_confirmed") is True:
            command.append("--board-confirmed")
        if config.get("allow_boot_selection_write") is True:
            command.append("--allow-boot-selection-write")
        self.process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + STARTUP_TIMEOUT
            result = None
            while True:
                line = await asyncio.wait_for(self.process.stdout.readline(), max(0, deadline - time.monotonic()))
                if not line:
                    break
                event = json.loads(line)
                if event.get("type") == "phase" and event.get("phase") in PHASES:
                    deadline = time.monotonic() + PHASE_TIMEOUTS[event["phase"]]
                    self.record_phase(event, action)
                elif event.get("type") == "result":
                    result = event
                    break
            await asyncio.wait_for(self.process.wait(), STARTUP_TIMEOUT)
            if result is None:
                raise LabError("Worker ended without a result; phase evidence retained")
            if self.process.returncode != 0 or not result.get("ok"):
                if self.active_run is not None:
                    self.active_run["error_phase"] = result.get("error_phase")
                raise LabError(result.get("error", "USB worker failed"))
            evidence = result["result"]
            if isinstance(evidence, dict):
                evidence["duration_seconds"] = round(time.monotonic() - started, 2)
            return evidence
        except asyncio.TimeoutError as exc:
            if self.active_run is not None:
                self.active_run["error_phase"] = self.active_run.get("last_phase", "startup")
            raise LabError("USB phase timed out. Firmware state unknown; cleanup requested, no retry") from exc
        finally:
            if self.process.returncode is None:
                await self.stop_worker(self.process, action)
            self.process = None

    def start(self, action, config, network=None, cycles=1, reason=None):
        if self.task and not self.task.done():
            raise LabError("A USB job is already running")
        if action not in ("inspect", "enrol", "baseline", "switch", "resnapshot", "cycle", "acknowledge_journal"):
            raise LabError("Unknown operation")
        if action in ("switch", "cycle"):
            require_closed_journal(self.data)
        if action == "acknowledge_journal" and reason not in ACK_REASONS:
            raise LabError("Choose an explicit journal acknowledgement reason")
        if not config.get("device") and action != "acknowledge_journal":
            raise LabError("Select a USB device in the app configuration")
        if action != "inspect" and config.get("board_confirmed") is not True:
            raise LabError("Confirm Heltec V4 ESP32-S3R2 / 16 MB / 868 MHz in the app configuration")
        if action in ("switch", "cycle") and config.get("allow_boot_selection_write") is not True:
            raise LabError("Enable experimental boot-selection writes in the app configuration")
        if action in ("baseline", "switch", "cycle") and network not in NETWORKS:
            raise LabError("Choose a firmware")
        if type(cycles) is not int or not 1 <= cycles <= 20:
            raise LabError("Choose 1–20 complete round trips")
        if action == "cycle":
            registry_path = self.data / "registry.json"
            registry = json.loads(registry_path.read_text()) if registry_path.exists() else {}
            if set(registry.get("profiles", {})) != set(NETWORKS):
                raise LabError("Establish both firmware baselines with individual switches first")
        run = {"id": uuid.uuid4().hex, "action": action, "started": now(),
               "status": "running", "steps": [], "target": network, "cycles": cycles, "reason": reason}
        self.state["runs"].append(run)
        self.persist()
        self.task = asyncio.create_task(self.execute(run, config))
        return run["id"]

    async def execute(self, run, config):
        self.active_run = run
        try:
            if run["action"] == "cycle":
                result = await self.worker("resnapshot", config)
                run["steps"].append({"time": now(), "phase": "resnapshot", "result": result})
                self.persist()
                first = run["target"]
                other = next(n for n in NETWORKS if n != first)
                # Establish the requested start (not counted as a transition),
                # then perform N actual A→B→A round trips.
                result = await self.worker("switch", config, first)
                run["steps"].append({"time": now(), "phase": "start", "result": result})
                self.persist()
                for cycle in range(1, run["cycles"] + 1):
                    for target in (other, first):
                        result = await self.worker("switch", config, target)
                        if result["status"] != "switch_verified" or not result["selection_written"]:
                            raise LabError("Cycle did not produce a verified actual transition")
                        run["steps"].append({"time": now(), "cycle": cycle, "result": result})
                        self.persist()
            elif run["action"] == "acknowledge_journal":
                result = await self.worker(run["action"], config, reason=run["reason"])
                run["steps"].append({"time": now(), "result": result})
            else:
                result = await self.worker(run["action"], config, run["target"])
                run["steps"].append({"time": now(), "result": result})
            if run["action"] == "inspect" and not result.get("layout_supported"):
                run.update(status="blocked", error=result.get("reason", "Unsupported layout"))
            else:
                run["status"] = "completed"
        except asyncio.CancelledError:
            run.update(status="interrupted", error="App stopped; firmware state unknown. Inspect before continuing")
            raise
        except Exception as exc:
            run.update(status="failed", error=str(exc))
        finally:
            run["finished"] = now()
            self.persist()
            self.active_run = None


LAB_KEY = web.AppKey("lab", Lab)


async def index(request):
    return web.FileResponse(Path(__file__).with_name("index.html"))


async def status(request):
    lab = request.app[LAB_KEY]
    return web.json_response({"busy": bool(lab.task and not lab.task.done()),
                              "options": options(lab.data), "report": lab.state})


async def start(request):
    try:
        body = await request.json()
        if not isinstance(body, dict):
            raise LabError("Expected a JSON object")
        lab = request.app[LAB_KEY]
        identifier = lab.start(body.get("action"), options(lab.data), body.get("network"), body.get("cycles", 1), body.get("reason"))
        return web.json_response({"job": identifier}, status=202)
    except (LabError, ValueError) as exc:
        return web.json_response({"error": str(exc)}, status=400)


async def report(request):
    response = web.json_response(request.app[LAB_KEY].state)
    response.headers["Content-Disposition"] = 'attachment; filename="dualboot-report.json"'
    return response


async def shutdown(app):
    lab = app[LAB_KEY]
    if lab.task and not lab.task.done():
        lab.task.cancel()
        await asyncio.gather(lab.task, return_exceptions=True)


def create_app(data=DATA):
    app = web.Application(middlewares=[ingress_only])
    app[LAB_KEY] = Lab(data)
    app.router.add_get("/", index)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/start", start)
    app.router.add_get("/api/report", report)
    app.on_shutdown.append(shutdown)
    return app


if __name__ == "__main__":
    web.run_app(create_app(), host="127.0.0.1" if LOCAL else "0.0.0.0", port=8099)
