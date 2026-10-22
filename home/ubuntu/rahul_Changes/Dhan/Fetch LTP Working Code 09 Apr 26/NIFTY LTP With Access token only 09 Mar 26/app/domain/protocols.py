from __future__ import annotations

from typing import Any, Protocol


class TradingContextProtocol(Protocol):
    def get_feed(self, instruments: list[tuple[int, str, int]], version: str = "v2") -> Any: ...
