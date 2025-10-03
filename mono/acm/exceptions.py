from typing import Any, Dict, List, Union, Optional
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import (
    APIException, ValidationError, AuthenticationFailed, NotAuthenticated,
    PermissionDenied, NotFound, MethodNotAllowed, Throttled, UnsupportedMediaType
)
from . import error_codes as EC


class CustomAPIException(APIException):
    """
    Raise this when you want a specific errorCode + status.
    Example:
        raise CustomAPIException(
            code=EC.ACC_EMAIL_TAKEN,
            message="Email already registered",
            status_code=status.HTTP_400_BAD_REQUEST
        )
    """
    def __init__(self, code: int, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(detail=message)
        self.status_code = status_code
        self.app_code = code


def _flatten_errors(data: Union[Dict[str, Any], List[Any], str]) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts = [_flatten_errors(x) for x in data if x is not None]
        return "; ".join([p for p in parts if p])
    if isinstance(data, dict):
        parts = []
        for k, v in data.items():
            msg = _flatten_errors(v)
            if msg:
                parts.append(f"{k}: {msg}")
        return "; ".join(parts)
    return str(data)


def _generic_code_for_status(status_code: int) -> int:
    mapping = {
        400: EC.HTTP_BAD_REQUEST,
        401: EC.HTTP_UNAUTHORIZED,
        403: EC.HTTP_FORBIDDEN,
        404: EC.HTTP_NOT_FOUND,
        405: EC.HTTP_METHOD_NOT_ALLOWED,
        409: EC.HTTP_CONFLICT,
        415: EC.HTTP_UNSUPPORTED_MEDIA_TYPE,
        422: EC.HTTP_UNPROCESSABLE_ENTITY,
        429: EC.HTTP_TOO_MANY_REQUESTS,
        500: EC.HTTP_INTERNAL_ERROR,
    }
    return mapping.get(status_code, EC.HTTP_INTERNAL_ERROR)


def custom_exception_handler(exc, context) -> Response:
    # Normalize Django exceptions -> DRF ones
    if isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied(detail=str(exc))
    elif isinstance(exc, DjangoValidationError):
        try:
            detail = exc.message_dict  # type: ignore[attr-defined]
        except Exception:
            detail = getattr(exc, "messages", None) or str(exc)
        exc = ValidationError(detail=detail)
    elif isinstance(exc, Http404):
        exc = NotFound()

    # If it's our custom exception, short-circuit with our code
    if isinstance(exc, CustomAPIException):
        return Response(
            {"errorCode": exc.app_code, "errorMessage": str(exc.detail)},
            status=exc.status_code,
        )

    # Let DRF build a response for its known exceptions
    response = drf_exception_handler(exc, context)
    if response is not None:
        status_code = response.status_code
        if isinstance(exc, ValidationError):
            message = _flatten_errors(response.data)
        else:
            message = _flatten_errors(getattr(exc, "detail", response.data))
        payload = {
            "errorCode": _generic_code_for_status(status_code),
            "errorMessage": message or "Error",
        }
        return Response(payload, status=status_code)

    # Any other unhandled exception -> 500
    return Response(
        {"errorCode": EC.HTTP_INTERNAL_ERROR, "errorMessage": "Internal server error"},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
