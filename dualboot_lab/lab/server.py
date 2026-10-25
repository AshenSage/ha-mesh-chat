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
from .worker import save_json
from .diagnostics import PHASES

DATA = Path(os.environ.get("LAB_DATA", "/data"))
LOCAL = os.environ.get("LAB_LOCAL") == "1"


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
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {"runs": []}
        # Never silently resume a switch/cycle after a host/add-on restart.
        for run in self.state["runs"]:
            if run["status"] == "running":
                run.update(status="interrupted", finished=now(),
                           error="Host/app restarted. Running firmware unknown; inspect before continuing")
        self.persist()

    def persist(self):
        save_json(self.path, self.state)

    async def worker(self, action, config, network=None):
        started = time.monotonic()
        command = [sys.executable, "-m", "lab.worker", action, "--device", config.get("device", ""),
                   "--data", str(self.data)]
        if network:
            command.extend(["--network", network])
        self.process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                            stderr=asyncio.subprocess.DEVNULL)
        timeout = 600 if action in ("enrol", "resnapshot") else 120
        try:
            deadline = time.monotonic() + timeout
            result = None
            while True:
                line = await asyncio.wait_for(self.process.stdout.readline(), max(0, deadline - time.monotonic()))
                if not line:
                    break
                event = json.loads(line)
                if event.get("type") == "phase" and event.get("phase") in PHASES:
                    if self.active_run is not None:
                        self.active_run["last_phase"] = event["phase"]
                        self.active_run.setdefault("phase_events", []).append({"time": now(), "action": action,
                                                                             "phase": event["phase"]})
                        self.persist()
                elif event.get("type") == "result":
                    result = event
            await asyncio.wait_for(self.process.wait(), max(0, deadline - time.monotonic()))
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
            raise LabError("USB operation timed out. Firmware state unknown; no automatic retry") from exc
        finally:
            if self.process.returncode is None:
                self.process.kill()
                await self.process.wait()
            self.process = None

    def start(self, action, config, network=None, cycles=1):
        if self.task and not self.task.done():
            raise LabError("A USB job is already running")
        if action not in ("inspect", "enrol", "baseline", "switch", "resnapshot", "cycle"):
            raise LabError("Unknown operation")
        if not config.get("device"):
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
               "status": "running", "steps": [], "target": network, "cycles": cycles}
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
        identifier = lab.start(body.get("action"), options(lab.data), body.get("network"), body.get("cycles", 1))
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
