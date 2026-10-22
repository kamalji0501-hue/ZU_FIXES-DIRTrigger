"""Dhan positions fetch + NIFTY option filtering (KAVACH /register wizard)."""

from __future__ import annotations

import logging
import math
import re
from datetime import date
from typing import Any

import httpx
import pandas as pd

from core.exceptions import BrokerAuthError, PositionError

logger = logging.getLogger("batman.positions")

_DHAN_POSITIONS_URL = "https://api.dhan.co/v2/positions"


def _extract_dhan_error(response: httpx.Response) -> str:
    detail = response.text.strip()
    try:
        payload = response.json()
        if isinstance(payload, dict):
            remarks = payload.get("remarks")
            if isinstance(remarks, dict):
                return str(remarks.get("error_message") or remarks)
            if isinstance(remarks, str):
                return remarks
    except Exception:
        pass
    return str(detail)[:240]


_DH906_LOCK = __import__("threading").Lock()
_DH906_LAST = 0.0


def _is_invalid_dhan_token(exc: BaseException) -> bool:
    text = str(exc)
    return "DH-906" in text or "Invalid Token" in text


def _recover_invalid_dhan_token() -> str:
    """Mint a fresh JWT once, persist it, and hot-reload the running broker."""
    global _DH906_LAST
    import time

    with _DH906_LOCK:
        now = time.time()
        if now - _DH906_LAST < 130:
            raise PositionError(
                "Dhan token invalid (DH-906); wait 2 minutes before another refresh."
            )
        _DH906_LAST = now
        from core.dhan_totp import load_credentials, renew_and_save

        creds = load_credentials()
        if not getattr(creds, "configured", False):
            raise PositionError(
                "Dhan token invalid (DH-906) and PIN/TOTP is not configured."
            )
        token = renew_and_save()
        try:
            from web.runtime import get_runtime

            rt = get_runtime()
            broker = getattr(rt, "broker", None) if rt else None
            if broker is not None and hasattr(broker, "hot_reload_token"):
                cc = str(getattr(broker, "_client_code", "") or creds.client_code or "")
                broker.hot_reload_token(cc, token)
        except Exception as exc:
            logger.warning("DH-906 remint saved but broker hot-reload skipped: %s", exc)
        logger.warning("Dhan DH-906 recovered — new JWT persisted and broker reloaded")
        return token


def _fetch_positions_rest_once(client_code: str, access_token: str) -> pd.DataFrame:
    if not client_code or not access_token:
        raise BrokerAuthError("Client ID or access token is missing.")

    try:
        response = httpx.get(
            _DHAN_POSITIONS_URL,
            headers={"access-token": access_token, "client-id": client_code},
            timeout=20.0,
        )
    except Exception as exc:
        raise PositionError(f"Could not reach Dhan positions API: {exc}") from exc

    if response.status_code != 200:
        raise PositionError(
            f"Dhan positions API HTTP {response.status_code}: {_extract_dhan_error(response)}"
        )

    payload = response.json()
    if not isinstance(payload, list):
        raise PositionError(f"Unexpected positions payload type: {type(payload).__name__}")

    return pd.DataFrame(payload)


def fetch_positions_rest(client_code: str, access_token: str) -> pd.DataFrame:
    """Fetch open positions via Dhan REST (read-only). Remint once on DH-906."""
    try:
        return _fetch_positions_rest_once(client_code, access_token)
    except PositionError as exc:
        if not _is_invalid_dhan_token(exc):
            raise
        logger.warning("Dhan positions DH-906 — reminting JWT and retrying once")
        token = _recover_invalid_dhan_token()
        return _fetch_positions_rest_once(client_code, token)


def parse_position_expiry(row: pd.Series | dict[str, Any], symbol: str) -> str:
    """Best-effort expiry label from Dhan/Kite row or tradingSymbol (dynamic weekly)."""
    if hasattr(row, "get"):
        label = row.get("expiryLabel")
        if label:
            return str(label)
        kite_exp = row.get("expiry")
        if kite_exp:
            text = str(kite_exp)[:10]
            if len(text) == 10 and text[4] == "-":
                try:
                    return date.fromisoformat(text).strftime("%d %b %Y")
                except ValueError:
                    pass
            return str(kite_exp)
    drv_exp = row.get("drvExpiryDate") if hasattr(row, "get") else None
    if drv_exp:
        text = str(drv_exp)[:10]
        if len(text) == 10 and text[4] == "-":
            try:
                return date.fromisoformat(text).strftime("%d %b %Y")
            except ValueError:
                pass
        return text

    if symbol.startswith("NIFTY-"):
        parts = symbol.split("-")
        if len(parts) >= 4:
            from core.uat_position_enrich import format_expiry_display

            return format_expiry_display(parts[1])

    from core.zerodha_instruments import parse_kite_weekly_expiry

    weekly = parse_kite_weekly_expiry(symbol)
    if weekly is not None:
        from core.nifty_option_expiry import expiry_label_from_date

        return expiry_label_from_date(weekly)

    m = re.search(r"^NIFTY(\d{2}[A-Z]{3})", symbol)
    if m:
        return m.group(1)
    return "UNKNOWN"


def build_ato_protect_symbol(sell_symbol: str, protect_strike: int, opt_type: str) -> str:
    """Build ATO protect symbol in the same format as the sell leg."""
    opt_type = opt_type.upper()
    if sell_symbol.startswith("NIFTY-") and sell_symbol.endswith(f"-{opt_type}"):
        parts = sell_symbol.split("-")
        if len(parts) >= 4:
            parts[-2] = str(protect_strike)
            return "-".join(parts)

    compact = re.match(r"^([A-Z]+\d{2}[A-Z]{3})(\d+)(CE|PE)$", sell_symbol)
    if compact:
        return f"{compact.group(1)}{protect_strike}{opt_type}"
    weekly = re.match(r"^(NIFTY\d{5})(\d{4,5})(CE|PE)$", sell_symbol)
    if weekly:
        return f"{weekly.group(1)}{protect_strike}{opt_type}"

    return f"NIFTY-{protect_strike}-{opt_type}"


def filter_nifty_positions(positions_df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Filter broker positions DataFrame to NIFTY options only.

    Returns list of dicts: symbol, strike, opt_type, direction, qty,
    avg_price, instrument_token, expiry.
    """
    results: list[dict[str, Any]] = []
    if positions_df is None or (hasattr(positions_df, "empty") and positions_df.empty):
        return results

    for _, row in positions_df.iterrows():
        symbol = str(row.get("tradingSymbol") or row.get("tradingsymbol", ""))
        if not symbol.startswith("NIFTY"):
            continue

        opt_type = None
        if symbol.endswith("CE"):
            opt_type = "CE"
        elif symbol.endswith("PE"):
            opt_type = "PE"
        else:
            continue

        net_qty = int(row.get("netQty", 0) or row.get("quantity", 0) or 0)
        if net_qty == 0:
            continue

        direction = "LONG" if net_qty > 0 else "SHORT"

        try:
            avg_price = float(
                row.get("avgPrice")
                or row.get("average_price")
                or row.get("avgCostPrice")
                or row.get("buyAvg")
                or row.get("costPrice")
                or row.get("sellAvg")
                or 0
            )
        except (TypeError, ValueError):
            avg_price = 0.0
        if math.isnan(avg_price) or math.isinf(avg_price):
            avg_price = 0.0

        m = re.search(r"-(\d{4,5})-(CE|PE)$", symbol, re.I)
        if not m:
            m = re.search(r"(\d{4,5})(CE|PE)$", symbol.replace("-", ""), re.I)
        if m:
            strike = int(m.group(1))
        else:
            try:
                strike = int(float(row.get("drvStrikePrice") or 0))
            except (TypeError, ValueError):
                strike = 0

        expiry = parse_position_expiry(row, symbol)

        from core.uat_position_enrich import format_position_symbol_display

        results.append(
            {
                "symbol": symbol,
                "display_symbol": format_position_symbol_display(symbol, expiry),
                "strike": strike,
                "opt_type": opt_type,
                "direction": direction,
                "qty": abs(net_qty),
                "avg_price": round(avg_price, 2) if avg_price > 0 else 0.0,
                "instrument_token": str(row.get("securityId") or row.get("instrumentToken") or row.get("instrument_token") or ""),
                "expiry": expiry,
            }
        )

    results.sort(key=lambda x: (x["strike"], x["opt_type"]))
    return results


def format_position_summary(positions: list[dict[str, Any]]) -> str:
    """Plain-text summary for CLI / Telegram."""
    if not positions:
        return "No open NIFTY option positions."

    lines = [f"Open NIFTY options: {len(positions)}"]
    for pos in positions:
        sym = pos.get("display_symbol") or pos["symbol"]
        px = pos.get("avg_price", 0)
        px_txt = f"₹{px:.2f}" if px and not math.isnan(float(px)) else "₹—"
        lines.append(
            f"• {sym} | {pos['direction']} {pos['qty']} | "
            f"strike {pos['strike']} | avg {px_txt}"
        )
    return "\n".join(lines)
