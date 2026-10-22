"""Compatibility wrapper. Prefer imports from `app.infra.clock`."""

from app.infra.clock import today_date


def get_today_date() -> str:
    return today_date()


__all__ = ["get_today_date"]
