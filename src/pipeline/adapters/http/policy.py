"""How the pipeline's clients report another module (feature 033): always UnavailableError and RejectedError."""

from common.http import ErrorPolicy
from pipeline.models import RejectedError, UnavailableError


def errors(service: str) -> ErrorPolicy:
    """Network, timeout, 5xx or an answer that isn't JSON: UnavailableError; a 4xx the client doesn't handle:
    RejectedError."""
    return ErrorPolicy(service, UnavailableError, RejectedError)
