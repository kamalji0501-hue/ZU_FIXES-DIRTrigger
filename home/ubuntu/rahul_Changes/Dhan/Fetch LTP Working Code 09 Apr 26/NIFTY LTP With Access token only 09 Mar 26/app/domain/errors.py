class AppError(Exception):
    """Base application error."""


class ConfigError(AppError):
    """Configuration is invalid or incomplete."""


class AuthError(AppError):
    """Authentication/session setup failed."""


class FeedError(AppError):
    """Market feed operation failed."""


class WriteError(AppError):
    """Output write failed."""
