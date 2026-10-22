from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LTPQuote:
    symbol: str
    ltp: float
    timestamp: str

    def as_dict(self) -> dict[str, str | float]:
        return {
            "symbol": self.symbol,
            "ltp": self.ltp,
            "timestamp": self.timestamp,
        }
