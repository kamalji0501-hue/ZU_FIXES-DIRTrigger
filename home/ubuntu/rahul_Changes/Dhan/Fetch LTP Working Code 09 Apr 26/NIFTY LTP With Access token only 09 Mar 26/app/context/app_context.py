from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config.settings import Settings, load_settings
from app.context.trading_context import create_trading_context
from app.domain.models import LTPQuote
from app.infra.file_writer import write_ltp_output
from app.infra.logger import setup_logging
from app.services.ltp_service import fetch_ltp


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    logger: logging.Logger
    trading_context: Any

    def run_once(self) -> tuple[LTPQuote, Path]:
        quote = fetch_ltp(
            trading_context=self.trading_context,
            symbol=self.settings.default_symbol,
            exchange_segment=self.settings.exchange_segment,
            security_id=self.settings.security_id,
            request_code=self.settings.request_code,
            timeout_seconds=self.settings.timeout_seconds,
            max_retries=self.settings.max_retries,
        )
        output_path = write_ltp_output(
            base_output_path=self.settings.external_output_base, quote=quote
        )
        return quote, output_path


def build_app_context(overrides: dict[str, Any] | None = None) -> AppContext:
    settings = load_settings(overrides=overrides)
    logger = setup_logging(settings.log_level, settings.external_output_base)
    trading_context = create_trading_context(
        client_id=settings.client_id, access_token=settings.access_token
    )
    return AppContext(settings=settings, logger=logger, trading_context=trading_context)
