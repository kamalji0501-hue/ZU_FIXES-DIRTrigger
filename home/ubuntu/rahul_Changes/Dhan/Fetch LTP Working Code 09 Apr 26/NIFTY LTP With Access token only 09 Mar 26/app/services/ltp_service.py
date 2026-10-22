from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from app.domain.errors import FeedError
from app.domain.models import LTPQuote
from app.domain.protocols import TradingContextProtocol

logger = logging.getLogger(__name__)


async def _fetch_single_tick(feed: Any, timeout_seconds: float) -> dict[str, Any]:
    try:
        await feed.connect()
        return await asyncio.wait_for(feed.get_instrument_data(), timeout=timeout_seconds)
    except Exception as exc:
        raise FeedError(f"Failed to fetch tick: {exc}") from exc
    finally:
        try:
            if hasattr(feed, "disconnect"):
                await feed.disconnect()
            elif hasattr(feed, "close"):
                await feed.close()
        except Exception:
            pass


def _to_quote(symbol: str, tick: dict[str, Any]) -> LTPQuote:
    if "LTP" not in tick:
        raise FeedError(f"LTP missing in tick payload: {tick}")
    try:
        ltp_value = float(tick["LTP"])
    except (TypeError, ValueError) as exc:
        raise FeedError(f"Invalid LTP value: {tick.get('LTP')}") from exc
    return LTPQuote(
        symbol=symbol, ltp=ltp_value, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


def fetch_ltp(
    trading_context: TradingContextProtocol,
    symbol: str,
    exchange_segment: int,
    security_id: str,
    request_code: int,
    timeout_seconds: float = 10.0,
    max_retries: int = 3,
) -> LTPQuote:
    if not symbol.strip():
        raise FeedError("Symbol cannot be empty.")
    if timeout_seconds <= 0:
        raise FeedError("timeout_seconds must be > 0")

    instruments = [(exchange_segment, security_id, request_code)]
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            logger.debug("Fetching LTP attempt %s/%s for %s", attempt + 1, max_retries + 1, symbol)
            feed = trading_context.get_feed(instruments=instruments, version="v2")
            tick = asyncio.run(_fetch_single_tick(feed, timeout_seconds=timeout_seconds))
            return _to_quote(symbol=symbol, tick=tick)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                logger.warning("Attempt %s failed: %s", attempt + 1, exc)
                time.sleep(2**attempt)

    raise FeedError(
        f"Unable to fetch LTP after {max_retries + 1} attempts: {last_error}"
    ) from last_error
