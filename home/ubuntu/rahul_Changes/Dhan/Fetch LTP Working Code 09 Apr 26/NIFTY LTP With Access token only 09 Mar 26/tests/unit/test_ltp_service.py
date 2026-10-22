from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.ltp_service import fetch_ltp


class TestLTPService(unittest.TestCase):
    @patch("app.services.ltp_service._fetch_single_tick", new_callable=AsyncMock)
    def test_fetch_ltp_returns_quote(self, mock_fetch: AsyncMock) -> None:
        mock_context = MagicMock()
        mock_context.get_feed.return_value = MagicMock()
        mock_fetch.return_value = {"LTP": "22456.25", "LTT": "2026-03-09T10:45:00"}

        quote = fetch_ltp(
            trading_context=mock_context,
            symbol="NIFTY",
            exchange_segment=0,
            security_id="13",
            request_code=15,
        )

        self.assertEqual(quote.symbol, "NIFTY")
        self.assertEqual(quote.ltp, 22456.25)
        self.assertTrue(quote.timestamp)


if __name__ == "__main__":
    unittest.main()
