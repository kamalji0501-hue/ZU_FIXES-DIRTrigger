"""Background poller + in-memory Command Center snapshot (up to 10 instances).

Cards are driven by the Licenses Google Sheet API (action=list) in sheet row order.
Optional instance_registry.json only supplies overrides (local flag, copy_key_env).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from web.command.registry import ensure_registry_file, load_registry, registry_path
from web.fleet.registry import resolve_copy_key

logger = logging.getLogger("batman.kavach.command")

_LOCK = threading.Lock()
_SNAP: dict[str, Any] = {
    "ok": True,
    "instances": [],
    "slots": 15,
    "live_count": 0,
    "updated_at": 0.0,
}
_STARTED = False
_THREAD: threading.Thread | None = None
_LICENSE_LIST: list[dict[str, Any]] = []
_LICENSE_LIST_AT = 0.0
_LICENSE_BY_SID: dict[str, dict[str, Any]] = {}

# Command Center host public URL (local desk on this box)
_LOCAL_PUBLIC_IDS = {
    "http://3.6.39.208:8789",
    "http://3.6.39.208:8789/",
    # legacy Anand EC2 (pre-move)
    "http://3.6.138.217:8789",
    "http://3.6.138.217:8789/",
}


def get_snapshot() -> dict[str, Any]:
    with _LOCK:
        return json.loads(json.dumps(_SNAP, default=str))


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict | None = None,
    timeout: float = 4.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    hdrs = dict(headers or {})
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"raw": raw[:300]}
            if not isinstance(parsed, dict):
                parsed = {"data": parsed}
            return int(resp.status), parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"error": raw[:300]}
        if not isinstance(parsed, dict):
            parsed = {"error": str(parsed)}
        return int(exc.code), parsed
    except Exception as exc:
        return 0, {"ok": False, "error": str(exc)}


def _norm_sid(s: str) -> str:
    s = (s or "").strip()
    while s.endswith("/"):
        s = s[:-1]
    return s.lower()


def _subscription_env() -> dict[str, str]:
    path = Path("/home/ubuntu/Trading_Runtime_Rahul/Credentials/subscription/subscription.env")
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        for ln in path.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


def _date_short(v: Any) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    m = re.search(r"\b([A-Za-z]{3})\s+(\d{1,2})\s+(\d{4})\b", s)
    if m:
        months = {
            "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
            "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
        }
        mo = months.get(m.group(1))
        if mo:
            return f"{m.group(3)}-{mo}-{int(m.group(2)):02d}"
    return s


def _fetch_license_list(force: bool = False) -> list[dict[str, Any]]:
    """All Licenses-sheet rows in sheet order via ?action=list."""
    global _LICENSE_LIST, _LICENSE_LIST_AT, _LICENSE_BY_SID
    now = time.time()
    if not force and _LICENSE_LIST and (now - _LICENSE_LIST_AT) < 60:
        return _LICENSE_LIST
    cfg = _subscription_env()
    api = (cfg.get("SUBSCRIPTION_API_URL") or "").strip()
    key = (cfg.get("SUBSCRIPTION_API_KEY") or "").strip()
    if not api or not key:
        return _LICENSE_LIST
    params = urllib.parse.urlencode({"action": "list", "api_key": key})
    sep = "&" if "?" in api else "?"
    code, body = _http_json("GET", f"{api}{sep}{params}", timeout=15.0)
    if code != 200 or not body.get("ok"):
        logger.warning(
            "licenses action=list failed code=%s err=%s",
            code,
            body.get("error") or body,
        )
        return _LICENSE_LIST
    rows = body.get("subscriptions")
    if not isinstance(rows, list):
        return _LICENSE_LIST
    clean: list[dict[str, Any]] = []
    by_sid: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("server_id") or "").strip()
        if not sid:
            continue
        clean.append(row)
        by_sid[_norm_sid(sid)] = row
    _LICENSE_LIST = clean
    _LICENSE_BY_SID = by_sid
    _LICENSE_LIST_AT = now
    logger.info("licenses list ok count=%s", len(clean))
    return clean


def _registry_overrides(reg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map normalized server_id → override entry from registry."""
    out: dict[str, dict[str, Any]] = {}
    for entry in reg.get("instances") or []:
        if not isinstance(entry, dict):
            continue
        for key in ("license_server_id", "server_id", "base_url"):
            val = str(entry.get(key) or "").strip()
            if val and "127.0.0.1" not in val and "localhost" not in val:
                out[_norm_sid(val)] = entry
                break
    # explicit overrides map
    ov = reg.get("overrides")
    if isinstance(ov, dict):
        for k, v in ov.items():
            if isinstance(v, dict):
                out[_norm_sid(str(k))] = {**out.get(_norm_sid(str(k)), {}), **v}
    return out


def _is_local(server_id: str, override: dict[str, Any], reg: dict[str, Any]) -> bool:
    if override.get("local") is True:
        return True
    sid_n = _norm_sid(server_id)
    if sid_n in {_norm_sid(x) for x in _LOCAL_PUBLIC_IDS}:
        return True
    for x in reg.get("local_server_ids") or []:
        if _norm_sid(str(x)) == sid_n:
            return True
    return False


def _entries_from_licenses(reg: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build poll entries from Licenses API sheet order. None = list unavailable."""
    rows = _fetch_license_list(force=False)
    if not rows:
        # Distinguish empty sheet vs API missing: if never loaded, fall back
        if _LICENSE_LIST_AT <= 0:
            return None
        return []
    overrides = _registry_overrides(reg)
    entries: list[dict[str, Any]] = []
    for i, lic in enumerate(rows):
        sid = str(lic.get("server_id") or "").strip()
        if not sid:
            continue
        # Skip blocked rows for card grid (still counted in API)
        status = str(lic.get("status") or "ACTIVE").strip().upper()
        if status in ("BLOCKED", "REVOKED", "DISABLED"):
            continue
        ov = overrides.get(_norm_sid(sid), {})
        local = _is_local(sid, ov, reg)
        # poll URL may differ from Licenses Server ID (e.g. GO health on :81)
        poll = str(ov.get("poll_url") or ov.get("base_url") or "").strip().rstrip("/")
        if local:
            base = "http://127.0.0.1:8789"
        elif poll:
            base = poll
        else:
            base = sid.rstrip("/")
        entry = {
            "id": ov.get("id") or f"lic-{i + 1}",
            "label": lic.get("name") or ov.get("label") or f"Instance {i + 1}",
            "slot": i + 1,
            "base_url": base,
            "license_server_id": sid if sid.endswith("/") else sid + "/",
            "server_tag": str(lic.get("serial_number") or (i + 1)),
            "aws_account": lic.get("server_alias") or ov.get("aws_account") or "",
            "link_type": "local" if local else (ov.get("link_type") or "public"),
            "local": local,
            "enabled": True,
            "copy_key_env": ov.get("copy_key_env") or "",
            "_license": lic,
        }
        entries.append(entry)
    return entries


def _fetch_license_row(server_id: str) -> dict[str, Any] | None:
    """Single-row Licenses lookup (fallback when action=list is not deployed yet)."""
    sid = _norm_sid(server_id)
    if sid in _LICENSE_BY_SID:
        return _LICENSE_BY_SID.get(sid)
    cfg = _subscription_env()
    api = (cfg.get("SUBSCRIPTION_API_URL") or "").strip()
    key = (cfg.get("SUBSCRIPTION_API_KEY") or "").strip()
    if not api or not key or not sid:
        return None
    want = server_id if str(server_id).endswith("/") else str(server_id).rstrip("/") + "/"
    params = urllib.parse.urlencode({"server_id": want, "api_key": key})
    sep = "&" if "?" in api else "?"
    code, body = _http_json("GET", f"{api}{sep}{params}", timeout=5.0)
    if code != 200 or not body.get("ok"):
        return None
    sub = body.get("subscription")
    if not isinstance(sub, dict):
        return None
    _LICENSE_BY_SID[sid] = sub
    return sub


def _license_for_entry(entry: dict[str, Any]) -> dict[str, Any] | None:
    lic = entry.get("_license")
    if isinstance(lic, dict):
        return lic
    return _fetch_license_row(_license_server_id(entry))


def _license_server_id(entry: dict[str, Any]) -> str:
    for key in ("license_server_id", "server_id", "base_url"):
        val = str(entry.get(key) or "").strip()
        if val and "127.0.0.1" not in val and "localhost" not in val:
            return val if val.endswith("/") else (val + "/")
    return "http://3.6.39.208:8789/"


def _entries_from_registry_fallback(reg: dict[str, Any]) -> list[dict[str, Any]]:
    """When action=list is not live yet, build cards from registry overrides + Server IDs."""
    entries: list[dict[str, Any]] = []
    for i, raw in enumerate(reg.get("instances") or []):
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            continue
        # License Server ID must match the Google Sheet (Auth / lots / dates).
        sid = str(raw.get("license_server_id") or raw.get("server_id") or "").strip()
        poll = str(raw.get("poll_url") or raw.get("base_url") or "").strip()
        if not sid:
            sid = poll
        if not sid:
            continue
        local = _is_local(sid, raw, reg)
        if local:
            base = "http://127.0.0.1:8789"
        elif poll:
            base = poll.rstrip("/")
        else:
            base = sid.rstrip("/")
        entries.append(
            {
                "id": raw.get("id") or f"reg-{i + 1}",
                "label": raw.get("label") or raw.get("id") or f"Instance {i + 1}",
                "slot": int(raw.get("slot") or (i + 1)),
                "base_url": base,
                "license_server_id": sid if sid.endswith("/") else sid + "/",
                "server_tag": str(raw.get("server_tag") or (i + 1)),
                "aws_account": raw.get("aws_account") or "",
                "link_type": "local" if local else (raw.get("link_type") or "public"),
                "local": local,
                "enabled": True,
                "copy_key_env": raw.get("copy_key_env") or "",
            }
        )
    return sorted(entries, key=lambda e: int(e.get("slot") or 999))


def _normalize(
    entry: dict[str, Any],
    snap: dict[str, Any],
    *,
    link_status: str,
    reachable: bool,
    source: str,
    error: str | None = None,
) -> dict[str, Any]:
    host = snap.get("host") or {}
    copy = snap.get("copy") or {}
    sub = dict(snap.get("subscription") or {})
    lic = _license_for_entry(entry)
    if lic:
        sub = {
            **sub,
            "max_sell_lots_batman": lic.get("max_sell_lots_batman"),
            "max_ato_lots_batman": lic.get("max_ato_lots_batman"),
            "max_sell_lots_directional": lic.get("max_sell_lots_directional"),
            "max_ato_lots_directional": lic.get("max_ato_lots_directional"),
            "ui_status": lic.get("status") or sub.get("ui_status"),
            "start_date": _date_short(lic.get("start_date")) or sub.get("start_date"),
            "end_date": _date_short(lic.get("end_date")) or sub.get("end_date"),
            "name": lic.get("name") or sub.get("name"),
            "server_alias": lic.get("server_alias") or sub.get("server_alias"),
            "serial_number": lic.get("serial_number"),
        }
    status = str(snap.get("status") or ("UNREACHABLE" if not reachable else "UNKNOWN"))
    allow = copy.get("allow_copy")
    channel = copy.get("channel_on")
    copy_on = bool(allow) and (channel is not False)
    batman_sell = sub.get("max_sell_lots_batman")
    batman_ato = sub.get("max_ato_lots_batman")
    dir_sell = sub.get("max_sell_lots_directional")
    dir_ato = sub.get("max_ato_lots_directional")
    # Back-compat aliases used by older UI
    batman = batman_sell
    directional = dir_sell if dir_sell is not None else dir_ato
    slot = entry.get("slot")
    server_tag = str(entry.get("server_tag") or slot or "")
    label = entry.get("label") or (lic or {}).get("name") or entry.get("id")
    aws_account = entry.get("aws_account") or (lic or {}).get("server_alias") or ""
    return {
        "id": entry.get("id"),
        "label": label,
        "slot": slot,
        "server_tag": server_tag,
        "aws_account": aws_account,
        "link_type": entry.get("link_type") or "unknown",
        "base_url": entry.get("base_url") or "",
        "reachable": reachable,
        "link_status": link_status,
        "status": status,
        "paused": snap.get("paused"),
        "order_mode": snap.get("order_mode"),
        "day_pnl": snap.get("day_pnl"),
        "cpu_pct": host.get("cpu_pct"),
        "ram_pct": host.get("ram_pct"),
        "disk_pct": host.get("disk_pct"),
        "feeder_ok": host.get("feeder_ok"),
        "feeder_cpu_pct": host.get("feeder_cpu_pct"),
        "feeder_unit": host.get("feeder_unit"),
        "copy_on": copy_on,
        "batman_lots": batman,
        "directional_lots": directional,
        "batman_sell_lots": batman_sell,
        "batman_ato_lots": batman_ato,
        "directional_sell_lots": dir_sell,
        "directional_ato_lots": dir_ato,
        "subscription_status": sub.get("ui_status"),
        "subscription_start": sub.get("start_date"),
        "subscription_end": sub.get("end_date"),
        "partial": bool(snap.get("partial")),
        "source": source,
        "error": error or snap.get("error"),
        "updated_at": snap.get("ts") or time.time(),
        "empty": False,
    }


def _local(entry: dict[str, Any], want_margin: bool) -> dict[str, Any]:
    from web.fleet.desk_export import build_desk_snapshot

    snap = build_desk_snapshot(include_margin=True, force_margin=want_margin)
    return _normalize(entry, snap, link_status="UP", reachable=True, source="local")


def _remote(entry: dict[str, Any], want_margin: bool) -> dict[str, Any]:
    base = str(entry.get("base_url") or "").rstrip("/")
    if not base:
        return _normalize(
            entry,
            {"ok": False, "status": "UNREACHABLE", "host": {}, "copy": {}, "subscription": {}},
            link_status="DOWN",
            reachable=False,
            source="no_url",
            error="missing base_url",
        )
    key = resolve_copy_key(entry)
    headers = {"X-Copy-Key": key, "X-Copy-Vps-Id": "command-center"}
    url = f"{base}/api/fleet/desk-snapshot?margin=1"
    if want_margin:
        url += "&force=1"
    code, body = _http_json("GET", url, headers=headers, timeout=4.0)
    if code == 200 and body.get("ok"):
        return _normalize(entry, body, link_status="UP", reachable=True, source="desk-snapshot")
    err = body.get("error") or f"http_{code}"
    # Still show Authorization from Licenses sheet even if desk metrics fail
    return _normalize(
        entry,
        {"ok": False, "status": "UNREACHABLE", "host": {}, "copy": {}, "subscription": {}},
        link_status="DOWN",
        reachable=False,
        source="error",
        error=str(err),
    )


def _empty_slot(slot: int) -> dict[str, Any]:
    return {
        "id": f"slot-{slot}",
        "label": f"Instance {slot}",
        "slot": slot,
        "empty": True,
        "reachable": False,
        "link_status": "EMPTY",
        "status": "EMPTY",
    }


def refresh_once(force_margin: bool = False) -> dict[str, Any]:
    global _LICENSE_LIST_AT
    reg = load_registry()
    poll = reg.get("poll") or {}
    margin_sec = float(poll.get("margin_sec") or 300)
    slots = int(reg.get("slots") or 15)
    with _LOCK:
        last_m = float(_SNAP.get("last_margin_poll") or 0)
    want_m = force_margin or ((time.time() - last_m) >= margin_sec)

    if force_margin:
        # Drop cached Licenses rows so Sub/lots/dates re-read from the sheet API
        _LICENSE_LIST_AT = 0.0
        _LICENSE_LIST.clear()
        _LICENSE_BY_SID.clear()

    # Card order = instance_registry.json slots (Licenses sheet sequence you set).
    # Optional action=list is off unless source=licenses_api explicitly.
    source_mode = str(reg.get("source") or "registry").strip().lower()
    entries = None
    if source_mode == "licenses_api":
        entries = _entries_from_licenses(reg)
    if entries is None:
        source_mode = "registry"
        entries = _entries_from_registry_fallback(reg)

    live_rows: list[dict[str, Any]] = []
    for entry in entries[:slots]:
        try:
            if entry.get("local"):
                row = _local(entry, want_m)
            else:
                row = _remote(entry, want_m)
        except Exception as exc:
            logger.exception("command instance poll failed id=%s", entry.get("id"))
            row = _normalize(
                entry,
                {"ok": False, "status": "UNREACHABLE", "host": {}, "copy": {}, "subscription": {}},
                link_status="DOWN",
                reachable=False,
                source="exception",
                error=str(exc),
            )
        live_rows.append(row)

    grid: list[dict[str, Any] | None] = [None] * slots
    for row in live_rows:
        try:
            s = int(row.get("slot") or 0)
        except Exception:
            s = 0
        if 1 <= s <= slots and grid[s - 1] is None:
            grid[s - 1] = row
        else:
            for i in range(slots):
                if grid[i] is None:
                    row = dict(row)
                    row["slot"] = i + 1
                    grid[i] = row
                    break
    instances = [grid[i] if grid[i] is not None else _empty_slot(i + 1) for i in range(slots)]
    live_count = sum(1 for r in instances if not r.get("empty") and r.get("reachable"))

    out = {
        "ok": True,
        "instances": instances,
        "slots": slots,
        "live_count": live_count,
        "registered_count": len(live_rows),
        "source": source_mode,
        "licenses_count": len(_LICENSE_LIST),
        "updated_at": time.time(),
        "last_margin_poll": time.time() if want_m else last_m,
        "poll": {"state_sec": poll.get("state_sec", 30), "margin_sec": margin_sec},
    }
    with _LOCK:
        _SNAP.clear()
        _SNAP.update(out)
    return get_snapshot()


def _loop() -> None:
    while True:
        try:
            reg = load_registry()
            state_sec = max(10, int((reg.get("poll") or {}).get("state_sec") or 30))
            refresh_once(force_margin=False)
            time.sleep(state_sec)
        except Exception:
            logger.exception("command aggregator loop error")
            time.sleep(15)


def _resolved_entries() -> list[dict[str, Any]]:
    reg = load_registry()
    source_mode = str(reg.get("source") or "registry").strip().lower()
    entries = None
    if source_mode == "licenses_api":
        entries = _entries_from_licenses(reg)
    if entries is None:
        entries = _entries_from_registry_fallback(reg)
    return entries or []


def _entry_by_id(inst_id: str) -> dict[str, Any] | None:
    want = (inst_id or "").strip()
    if not want:
        return None
    for entry in _resolved_entries():
        if str(entry.get("id") or "") == want:
            return dict(entry)
    return None


def _fetch_pnl_split_for_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Call desk /api/fleet/desk-pnl-split (local import or remote HTTP)."""
    eid = str(entry.get("id") or "")
    label = str(entry.get("label") or eid)
    try:
        if entry.get("local"):
            from core.day_pnl_cache import booked_running_pnl
            from web.runtime import get_runtime

            broker = None
            try:
                rt = get_runtime()
                broker = getattr(rt, "broker", None) if rt is not None else None
            except Exception:
                broker = None
            out = booked_running_pnl(refresh=True, broker=broker)
            out["id"] = eid
            out["label"] = label
            return out

        base = str(entry.get("base_url") or entry.get("license_server_id") or "").rstrip("/")
        if not base:
            # Registry may only store license_server_id
            base = str(entry.get("license_server_id") or "").rstrip("/")
        if not base:
            return {"ok": False, "id": eid, "label": label, "error": "missing base_url"}
        key = resolve_copy_key(entry)
        headers = {"X-Copy-Key": key, "X-Copy-Vps-Id": "command-center"}
        url = f"{base}/api/fleet/desk-pnl-split?refresh=1"
        code, body = _http_json("GET", url, headers=headers, timeout=6.0)
        if code == 200 and body.get("ok"):
            body = dict(body)
            body["id"] = eid
            body["label"] = label
            return body
        err = body.get("error") or f"http_{code}"
        if code == 404:
            err = "desk needs update (no desk-pnl-split)"
        return {"ok": False, "id": eid, "label": label, "error": str(err)}
    except Exception as exc:
        logger.exception("desk pnl split failed id=%s", eid)
        return {"ok": False, "id": eid, "label": label, "error": str(exc)}


def fetch_desk_pnl_split(inst_id: str) -> dict[str, Any]:
    entry = _entry_by_id(inst_id)
    if not entry:
        return {"ok": False, "error": "unknown instance", "id": inst_id}
    return _fetch_pnl_split_for_entry(entry)


def fetch_all_desk_pnl_splits(*, concurrency: int = 4) -> dict[str, Any]:
    """Fan-out booked/running fetch to all non-empty UP desks."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    snap = get_snapshot()
    up_ids = {
        str(r.get("id") or "")
        for r in (snap.get("instances") or [])
        if (not r.get("empty")) and r.get("reachable") and r.get("id")
    }
    entries = [e for e in _resolved_entries() if str(e.get("id") or "") in up_ids]

    results: dict[str, Any] = {}
    if not entries:
        return {"ok": True, "results": results, "count": 0}

    workers = max(1, min(int(concurrency or 4), len(entries)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch_pnl_split_for_entry, e): e for e in entries}
        for fut in as_completed(futs):
            out = fut.result()
            rid = str(out.get("id") or "")
            if rid:
                results[rid] = out
    return {"ok": True, "results": results, "count": len(results)}


_BROADCAST_LOCK = threading.Lock()
_LAST_BROADCAST_AT = 0.0
_BROADCAST_MIN_GAP_S = 30.0


def _deliver_operator_notice(
    entry: dict[str, Any],
    *,
    text: str,
    severity: str,
    filename: str,
    content_b64: str,
    content_type: str,
) -> dict[str, Any]:
    eid = str(entry.get("id") or "")
    label = str(entry.get("label") or eid)
    try:
        if entry.get("local"):
            from web.fleet.operator_notice import receive_operator_notice

            out = receive_operator_notice(
                text=text,
                severity=severity,
                filename=filename,
                content_type=content_type,
                content_b64=content_b64,
            )
            out = dict(out)
            out["id"] = eid
            out["label"] = label
            return out

        base = str(entry.get("base_url") or entry.get("license_server_id") or "").rstrip("/")
        if not base:
            return {"ok": False, "id": eid, "label": label, "error": "missing base_url"}
        key = resolve_copy_key(entry)
        headers = {"X-Copy-Key": key, "X-Copy-Vps-Id": "command-center"}
        body = {
            "text": text,
            "severity": severity,
            "filename": filename,
            "content_type": content_type,
            "content_b64": content_b64,
        }
        url = f"{base}/api/fleet/operator-notice"
        code, resp = _http_json("POST", url, headers=headers, body=body, timeout=12.0)
        if code == 200 and resp.get("ok"):
            resp = dict(resp)
            resp["id"] = eid
            resp["label"] = label
            return resp
        err = resp.get("error") or f"http_{code}"
        if code == 404:
            err = "desk needs update (no operator-notice)"
        return {"ok": False, "id": eid, "label": label, "error": str(err)}
    except Exception as exc:
        logger.exception("operator notice failed id=%s", eid)
        return {"ok": False, "id": eid, "label": label, "error": str(exc)}


def broadcast_operator_notice(
    *,
    text: str,
    severity: str = "orange",
    filename: str = "",
    content_b64: str = "",
    content_type: str = "",
    desk_ids: list[str] | None = None,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Fan-out a Command Center notice (+ optional file) to selected (or all) desks."""
    global _LAST_BROADCAST_AT
    msg = str(text or "").strip()
    if not msg:
        return {"ok": False, "error": "empty_message"}
    with _BROADCAST_LOCK:
        now = time.time()
        gap = now - _LAST_BROADCAST_AT
        if _LAST_BROADCAST_AT and gap < _BROADCAST_MIN_GAP_S:
            wait = int(_BROADCAST_MIN_GAP_S - gap) + 1
            return {"ok": False, "error": f"wait_{wait}s_before_next_broadcast"}
        _LAST_BROADCAST_AT = now

    from concurrent.futures import ThreadPoolExecutor, as_completed

    entries = [e for e in _resolved_entries() if e.get("enabled", True)]
    if desk_ids is not None:
        want = {str(x).strip() for x in desk_ids if str(x).strip()}
        if not want:
            return {"ok": False, "error": "no_desks_selected"}
        entries = [e for e in entries if str(e.get("id") or "") in want]
        if not entries:
            return {"ok": False, "error": "no_matching_desks"}
    results: list[dict[str, Any]] = []
    if not entries:
        return {"ok": True, "results": results, "ok_count": 0, "fail_count": 0}

    workers = max(1, min(int(concurrency or 4), len(entries)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                _deliver_operator_notice,
                e,
                text=msg,
                severity=severity or "orange",
                filename=filename or "",
                content_b64=content_b64 or "",
                content_type=content_type or "",
            )
            for e in entries
        ]
        for fut in as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: str(r.get("label") or r.get("id") or ""))
    ok_count = sum(1 for r in results if r.get("ok"))
    fail_count = len(results) - ok_count
    return {
        "ok": True,
        "results": results,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "count": len(results),
    }


def start_aggregator() -> None:
    global _STARTED, _THREAD
    if _STARTED:
        return
    force = (os.environ.get("COMMAND_ENABLE_AGGREGATOR") or "").strip() == "1"
    path = registry_path()
    cfg = _subscription_env()
    has_license_api = bool(cfg.get("SUBSCRIPTION_API_URL") and cfg.get("SUBSCRIPTION_API_KEY"))
    if not force and not path.is_file() and not has_license_api:
        logger.info("command aggregator skipped (no registry and no license API)")
        return
    if path.parent.is_dir():
        ensure_registry_file()
    _STARTED = True
    _THREAD = threading.Thread(target=_loop, name="command-aggregator", daemon=True)
    _THREAD.start()
    logger.info("command aggregator started (licenses_api=%s)", has_license_api)
