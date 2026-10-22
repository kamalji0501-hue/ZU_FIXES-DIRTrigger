#!/usr/bin/env python3
"""GO-desk fleet health shim for Command Center (no Kavach).

Listens on 8789 and serves the same endpoints the Anand aggregator polls:
  GET /api/fleet/desk-snapshot
  GET /api/host-health

Auth: X-Copy-Key matching Trading_Runtime_Rahul copy_key.txt (or GO_FLEET_COPY_KEY).
Keep batman-kavach2 down; this process is health-only.
"""

from __future__ import annotations

import hmac
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

COPY_KEY_PATHS = (
    Path("/home/ubuntu/Trading_Runtime_Rahul/Data/data/shared/copy_trading/copy_key.txt"),
    Path("/home/ubuntu/Go_Bot_Runtime/Data/data/shared/copy_trading/copy_key.txt"),
)

_LAST_CPU: tuple[float, float] | None = None


def _read_copy_key() -> str:
    env = (os.environ.get("GO_FLEET_COPY_KEY") or os.environ.get("FLEET_COPY_KEY") or "").strip()
    if env:
        return env
    for path in COPY_KEY_PATHS:
        try:
            if path.is_file():
                key = path.read_text(encoding="utf-8").strip()
                if key:
                    return key
        except Exception:
            continue
    return ""


def _auth_ok(request: Request) -> bool:
    expect = _read_copy_key()
    if not expect:
        return False
    got = (request.headers.get("x-copy-key") or "").strip()
    return bool(got) and hmac.compare_digest(got, expect)


def _unit_active(unit: str) -> str:
    try:
        r = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return (r.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _read_proc_stat() -> tuple[float, float] | None:
    try:
        with open("/proc/stat", encoding="utf-8") as fh:
            line = fh.readline()
        parts = line.split()
        if parts[0] != "cpu":
            return None
        nums = [float(x) for x in parts[1:]]
        idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)
        return idle, sum(nums)
    except Exception:
        return None


def _cpu_percent() -> float | None:
    global _LAST_CPU
    cur = _read_proc_stat()
    if cur is None:
        try:
            load1 = os.getloadavg()[0]
            ncpu = os.cpu_count() or 1
            return round(min(100.0, (load1 / max(ncpu, 1)) * 100.0), 1)
        except Exception:
            return None
    if _LAST_CPU is None:
        _LAST_CPU = cur
        time.sleep(0.12)
        cur2 = _read_proc_stat()
        if cur2 is None:
            return None
        prev, cur = _LAST_CPU, cur2
    else:
        prev, cur = _LAST_CPU, cur
    _LAST_CPU = cur
    di = cur[0] - prev[0]
    dt = cur[1] - prev[1]
    if dt <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1.0 - di / dt) * 100.0)), 1)


def _mem_percent() -> tuple[float | None, float | None, float | None]:
    try:
        info: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                info[k.strip()] = int(v.strip().split()[0])
        total_kb = float(info.get("MemTotal") or 0)
        avail_kb = float(info.get("MemAvailable") or info.get("MemFree") or 0)
        if total_kb <= 0:
            return None, None, None
        used_kb = total_kb - avail_kb
        return (
            round((used_kb / total_kb) * 100.0, 1),
            round(used_kb / (1024 * 1024), 2),
            round(total_kb / (1024 * 1024), 2),
        )
    except Exception:
        return None, None, None


def _disk_percent(path: str = "/") -> tuple[float | None, float | None, float | None]:
    try:
        u = shutil.disk_usage(path)
        pct = round((u.used / u.total) * 100.0, 1) if u.total else None
        return pct, round(u.used / (1024**3), 2), round(u.total / (1024**3), 2)
    except Exception:
        return None, None, None


def _process_cpu(needles: tuple[str, ...]) -> tuple[bool, float | None, int | None]:
    try:
        r = subprocess.run(
            ["ps", "-eo", "pid,pcpu,comm,args", "--no-headers"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if r.returncode != 0:
            return False, None, None
        ncpu = max(os.cpu_count() or 1, 1)
        best = None
        for line in (r.stdout or "").splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) < 4:
                continue
            pid_s, pcpu_s, comm, args = parts
            blob = f"{comm} {args}".lower()
            if not any(n in blob for n in needles):
                continue
            try:
                pid = int(pid_s)
                pcpu = float(pcpu_s)
            except Exception:
                continue
            host_pct = round(min(100.0, pcpu / ncpu), 1)
            row = (pid, host_pct, pcpu)
            if best is None or row[2] > best[2]:
                best = row
        if not best:
            return False, None, None
        return True, best[1], best[0]
    except Exception:
        return False, None, None


def collect_host_health() -> dict[str, Any]:
    cpu = _cpu_percent()
    ram_pct, ram_used, ram_total = _mem_percent()
    disk_pct, disk_used, disk_total = _disk_percent("/")
    load = None
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass
    units = {
        "batman-kavach2": _unit_active("batman-kavach2.service"),
        "go_bot": _unit_active("go_bot.service"),
        "go_datafeeder": _unit_active("go_datafeeder.service"),
        "datafeedbot": _unit_active("datafeedbot.service"),
    }
    feeder_found, feeder_cpu, feeder_pid = _process_cpu(
        (
            "run_datafeedbot",
            "go_datafeeder",
            "datafeedbot",
            "run_datafeed",
            "dhan_feed",
        )
    )
    feeder_ok = units.get("go_datafeeder") == "active" or units.get("datafeedbot") == "active" or feeder_found
    return {
        "ok": True,
        "cpu_pct": cpu,
        "ram_pct": ram_pct,
        "ram_used_gb": ram_used,
        "ram_total_gb": ram_total,
        "disk_pct": disk_pct,
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "load": load,
        "units": units,
        "feeder_ok": bool(feeder_ok),
        "feeder_cpu_pct": feeder_cpu,
        "feeder_pid": feeder_pid,
        "feeder_unit": "go_datafeeder" if units.get("go_datafeeder") == "active" else "datafeedbot",
        "desk": "go",
    }


def build_desk_snapshot() -> dict[str, Any]:
    host = collect_host_health()
    go_ok = host.get("units", {}).get("go_bot") == "active"
    feeder_ok = bool(host.get("feeder_ok"))
    if go_ok:
        status = "RUNNING"
    elif feeder_ok:
        status = "FEED_ONLY"
    else:
        status = "DOWN"
    return {
        "ok": True,
        "ts": time.time(),
        "status": status,
        "paused": False,
        "deployment": False,
        "order_mode": "go",
        "day_pnl": None,
        "batman_pnl": None,
        "nifty": None,
        "nifty_ltp": None,
        "nifty_ok": False,
        "host": host,
        "copy": {
            "role": None,
            "allow_copy": False,
            "channel_on": False,
            "lots": None,
            "link_ok": None,
            "link_ms": None,
            "peer_name": None,
        },
        "subscription": {},
        "margin": {"ok": False, "available": None, "skipped": True},
        "partial": True,
        "desk": "go",
        "note": "GO health shim (Kavach down)",
    }


async def api_host_health(request: Request) -> Response:
    if not _auth_ok(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return JSONResponse(collect_host_health())


async def api_desk_snapshot(request: Request) -> Response:
    if not _auth_ok(request):
        return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)
    return JSONResponse(build_desk_snapshot())


async def api_ping(request: Request) -> Response:
    return JSONResponse({"ok": True, "service": "go-fleet-health", "ts": time.time()})


app = Starlette(
    routes=[
        Route("/", api_ping),
        Route("/api/ping", api_ping),
        Route("/api/host-health", api_host_health),
        Route("/api/fleet/desk-snapshot", api_desk_snapshot),
    ]
)


def main() -> None:
    import uvicorn

    host = (os.environ.get("GO_FLEET_HEALTH_HOST") or "0.0.0.0").strip()
    port = int(os.environ.get("GO_FLEET_HEALTH_PORT") or "8789")
    if not _read_copy_key():
        print("WARN: no copy key found; desk-snapshot will 401", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
