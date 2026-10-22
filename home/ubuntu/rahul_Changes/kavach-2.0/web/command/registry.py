"""Load Command Center instance registry (up to 15 slots / 5×3 grid)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def runtime_root() -> Path:
    env = (os.environ.get("TRADING_RUNTIME") or "").strip()
    if env:
        return Path(env)
    return Path("/home/ubuntu/Trading_Runtime_Rahul")


def registry_path() -> Path:
    return runtime_root() / "Data" / "data" / "shared" / "command" / "instance_registry.json"


def default_registry() -> dict[str, Any]:
    return {
        "slots": 15,
        "instances": [],
        "poll": {"state_sec": 30, "margin_sec": 300},
    }


def load_registry() -> dict[str, Any]:
    path = registry_path()
    if not path.is_file():
        return default_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return default_registry()
        data.setdefault("slots", 15)
        data.setdefault("instances", [])
        data.setdefault("poll", {"state_sec": 30, "margin_sec": 300})
        return data
    except Exception:
        return default_registry()


def iter_instances(reg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    reg = reg or load_registry()
    out: list[dict[str, Any]] = []
    for i, entry in enumerate(reg.get("instances") or []):
        if not isinstance(entry, dict):
            continue
        if entry.get("enabled") is False:
            continue
        row = dict(entry)
        row.setdefault("slot", i + 1)
        out.append(row)
    return out


def ensure_registry_file(seed: dict[str, Any] | None = None) -> Path:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(json.dumps(seed or default_registry(), indent=2) + "\n", encoding="utf-8")
    return path
