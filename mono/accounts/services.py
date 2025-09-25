from typing import Tuple
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User
from .utils.otp import create_otp

# ---- Notification bridge (email/SMS) ----
# Implement this in your notification app:
# def send_otp(destination: str, code: str, channel: str = "email") -> None: ...
from notification.services import send_otp  # you implement this function


def start_signup(email: str, password: str, first_name: str = "", last_name: str = "", phone_number: str = "") -> str:
    user, created = User.objects.get_or_create(email=email)
    if not created and user.is_email_verified:
        raise ValueError("Email already registered")
    if created:
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number
    if password:
        user.set_password(password)
    user.is_active = True
    user.save()

    token, code = create_otp(email=email, intent="signup", user_id=user.id)
    send_otp(destination=email, code=code, channel="email")
    return token


def start_login(email: str, password: str) -> str:
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise ValueError("Invalid credentials")
    if not user.check_password(password):
        raise ValueError("Invalid credentials")
    if not user.is_active:
        raise ValueError("Account disabled")

    token, code = create_otp(email=email, intent="login", user_id=user.id)
    send_otp(destination=email, code=code, channel="email")
    return token


def issue_tokens(user: User) -> Tuple[str, str]:
    refresh = RefreshToken.for_user(user)
    access = refresh.access_token
    return str(access), str(refresh)