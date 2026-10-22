"""Compatibility wrapper. Prefer imports from `app.services.ltp_service`."""

from app.services.ltp_service import fetch_ltp

__all__ = ["fetch_ltp"]
