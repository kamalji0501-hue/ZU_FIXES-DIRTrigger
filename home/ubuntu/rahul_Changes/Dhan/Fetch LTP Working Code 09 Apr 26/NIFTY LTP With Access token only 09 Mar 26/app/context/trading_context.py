from __future__ import annotations

from typing import Any

from app.domain.errors import AuthError
from app.domain.protocols import TradingContextProtocol

try:
    from dhanhq.marketfeed import DhanFeed as LegacyDhanFeed

    _USE_LEGACY_FEED = True
except ImportError:
    from dhanhq import DhanContext
    from dhanhq.marketfeed import MarketFeed as ModernMarketFeed

    _USE_LEGACY_FEED = False


class DhanTradingContext(TradingContextProtocol):
    def __init__(self, client_id: str, access_token: str) -> None:
        if not client_id or not access_token:
            raise AuthError("Client ID and access token are required.")
        self.client_id = client_id
        self.access_token = access_token

    def get_feed(self, instruments: list[tuple[int, str, int]], version: str = "v2") -> Any:
        try:
            if _USE_LEGACY_FEED:
                return LegacyDhanFeed(
                    client_id=self.client_id,
                    access_token=self.access_token,
                    instruments=instruments,
                    version=version,
                )
            context = DhanContext(client_id=self.client_id, access_token=self.access_token)
            return ModernMarketFeed(dhan_context=context, instruments=instruments, version=version)
        except Exception as exc:
            raise AuthError(f"Unable to create market feed: {exc}") from exc


def create_trading_context(client_id: str, access_token: str) -> TradingContextProtocol:
    return DhanTradingContext(client_id=client_id, access_token=access_token)
