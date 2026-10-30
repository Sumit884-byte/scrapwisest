"""
Custom domain exceptions and FastAPI exception handlers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base domain exception for Scrapwisest."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_SERVER_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class EntityNotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            details=details,
        )


class ValidationAppError(AppException):
    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            details=details,
        )


class InvalidImageError(ValidationAppError):
    def __init__(self, message: str = "Invalid image file uploaded", details: Optional[Any] = None):
        super().__init__(message=message, details=details)
        self.code = "INVALID_IMAGE"


class ModelNotAvailableError(AppException):
    def __init__(self, message: str = "Requested model is currently unavailable", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="MODEL_UNAVAILABLE",
            details=details,
        )


class QuotaExceededError(AppException):
    def __init__(self, message: str = "API budget is exhausted for now", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="QUOTA_EXCEEDED",
            details=details,
        )


class ExternalServiceError(AppException):
    def __init__(self, message: str = "External upstream service failed", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("Domain exception handled: %s (code: %s) on path: %s", exc.message, exc.code, request.url.path)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error": exc.code,
            "details": exc.details,
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled server exception on %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Something went wrong processing your request.",
            "error": "INTERNAL_SERVER_ERROR",
        },
    )
