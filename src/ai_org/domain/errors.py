from __future__ import annotations


class DomainError(Exception):
    """Base domain exception."""


class InvalidTransitionError(DomainError):
    """Raised when a state transition is not allowed."""


class ConflictError(DomainError):
    """Raised when optimistic locking or idempotency detects a conflict."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""


class ValidationFailure(DomainError):
    """Raised when deterministic validation fails."""
