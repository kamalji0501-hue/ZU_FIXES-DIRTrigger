from __future__ import annotations

from datetime import datetime


def today_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")
