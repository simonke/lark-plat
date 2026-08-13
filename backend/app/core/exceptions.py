"""Application exception hierarchy mapped to contract error codes."""

from __future__ import annotations


class AppError(Exception):
    """Base business exception."""

    code: int = 500
    http_status: int = 400
    message: str = "server error"

    def __init__(self, message: str | None = None, code: int | None = None, data=None):
        if message is not None:
            self.message = message
        if code is not None:
            self.code = code
        self.data = data
        super().__init__(self.message)


class BadRequestError(AppError):
    code = 400
    http_status = 400
    message = "bad request"


class UnauthorizedError(AppError):
    code = 401
    http_status = 401
    message = "unauthorized"


class ForbiddenError(AppError):
    code = 403
    http_status = 403
    message = "forbidden"


class NotFoundError(AppError):
    code = 404
    http_status = 404
    message = "not found"


class ConflictError(AppError):
    code = 409
    http_status = 409
    message = "conflict"


class RateLimitError(AppError):
    code = 429
    http_status = 429
    message = "too many requests / concurrency limit reached"


class BusinessError(AppError):
    """Business error (code 1001), e.g. 'approval required'."""

    code = 1001
    http_status = 400
    message = "business error"
