from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, OpenApiResponse

from acm import error_codes
from acm.exceptions import CustomAPIException

from .serializers import (
    SignupStartSerializer, LoginStartSerializer, OtpVerifySerializer,
    UserSerializer, UserExtraDataSerializer,
)
from .models import UserExtraData
from .utils.otp import verify_otp
from .services import start_signup, start_login, issue_tokens

User = get_user_model()

# ----- Small response serializers so Swagger shows bodies -----
class OTPTokenResponseSerializer(serializers.Serializer):
    otp_token = serializers.CharField()

class TokenWithUserResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    user = UserSerializer()

class AccessTokenOnlySerializer(serializers.Serializer):
    access = serializers.CharField()
# --------------------------------------------------------------

COOKIE_CONF = settings.REFRESH_TOKEN_COOKIE

def set_refresh_cookie(resp: Response, refresh_token: str):
    resp.set_cookie(
        COOKIE_CONF["key"], refresh_token,
        httponly=COOKIE_CONF.get("httponly", True),
        secure=COOKIE_CONF.get("secure", True),
        samesite=COOKIE_CONF.get("samesite", "Lax"),
        path=COOKIE_CONF.get("path", "/"),
        max_age=60*60*24*30,
    )

class SignupStartView(APIView):
    permission_classes = []

    @extend_schema(
        request=SignupStartSerializer,
        responses={201: OTPTokenResponseSerializer},
        description="Begin signup via OTP. Sends OTP and returns an opaque otp_token."
    )
    def post(self, request):
        s = SignupStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        token = start_signup(**s.validated_data)
        return Response({"otp_token": token}, status=201)

class SignupVerifyView(APIView):
    permission_classes = []

    @extend_schema(
        request=OtpVerifySerializer,
        responses={
            200: TokenWithUserResponseSerializer,
            400: OpenApiResponse(description="Invalid or expired OTP"),
        },
        description="Verify signup OTP. On success: marks email verified, returns access token and sets refresh cookie."
    )
    @transaction.atomic
    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rec = verify_otp(s.validated_data["token"], s.validated_data["code"])
        if not rec or rec.intent != "signup":
            # unified API error shape
            raise CustomAPIException(
                code=error_codes.ACC_INVALID_OTP,
                message="Invalid or expired OTP",
                status_code=400,
            )
        user = User.objects.select_for_update().get(id=rec.user_id)
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        access, refresh = issue_tokens(user)
        resp = Response({"access": access, "user": UserSerializer(user).data}, status=200)
        set_refresh_cookie(resp, refresh)
        return resp

class LoginStartView(APIView):
    permission_classes = []

    @extend_schema(
        request=LoginStartSerializer,
        responses={200: OTPTokenResponseSerializer},
        description="Begin login via OTP. Sends OTP and returns an opaque otp_token."
    )
    def post(self, request):
        s = LoginStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        # start_login already raises CustomAPIException with proper codes
        token = start_login(**s.validated_data)
        return Response({"otp_token": token}, status=200)

class LoginVerifyView(APIView):
    permission_classes = []

    @extend_schema(
        request=OtpVerifySerializer,
        responses={
            200: TokenWithUserResponseSerializer,
            400: OpenApiResponse(description="Invalid or expired OTP"),
        },
        description="Verify login OTP. Returns access token and sets rotated refresh cookie."
    )
    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rec = verify_otp(s.validated_data["token"], s.validated_data["code"])
        if not rec or rec.intent != "login":
            raise CustomAPIException(
                code=error_codes.ACC_INVALID_OTP,
                message="Invalid or expired OTP",
                status_code=400,
            )
        user = User.objects.get(id=rec.user_id)
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])
        access, refresh = issue_tokens(user)
        resp = Response({"access": access, "user": UserSerializer(user).data}, status=200)
        set_refresh_cookie(resp, refresh)
        return resp

class RefreshView(APIView):
    permission_classes = []

    @extend_schema(
        request=None,
        responses={
            200: AccessTokenOnlySerializer,
            401: OpenApiResponse(description="No/invalid refresh token"),
        },
        description="Rotate refresh token from cookie and return a new access token."
    )
    def post(self, request):
        token = request.COOKIES.get(COOKIE_CONF["key"])
        if not token:
            raise CustomAPIException(
                code=error_codes.ACC_NO_REFRESH,
                message="No refresh token",
                status_code=401,
            )
        try:
            rt = RefreshToken(token)
        except Exception:
            raise CustomAPIException(
                code=error_codes.ACC_INVALID_REFRESH,
                message="Invalid refresh",
                status_code=401,
            )
        access = str(rt.access_token)
        # If blacklist app is enabled, this is fine. If not, it’s a no-op.
        try:
            rt.blacklist()
        except Exception:
            pass
        new_rt = RefreshToken.for_user(User.objects.get(id=rt["user_id"]))
        resp = Response({"access": access}, status=200)
        set_refresh_cookie(resp, str(new_rt))
        return resp

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={204: OpenApiResponse(description="Logged out; refresh cookie cleared")},
        description="Blacklist current refresh (from cookie) and clear it."
    )
    def post(self, request):
        token = request.COOKIES.get(COOKIE_CONF["key"])
        resp = Response(status=204)
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:
                pass
        resp.delete_cookie(COOKIE_CONF["key"], path=COOKIE_CONF.get("path", "/"))
        return resp

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: UserSerializer},
        description="Get current user profile."
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)

    @extend_schema(
        request=UserSerializer,
        responses={200: UserSerializer},
        description="Partial update current user profile."
    )
    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

class ExtraDataView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={200: UserExtraDataSerializer},
        description="Get current user's extra data."
    )
    def get(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        return Response(UserExtraDataSerializer(extra).data)

    @extend_schema(
        request=UserExtraDataSerializer,
        responses={200: UserExtraDataSerializer},
        description="Replace current user's extra data."
    )
    def put(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        s = UserExtraDataSerializer(extra, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    @extend_schema(
        request=UserExtraDataSerializer,
        responses={200: UserExtraDataSerializer},
        description="Patch current user's extra data."
    )
    def patch(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        s = UserExtraDataSerializer(extra, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)
