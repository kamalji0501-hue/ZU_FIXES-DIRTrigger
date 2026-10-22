"""Compatibility wrapper. Prefer imports from `app.infra.logger`."""

from pathlib import Path

from app.infra.logger import setup_logging

__all__ = ["setup_logging", "Path"]
