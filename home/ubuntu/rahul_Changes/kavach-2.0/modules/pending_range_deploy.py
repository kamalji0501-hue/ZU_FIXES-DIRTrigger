"""Always-on watcher: first time Nifty is inside the armed band, run Confirm Deploy and Register once."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger("batman.pending_range_deploy.watch")

_STOP: threading.Event | None = None
_THREAD: threading.Thread | None = None
_POLL_SEC = 2.0


def start_pending_range_deploy_watcher() -> None:
    global _STOP, _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        logger.info("pending range deploy watcher already running")
        return
    _STOP = threading.Event()
    _THREAD = threading.Thread(
        target=_loop,
        name="pending-range-deploy",
        daemon=True,
    )
    _THREAD.start()
    logger.info("pending range deploy watcher started")


def stop_pending_range_deploy_watcher() -> None:
    global _STOP, _THREAD
    if _STOP is not None:
        _STOP.set()
    t = _THREAD
    if t is not None and t.is_alive():
        t.join(timeout=4.0)
    _STOP = None
    _THREAD = None
    logger.info("pending range deploy watcher stopped")


def _loop() -> None:
    assert _STOP is not None
    while not _STOP.is_set():
        try:
            _tick()
        except Exception as exc:
            logger.warning("pending range deploy tick failed: %s", exc)
        if _STOP.wait(_POLL_SEC):
            return


def _tick() -> None:
    from core.pending_range_deploy import (
        mark_done,
        mark_failed,
        resolve_nifty_spot,
        snapshot_pending,
        try_claim_fire,
    )

    pending = snapshot_pending()
    if not pending:
        return
    status = str(pending.get("status") or "")
    if status not in {"armed", "firing"}:
        return

    paused = False
    try:
        from web.runtime import get_runtime

        rt = get_runtime()
        if rt is not None and rt.state is not None:
            paused = bool(rt.state.get("algo.paused", False))
    except Exception:
        paused = False

    spot = resolve_nifty_spot()
    payload = try_claim_fire(spot, paused=paused)
    if not payload:
        return
    _fire(payload)


def _fire(payload: dict[str, Any]) -> None:
    from core.pending_range_deploy import mark_done, mark_failed

    logger.info("pending range deploy punching Confirm Deploy and Register (one shot)")
    try:
        from web.arm import deploy_and_register_batman

        out = deploy_and_register_batman(dict(payload or {}))
    except Exception as exc:
        mark_failed(str(exc))
        return
    if not isinstance(out, dict) or not out.get("ok"):
        err = str((out or {}).get("error") or (out or {}).get("text") or "Deploy at range failed.")
        mark_failed(err, out if isinstance(out, dict) else None)
        return
    mark_done(out)
    try:
        from modules.copy_trading import schedule_copy

        body = dict(payload or {})
        if not body.get("strategy"):
            body["strategy"] = "directional"
        schedule_copy("DEPLOY_REGISTER", body, "Deploy and register")
    except Exception as exc:
        logger.warning("range-deploy copy emit failed: %s", exc)
