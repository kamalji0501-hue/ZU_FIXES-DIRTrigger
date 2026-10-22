"""One-shot Directional Deploy arm: punch Confirm Deploy and Register when Nifty is in range.

Pending file lives under runtime shared data. Status machine:

    armed -> firing -> done | failed
    armed -> expired (after 15:30 IST or next calendar day)
    armed -> (deleted on cancel)

The watcher claims ``armed -> firing`` atomically so a bouncing spot cannot
punch twice. Instant Confirm Deploy and Register may cancel only while
``armed`` (never while ``firing``).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, time
from pathlib import Path
from typing import Any

logger = logging.getLogger("batman.pending_range_deploy")

_LOCK = threading.RLock()
_STALE_FIRING_SEC = 180.0
_EXPIRE_AT = time(15, 30)

_STATUSES_ALL = frozenset({"armed", "firing", "done", "failed", "expired"})


def pending_path() -> Path:
    from core.batman_mode import shared_data_dir

    folder = shared_data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "pending_range_deploy.json"


def snapshot_pending() -> dict[str, Any] | None:
    rec = _read()
    if not rec:
        return None
    return _public(rec)


def parse_band(low: Any, high: Any) -> tuple[float, float] | str:
    """Two Nifty levels in any order become an inclusive min/max band."""
    try:
        a = float(low)
        b = float(high)
    except (TypeError, ValueError):
        return "Enter both Nifty From and Nifty To."
    if a <= 0 or b <= 0:
        return "Nifty From and To must be positive."
    if a == b:
        return "Enter two different Nifty levels so a range can be made."
    return (min(a, b), max(a, b))


def spot_in_band(spot: float, low: float, high: float) -> bool:
    return float(low) <= float(spot) <= float(high)


def should_expire(now: datetime, armed_on: str | None) -> bool:
    if now.time() >= _EXPIRE_AT:
        return True
    if armed_on and str(armed_on) != str(now.date()):
        return True
    return False


def arm_pending(
    payload: dict[str, Any],
    nifty_low: float,
    nifty_high: float,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    from core.utils import now_ist, today_ist

    now = now or now_ist()
    if should_expire(now, str(now.date())):
        err = "Range deploy can only be armed before 15:30 IST. It is not held overnight."
        return {"ok": False, "error": err, "text": err}

    view = str((payload or {}).get("view") or "").strip().lower()
    with _LOCK:
        cur = _read()
        cur_status = str((cur or {}).get("status") or "")
        if cur_status == "firing":
            return {
                "ok": False,
                "error": "A range deploy is already punching. Wait for it to finish.",
            }
        if cur_status == "armed":
            cur_view = str((cur or {}).get("view") or "")
            if cur_view and cur_view != view:
                return {
                    "ok": False,
                    "error": f"A {cur_view} range deploy is already armed. Cancel / Clear Arm first.",
                }
            return {
                "ok": False,
                "error": "Already armed. Use UPDATE RANGE or CANCEL / CLEAR ARM.",
            }
        rec = {
            "status": "armed",
            "view": view,
            "nifty_low": float(nifty_low),
            "nifty_high": float(nifty_high),
            "payload": dict(payload or {}),
            "armed_on": str(today_ist()),
            "armed_at": now_ist().isoformat(),
            "updated_at": now_ist().isoformat(),
            "fired_at": None,
            "error": None,
            "result_ok": None,
        }
        _write(rec)
    logger.info(
        "range-deploy ARMED view=%s band=[%s, %s] lots=%s expiry=%s",
        view,
        nifty_low,
        nifty_high,
        (payload or {}).get("lots"),
        (payload or {}).get("expiry"),
    )
    return {"ok": True, "text": "Armed. Confirm Deploy and Register will run once when Nifty is in range.", "pending_range_deploy": _public(rec)}


def update_pending_range(nifty_low: float, nifty_high: float) -> dict[str, Any]:
    from core.utils import now_ist

    with _LOCK:
        rec = _read()
        if not rec:
            return {"ok": False, "error": "Nothing is armed. Arm a range first."}
        status = str(rec.get("status") or "")
        if status == "firing":
            return {"ok": False, "error": "Punch already started. Range cannot be changed now."}
        if status != "armed":
            return {"ok": False, "error": "Range can only be changed while ARMED."}
        rec["nifty_low"] = float(nifty_low)
        rec["nifty_high"] = float(nifty_high)
        rec["updated_at"] = now_ist().isoformat()
        _write(rec)
    logger.info("range-deploy UPDATE band=[%s, %s]", nifty_low, nifty_high)
    return {"ok": True, "text": "Range updated. Still armed, still one-shot.", "pending_range_deploy": _public(rec)}


def cancel_pending(*, allow_firing: bool = False) -> dict[str, Any]:
    with _LOCK:
        rec = _read()
        if not rec:
            return {"ok": True, "text": "No armed range deploy to clear.", "pending_range_deploy": None}
        status = str(rec.get("status") or "")
        if status == "firing" and not allow_firing:
            return {"ok": False, "error": "Punch already started. Cannot cancel now."}
        _delete()
    logger.info("range-deploy CANCEL/CLEAR was status=%s", status)
    return {"ok": True, "text": "Armed range deploy cleared. No basket was punched.", "pending_range_deploy": None}


def cancel_if_armed() -> bool:
    """Clear a waiting arm so an instant deploy cannot double-punch. No-op if firing."""
    with _LOCK:
        rec = _read()
        if not rec:
            return False
        if str(rec.get("status") or "") != "armed":
            return False
        _delete()
        logger.info("range-deploy cancelled because an instant deploy started")
        return True


def try_claim_fire(spot: float | None, *, paused: bool, now: datetime | None = None) -> dict[str, Any] | None:
    """If this tick should punch, mark firing and return the deploy payload."""
    from core.utils import now_ist

    now = now or now_ist()
    with _LOCK:
        rec = _read()
        if not rec:
            return None
        status = str(rec.get("status") or "")
        if status == "firing":
            rec = _fail_stale_firing(rec, now)
            return None
        if status != "armed":
            return None
        if should_expire(now, rec.get("armed_on")):
            rec["status"] = "expired"
            rec["updated_at"] = now.isoformat()
            rec["error"] = "Expired at 15:30 IST. Not punched."
            _write(rec)
            logger.info("range-deploy EXPIRED without punch")
            return None
        if paused:
            return None
        if spot is None or float(spot) <= 0:
            return None
        low = float(rec.get("nifty_low") or 0)
        high = float(rec.get("nifty_high") or 0)
        if not spot_in_band(float(spot), low, high):
            return None
        rec["status"] = "firing"
        rec["fired_at"] = now.isoformat()
        rec["updated_at"] = now.isoformat()
        rec["spot_at_fire"] = float(spot)
        _write(rec)
        payload = dict(rec.get("payload") or {})
        logger.info(
            "range-deploy CLAIM FIRE spot=%s band=[%s, %s] view=%s",
            spot,
            low,
            high,
            rec.get("view"),
        )
        return payload


def mark_done(result: dict[str, Any] | None = None) -> None:
    from core.utils import now_ist

    with _LOCK:
        rec = _read()
        if not rec:
            return
        rec["status"] = "done"
        rec["result_ok"] = True
        rec["error"] = None
        rec["updated_at"] = now_ist().isoformat()
        rec["result_text"] = str((result or {}).get("text") or "")[:500]
        _write(rec)
    logger.info("range-deploy DONE")


def mark_failed(error: str, result: dict[str, Any] | None = None) -> None:
    from core.utils import now_ist

    with _LOCK:
        rec = _read()
        if not rec:
            return
        rec["status"] = "failed"
        rec["result_ok"] = False
        rec["error"] = str(error or "Deploy at range failed.")
        rec["updated_at"] = now_ist().isoformat()
        rec["result_text"] = str((result or {}).get("text") or rec["error"])[:500]
        _write(rec)
    logger.warning("range-deploy FAILED: %s", error)


def resolve_nifty_spot() -> float | None:
    try:
        from core.feeder_ipc import peek_index_ltp

        live = peek_index_ltp(wait_seconds=0.4)
        if live and float(live) > 0:
            return float(live)
    except Exception as exc:
        logger.debug("range-deploy peek_index_ltp failed: %s", exc)
    try:
        from core.nifty_ltp_feed import read_nifty_ltp_cache

        snap = read_nifty_ltp_cache()
        if snap is not None and float(snap.ltp) > 0:
            return float(snap.ltp)
    except Exception as exc:
        logger.debug("range-deploy cache ltp failed: %s", exc)
    return None


def _public(rec: dict[str, Any]) -> dict[str, Any]:
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    return {
        "status": str(rec.get("status") or ""),
        "view": str(rec.get("view") or ""),
        "nifty_low": rec.get("nifty_low"),
        "nifty_high": rec.get("nifty_high"),
        "lots": payload.get("lots"),
        "expiry": payload.get("expiry"),
        "level": payload.get("level"),
        "legs": list(payload.get("legs") or []),
        "armed_on": rec.get("armed_on"),
        "armed_at": rec.get("armed_at"),
        "updated_at": rec.get("updated_at"),
        "fired_at": rec.get("fired_at"),
        "spot_at_fire": rec.get("spot_at_fire"),
        "error": rec.get("error"),
        "result_ok": rec.get("result_ok"),
        "result_text": rec.get("result_text"),
    }


def _read() -> dict[str, Any] | None:
    path = pending_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("range-deploy read failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None
    status = str(data.get("status") or "")
    if status not in _STATUSES_ALL:
        return None
    return data


def _write(rec: dict[str, Any]) -> None:
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(rec, indent=2)
    fd, tmp = tempfile.mkstemp(prefix="pending_range_deploy.", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _delete() -> None:
    path = pending_path()
    try:
        path.unlink(missing_ok=True)
    except TypeError:
        if path.exists():
            path.unlink()


def _fail_stale_firing(rec: dict[str, Any], now: datetime) -> dict[str, Any]:
    raw = rec.get("fired_at") or rec.get("updated_at")
    if not raw:
        return rec
    try:
        started = datetime.fromisoformat(str(raw))
        if started.tzinfo is None:
            started = started.replace(tzinfo=now.tzinfo)
        age = (now - started).total_seconds()
    except Exception:
        return rec
    if age < _STALE_FIRING_SEC:
        return rec
    rec["status"] = "failed"
    rec["error"] = "Range deploy punch was interrupted. Not retried."
    rec["result_ok"] = False
    rec["updated_at"] = now.isoformat()
    _write(rec)
    logger.warning("range-deploy stale firing marked failed after %.0fs", age)
    return rec
