"""What every module's API shares (feature 033): the error body and the error handlers."""

from .errors import Error, error_handlers

__all__ = ["Error", "error_handlers"]
