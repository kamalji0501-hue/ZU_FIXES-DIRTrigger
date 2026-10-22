from __future__ import annotations

import logging
from pathlib import Path

from app.domain.errors import WriteError
from app.domain.models import LTPQuote
from app.infra.clock import today_date

logger = logging.getLogger(__name__)


def get_output_dir(base_output_path: Path) -> Path:
    dated = base_output_path / today_date()
    dated.mkdir(parents=True, exist_ok=True)
    return dated


def write_ltp_output(base_output_path: Path, quote: LTPQuote) -> Path:
    output_dir = get_output_dir(base_output_path)
    output_file = output_dir / "ltp_output.txt"
    content = f"timestamp: {quote.timestamp}\nsymbol: {quote.symbol}\nltp: {quote.ltp:.2f}\n"
    try:
        output_file.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise WriteError(f"Failed to write output file: {exc}") from exc
    logger.info("Wrote LTP %.2f for %s to %s", quote.ltp, quote.symbol, output_file)
    return output_file


def write_test_result(base_output_path: Path, text: str) -> Path:
    output_dir = get_output_dir(base_output_path)
    output_file = output_dir / "test_results.txt"
    try:
        output_file.write_text(text.rstrip() + "\n", encoding="utf-8")
    except OSError as exc:
        raise WriteError(f"Failed to write test results: {exc}") from exc
    return output_file


def print_output_location(path: Path) -> None:
    print("Output stored at:")
    print(str(path))
