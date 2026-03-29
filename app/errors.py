from __future__ import annotations


class AppError(RuntimeError):
    """Base application exception for expected operational failures."""


class NotConfiguredError(AppError):
    """Raised when a feature depends on infrastructure that is not configured."""
