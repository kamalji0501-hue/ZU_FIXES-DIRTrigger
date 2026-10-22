from __future__ import annotations

import logging
import sys
from pathlib import Path

from app.infra.file_writer import get_output_dir


def setup_logging(log_level: str, base_output_path: Path) -> logging.Logger:
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    dated_output = get_output_dir(base_output_path)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    file_handler = logging.FileHandler(dated_output / "logs.txt", encoding="utf-8")
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=numeric_level, handlers=[console, file_handler], force=True)
    return logging.getLogger()
