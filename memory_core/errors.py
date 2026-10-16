"""Typed memory layer exceptions matching spec error codes."""

from __future__ import annotations


class MemoryError(Exception):
    """Base class for all Memory Fabric exceptions."""

    code: str = "DB_ERROR"

    def __init__(self, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.message: str = message
        if code:
            self.code = code


class NotFoundError(MemoryError):
    """Resource not found in graph."""

    code: str = "NOT_FOUND"


class InvalidInputError(MemoryError):
    """Input validation failure or unrecognized entity/predicate."""

    code: str = "INVALID_INPUT"


class ForbiddenError(MemoryError):
    """Action prohibited by security policy, user mismatch, or role allowlist."""

    code: str = "FORBIDDEN"


class ConflictError(MemoryError):
    """Concurrency violation, CAS mismatch, or state transition conflict."""

    code: str = "CONFLICT"

    def __init__(self, message: str, current_version: int | None = None) -> None:
        super().__init__(message, code="CONFLICT")
        self.current_version: int | None = current_version


class DatabaseError(MemoryError):
    """FalkorDB query failure or connection error."""

    code: str = "DB_ERROR"
