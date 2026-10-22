"""Compatibility wrapper. Prefer imports from `app.infra.file_writer`."""

from pathlib import Path

from app.domain.models import LTPQuote
from app.infra.file_writer import print_output_location, write_ltp_output


def save_ltp_data(
    ltp_data: dict[str, str | float], external_output_base: Path, custom_date: str | None = None
) -> Path:
    # `custom_date` is kept for backward signature compatibility.
    quote = LTPQuote(
        symbol=str(ltp_data["symbol"]),
        ltp=float(ltp_data["ltp"]),
        timestamp=str(ltp_data["timestamp"]),
    )
    return write_ltp_output(external_output_base, quote)


__all__ = ["save_ltp_data", "print_output_location"]
