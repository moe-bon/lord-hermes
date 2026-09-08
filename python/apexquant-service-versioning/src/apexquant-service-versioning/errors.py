from __future__ import annotations


class VersioningError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "VERSIONING_ERROR",
    ) -> None:
        super().__init__(message)

        self.message = message
        self.status_code = status_code
        self.code = code


class NotFoundError(VersioningError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404, code="NOT_FOUND")


class ConflictError(VersioningError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, code="CONFLICT")


class InvalidTransitionError(VersioningError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, code="INVALID_TRANSITION")