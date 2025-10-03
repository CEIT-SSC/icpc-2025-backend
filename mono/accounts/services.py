from typing import Tuple
from django.conf import settings
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from acm import error_codes
from acm.exceptions import CustomAPIException
from .models import User
from .utils.otp import create_otp

from notification.services import send_otp


def start_signup(email: str, first_name: str = "", last_name: str = "", phone_number: str = "") -> str:
    """
    Begins signup: ensures a single (case-insensitive) user record exists,
    blocks if a verified user already owns this email, then sends OTP.
    """
    existing = User.objects.filter(email__iexact=email).first()

    if existing:
        user = existing
        if user.is_email_verified:
            raise CustomAPIException(
                code=error_codes.ACC_EMAIL_TAKEN,
                message="Email already registered",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if phone_number:
            user.phone_number = phone_number
        user.is_active = True
        user.save(update_fields=["first_name", "last_name", "phone_number", "is_active"])
    else:
        norm_email = (email or "").strip().lower()
        user = User.objects.create(
            email=norm_email,
            first_name=first_name or "",
            last_name=last_name or "",
            phone_number=phone_number or "",
            is_active=True,
        )

    # Create & send OTP
    token, code = create_otp(email=user.email, intent="signup", user_id=user.id)
    send_otp(destination=user.email, code=code, channel="email")
    return token


def start_login(email: str) -> str:
    """
    Begins login via OTP. Returns an opaque otp_token.
    """
    user = User.objects.filter(email__iexact=email).first()
    if not user:
        raise CustomAPIException(
            code=error_codes.ACC_INVALID_CREDENTIALS,
            message="Invalid credentials",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    if not user.is_active:
        raise CustomAPIException(
            code=error_codes.ACC_ACCOUNT_DISABLED,
            message="Account disabled",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    token, code = create_otp(email=user.email, intent="login", user_id=user.id)
    send_otp(destination=user.email, code=code, channel="email")
    return token


def issue_tokens(user: User) -> Tuple[str, str]:
    """
    Returns (access, refresh) as strings.
    """
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    return str(access), str(refresh)
