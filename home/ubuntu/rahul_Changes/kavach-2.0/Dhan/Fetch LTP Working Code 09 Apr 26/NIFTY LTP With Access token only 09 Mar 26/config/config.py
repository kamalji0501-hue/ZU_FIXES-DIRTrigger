"""
Configuration management for the F&O LTP Data Fetching Application.

This module handles loading and validation of application configuration
from various sources including files, environment variables, and defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class AppConfig:
    """
    Application configuration data class.

    Contains all configuration parameters needed for the application.
    """

    # API Configuration
    client_id: str
    access_token: str

    # Trading Configuration
    exchange_segment: int
    security_id: str
    request_code: int
    default_symbol: str

    # External Output Configuration (H:\RK Data\Algo\Daily Output)
    external_output_base: Path

    # Logging Configuration
    log_level: str
    log_file: Path

    # API Connection Settings
    max_retries: int = 3
    timeout_seconds: int = 30


def get_project_root() -> Path:
    """
    Get the project root directory.

    Returns:
        Path: Project root directory path
    """
    return Path(__file__).resolve().parents[1]


def _read_text_file(file_path: Path, description: str) -> str:
    """
    Read and validate a text file.

    Args:
        file_path: Path to the file
        description: Description for error messages

    Returns:
        str: File content (stripped)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file is empty
    """
    if not file_path.exists():
        raise FileNotFoundError(f"{description} file not found: {file_path}")

    content = file_path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"{description} file is empty: {file_path}")

    return content


def _load_client_id(config_dir: Path) -> str:
    """
    Load client ID from configuration file.

    Args:
        config_dir: Configuration directory path

    Returns:
        str: Client ID
    """
    client_id_file = config_dir / "client_id.txt"
    return _read_text_file(client_id_file, "Client ID")


def _load_access_token(config_dir: Path) -> str:
    """
    Load access token from configuration file.

    Args:
        config_dir: Configuration directory path

    Returns:
        str: Access token
    """
    token_file = config_dir / "token.txt"
    content = _read_text_file(token_file, "Access token")

    # Handle different token file formats
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("ACCESS_TOKEN="):
            return line.split("=", 1)[1].strip()
        return line

    raise ValueError(f"No valid access token found in: {token_file}")


def _load_settings(config_dir: Path) -> Dict[str, Any]:
    """
    Load application settings from JSON file.

    Args:
        config_dir: Configuration directory path

    Returns:
        Dict[str, Any]: Settings dictionary
    """
    settings_file = config_dir / "settings.json"

    # Default settings
    default_settings = {
        "trading": {
            "exchange_segment": 0,
            "security_id": "13",
            "request_code": 15,
            "default_symbol": "NIFTY",
        },
        "output": {"external_base_dir": "H:\\RK Data\\Algo\\Daily Output"},
        "logging": {"level": "INFO", "file": "logs/app.log"},
        "api": {"max_retries": 3, "timeout_seconds": 30},
    }

    if not settings_file.exists():
        return default_settings

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            user_settings = json.load(f)

        # Merge user settings with defaults
        _deep_merge(default_settings, user_settings)
        return default_settings

    except (json.JSONDecodeError, IOError) as exc:
        raise ValueError(f"Invalid settings file {settings_file}: {exc}") from exc


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> None:
    """
    Deep merge override dictionary into base dictionary.

    Args:
        base: Base dictionary to merge into
        override: Override dictionary to merge from
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _apply_env_overrides(settings: Dict[str, Any]) -> None:
    """
    Apply environment variable overrides to settings.

    Args:
        settings: Settings dictionary to modify
    """
    env_mappings = [
        ("FTLTP_CLIENT_ID", ["api", "client_id"]),
        ("FTLTP_ACCESS_TOKEN", ["api", "access_token"]),
        ("FTLTP_LOG_LEVEL", ["logging", "level"]),
        ("FTLTP_OUTPUT_DIR", ["output", "external_base_dir"]),
        ("FTLTP_SYMBOL", ["trading", "default_symbol"]),
    ]

    for env_var, path in env_mappings:
        value = os.getenv(env_var)
        if value:
            current = settings
            for key in path[:-1]:
                current = current.setdefault(key, {})
            current[path[-1]] = value


def load_config(config_dir: Optional[Path] = None) -> AppConfig:
    """
    Load application configuration from files and environment.

    Args:
        config_dir: Optional configuration directory path

    Returns:
        AppConfig: Loaded configuration

    Raises:
        FileNotFoundError: If required config files are missing
        ValueError: If configuration is invalid
    """
    if config_dir is None:
        config_dir = get_project_root() / "config"

    # Load settings
    settings = _load_settings(config_dir)

    # Apply environment overrides
    _apply_env_overrides(settings)

    # Load credentials (prefer environment variables)
    client_id = os.getenv("FTLTP_CLIENT_ID") or _load_client_id(config_dir)
    access_token = os.getenv("FTLTP_ACCESS_TOKEN") or _load_access_token(config_dir)

    # Build configuration
    project_root = get_project_root()

    return AppConfig(
        client_id=client_id,
        access_token=access_token,
        exchange_segment=int(settings["trading"]["exchange_segment"]),
        security_id=str(settings["trading"]["security_id"]),
        request_code=int(settings["trading"]["request_code"]),
        default_symbol=str(settings["trading"]["default_symbol"]),
        external_output_base=Path(settings["output"]["external_base_dir"]),
        log_level=str(settings["logging"]["level"]).upper(),
        log_file=project_root / settings["logging"]["file"],
        max_retries=int(settings["api"]["max_retries"]),
        timeout_seconds=int(settings["api"]["timeout_seconds"]),
    )
