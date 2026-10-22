from __future__ import annotations

from pathlib import Path

from app.config.settings import Settings
from app.context.app_context import build_app_context
from app.domain.models import LTPQuote


def run_once(settings: Settings | None = None) -> tuple[LTPQuote, Path]:
    overrides = settings.__dict__ if settings else None
    ctx = build_app_context(overrides=overrides)
    return ctx.run_once()
