"""Kavach client for Datafeedbot Unix IPC (NIFTY index + option Bid/LTP)."""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("batman.feeder_ipc")

_DFB = Path("/home/ubuntu/Datafeedbot")
_SOCK_DEFAULT = Path("/home/ubuntu/Datafeedbot_Runtime/ipc/market.sock")

_LOCK = threading.Lock()
_SHARED: Any = None
_SHARED_PATH: Path | None = None


def _ensure_dfb_path() -> None:
    if _DFB.is_dir() and str(_DFB) not in sys.path:
        sys.path.insert(0, str(_DFB))


def socket_path(path: str | Path | None = None) -> Path:
    if path:
        return Path(path)
    try:
        _ensure_dfb_path()
        from datafeedbot.config import Settings

        return Path(Settings.load().ipc_socket)
    except Exception:
        return _SOCK_DEFAULT


def feeder_socket_ready(path: str | Path | None = None) -> bool:
    sock = socket_path(path)
    return sock.exists()


def _connect(path: str | Path | None = None):
    """Private one-shot client (collector / tests). Peeks use the singleton."""
    _ensure_dfb_path()
    from datafeedbot.ipc import IpcClient

    client = IpcClient(socket_path(path))
    client.connect(timeout=0.8)
    return client


def _drop_shared_locked() -> None:
    global _SHARED, _SHARED_PATH
    if _SHARED is not None:
        try:
            _SHARED.close()
        except Exception:
            pass
    _SHARED = None
    _SHARED_PATH = None


def _shared_client(path: str | Path | None = None):
    """Process-wide IpcClient: connect once, reuse, reconnect on error."""
    global _SHARED, _SHARED_PATH
    sock = socket_path(path)
    if _SHARED is not None and getattr(_SHARED, "connected", False) and _SHARED_PATH == sock:
        return _SHARED
    _drop_shared_locked()
    client = _connect(sock)
    _SHARED = client
    _SHARED_PATH = sock
    logger.info("IPC client connected clients=1 socket=%s (singleton reuse)", sock)
    return _SHARED


def peek_index_ltp(*, wait_seconds: float = 2.0, socket: str | Path | None = None) -> float | None:
    """Wait for a NIFTY_INDEX tick. Does not steal the option subscribe slot."""
    with _LOCK:
        try:
            client = _shared_client(socket)
        except Exception as exc:
            logger.debug("Feeder index connect failed: %s", exc)
            _drop_shared_locked()
            return None
        try:
            try:
                client.send_control("want", filter="index")
            except Exception:
                pass
            deadline = time.monotonic() + max(0.2, float(wait_seconds))
            while time.monotonic() < deadline:
                msg = client.recv(timeout=0.4)
                if not msg:
                    continue
                if msg.get("type") != "tick":
                    continue
                tick = msg.get("data") or {}
                if not isinstance(tick, dict):
                    continue
                inst = str(tick.get("instrument") or "")
                sid = str(tick.get("broker_id") or tick.get("security_id") or "")
                if inst != "NIFTY_INDEX" and sid != "13":
                    continue
                try:
                    ltp = float(tick.get("ltp") or 0)
                except (TypeError, ValueError):
                    continue
                if ltp > 0:
                    return ltp
            return None
        except Exception as exc:
            logger.debug("Feeder index peek failed: %s", exc)
            _drop_shared_locked()
            return None


def peek_option_quote(
    *,
    security_id: str = "",
    strike: int | None = None,
    option_type: str = "CE",
    expiry: str | None = None,
    wait_seconds: float = 3.0,
    socket: str | Path | None = None,
) -> dict[str, Any] | None:
    """Subscribe one option and wait for a fresh tick. Returns ltp/bid/ask.

    Pass expiry (ISO or label) so Shoonya resolve does not pick the wrong week.
    """
    sid = str(security_id or "").strip()
    opt = str(option_type or "CE").upper().strip() or "CE"
    try:
        strike_i = int(strike) if strike else 0
    except (TypeError, ValueError):
        strike_i = 0
    if not sid and strike_i <= 0:
        return None
    with _LOCK:
        try:
            client = _shared_client(socket)
        except Exception as exc:
            logger.warning("Feeder option connect failed: %s", exc)
            _drop_shared_locked()
            return None
        try:
            clearer = getattr(client, "clear_pending", None)
            if callable(clearer):
                try:
                    clearer()
                except Exception:
                    pass
            kwargs: dict[str, Any] = {
                "option_type": opt,
                "underlying": "NIFTY",
                "strike": strike_i,
            }
            if sid:
                kwargs["dhan_security_id"] = sid
            if expiry:
                kwargs["expiry"] = str(expiry).strip()
            try:
                client.send_control("subscribe", **kwargs)
            except Exception as exc:
                logger.warning("Feeder option subscribe failed: %s", exc)
                _drop_shared_locked()
                return None
            want = f"NIFTY_{strike_i}_{opt}" if strike_i else ""
            deadline = time.monotonic() + max(0.2, float(wait_seconds))
            while time.monotonic() < deadline:
                msg = client.recv(timeout=0.4)
                if not msg or msg.get("type") != "tick":
                    continue
                tick = msg.get("data") or {}
                if not isinstance(tick, dict):
                    continue
                inst = str(tick.get("instrument") or "")
                if inst == "NIFTY_INDEX":
                    continue
                if want and inst and inst != want:
                    continue
                tick_sid = str(
                    tick.get("dhan_security_id")
                    or tick.get("security_id")
                    or tick.get("broker_id")
                    or ""
                )
                if sid and tick_sid and tick_sid != sid:
                    continue
                try:
                    ltp = float(tick.get("ltp") or 0)
                except (TypeError, ValueError):
                    continue
                if ltp <= 0:
                    continue
                bid = tick.get("bid")
                ask = tick.get("ask")
                try:
                    bid_f = float(bid) if bid is not None else None
                except (TypeError, ValueError):
                    bid_f = None
                try:
                    ask_f = float(ask) if ask is not None else None
                except (TypeError, ValueError):
                    ask_f = None
                return {"ltp": ltp, "bid": bid_f, "ask": ask_f, "instrument": inst}
            logger.warning("Feeder option LTP wait timed out sid=%s strike=%s %s", sid, strike_i, opt)
            return None
        except Exception as exc:
            logger.warning("Feeder option peek failed: %s", exc)
            _drop_shared_locked()
            return None
