from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.domain.errors import ConfigError


@dataclass(frozen=True)
class Settings:
    client_id: str
    access_token: str
    exchange_segment: int
    security_id: str
    request_code: int
    default_symbol: str
    external_output_base: Path
    log_level: str
    max_retries: int
    timeout_seconds: int
    continuous: bool
    poll_interval_seconds: int


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _read_first_valid_line(file_path: Path, label: str) -> str:
    if not file_path.exists():
        raise ConfigError(f"{label} file not found: {file_path}")

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ACCESS_TOKEN="):
            line = line.split("=", 1)[1].strip()
        if "YOUR_" in line.upper() or "ADD YOUR" in line.upper():
            raise ConfigError(f"{label} appears to be a placeholder. Update: {file_path}")
        if any(char in line for char in [" ", "\t", "\r", "\n", "#"]):
            raise ConfigError(f"{label} contains invalid characters")
        return line

    raise ConfigError(f"{label} is empty: {file_path}")


def _load_json_settings(config_dir: Path) -> dict[str, Any]:
    default = {
        "trading": {
            "exchange_segment": 0,
            "security_id": "13",
            "request_code": 15,
            "default_symbol": "NIFTY",
        },
        "output": {
            "external_base_dir": r"H:\RK Data\Algo\Daily Output",
        },
        "logging": {
            "level": "INFO",
        },
        "api": {
            "max_retries": 3,
            "timeout_seconds": 30,
        },
        "runtime": {
            "continuous": True,
            "poll_interval_seconds": 10,
        },
    }
    settings_file = config_dir / "settings.json"
    if not settings_file.exists():
        return default

    try:
        override = json.loads(settings_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {settings_file}: {exc}") from exc

    for section, values in override.items():
        if isinstance(values, dict) and section in default and isinstance(default[section], dict):
            default[section].update(values)
        else:
            default[section] = values
    return default


def _validate_settings(settings: Settings) -> Settings:
    if settings.exchange_segment < 0:
        raise ConfigError("exchange_segment must be >= 0")
    if not settings.security_id.strip():
        raise ConfigError("security_id cannot be empty")
    if settings.request_code <= 0:
        raise ConfigError("request_code must be > 0")
    if not settings.default_symbol.strip():
        raise ConfigError("default_symbol cannot be empty")
    if settings.max_retries < 0:
        raise ConfigError("max_retries must be >= 0")
    if settings.timeout_seconds <= 0:
        raise ConfigError("timeout_seconds must be > 0")
    if settings.poll_interval_seconds <= 0:
        raise ConfigError("poll_interval_seconds must be > 0")
    return settings


def load_settings(overrides: dict[str, Any] | None = None) -> Settings:
    root = _project_root()
    config_dir = root / "config"
    settings = _load_json_settings(config_dir)
    overrides = overrides or {}

    client_id = os.getenv("FTLTP_CLIENT_ID") or _read_first_valid_line(
        config_dir / "client_id.txt", "Client ID"
    )
    access_token = os.getenv("FTLTP_ACCESS_TOKEN") or _read_first_valid_line(
        config_dir / "token.txt", "Access token"
    )

    if "YOUR_" in client_id.upper() or "YOUR_" in access_token.upper():
        raise ConfigError("Credentials contain placeholders.")

    external_base = Path(
        overrides.get("external_output_base")
        or os.getenv("FTLTP_OUTPUT_DIR")
        or settings["output"]["external_base_dir"]
    )
    loaded = Settings(
        client_id=client_id,
        access_token=access_token,
        exchange_segment=int(
            overrides.get("exchange_segment", settings["trading"]["exchange_segment"])
        ),
        security_id=str(overrides.get("security_id", settings["trading"]["security_id"])),
        request_code=int(overrides.get("request_code", settings["trading"]["request_code"])),
        default_symbol=str(
            overrides.get("default_symbol")
            or os.getenv("FTLTP_SYMBOL")
            or settings["trading"]["default_symbol"]
        ),
        external_output_base=external_base,
        log_level=str(
            overrides.get("log_level")
            or os.getenv("FTLTP_LOG_LEVEL")
            or settings["logging"]["level"]
        ).upper(),
        max_retries=int(overrides.get("max_retries", settings["api"]["max_retries"])),
        timeout_seconds=int(overrides.get("timeout_seconds", settings["api"]["timeout_seconds"])),
        continuous=bool(overrides.get("continuous", settings["runtime"]["continuous"])),
        poll_interval_seconds=int(
            overrides.get("poll_interval_seconds", settings["runtime"]["poll_interval_seconds"])
        ),
    )
    return _validate_settings(loaded)
