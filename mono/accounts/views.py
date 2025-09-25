from django.shortcuts import render

# Create your views here.
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    SignupStartSerializer, LoginStartSerializer, OtpVerifySerializer,
    UserSerializer, UserExtraDataSerializer,
)
from .models import UserExtraData
from .utils.otp import verify_otp
from .services import start_signup, start_login, issue_tokens

User = get_user_model()

# Cookie helpers
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

    def post(self, request):
        s = SignupStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        token = start_signup(**s.validated_data)
        return Response({"otp_token": token}, status=201)

class SignupVerifyView(APIView):
    permission_classes = []

    @transaction.atomic
    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rec = verify_otp(s.validated_data["token"], s.validated_data["code"])
        if not rec or rec.intent != "signup":
            return Response({"detail": "Invalid or expired OTP"}, status=400)
        user = User.objects.select_for_update().get(id=rec.user_id)
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
        access, refresh = issue_tokens(user)
        resp = Response({"access": access, "user": UserSerializer(user).data}, status=200)
        set_refresh_cookie(resp, refresh)
        return resp

class LoginStartView(APIView):
    permission_classes = []

    def post(self, request):
        s = LoginStartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        token = start_login(**s.validated_data)
        return Response({"otp_token": token}, status=200)

class LoginVerifyView(APIView):
    permission_classes = []

    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        rec = verify_otp(s.validated_data["token"], s.validated_data["code"])
        if not rec or rec.intent != "login":
            return Response({"detail": "Invalid or expired OTP"}, status=400)
        user = User.objects.get(id=rec.user_id)
        if not user.is_email_verified:
            # if user somehow wasn't verified, treat successful OTP as verification
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])
        access, refresh = issue_tokens(user)
        resp = Response({"access": access, "user": UserSerializer(user).data}, status=200)
        set_refresh_cookie(resp, refresh)
        return resp

class RefreshView(APIView):
    permission_classes = []

    def post(self, request):
        token = request.COOKIES.get(COOKIE_CONF["key"])  # read from cookie
        if not token:
            return Response({"detail": "No refresh token"}, status=401)
        try:
            rt = RefreshToken(token)
        except Exception:
            return Response({"detail": "Invalid refresh"}, status=401)
        access = str(rt.access_token)
        # rotate + blacklist
        rt.blacklist()
        new_rt = RefreshToken.for_user(User.objects.get(id=rt["user_id"]))
        resp = Response({"access": access}, status=200)
        set_refresh_cookie(resp, str(new_rt))
        return resp

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.COOKIES.get(COOKIE_CONF["key"])  # refresh in cookie
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

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        s = UserSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

class ExtraDataView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        return Response(UserExtraDataSerializer(extra).data)

    def put(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        s = UserExtraDataSerializer(extra, data=request.data, partial=False)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)

    def patch(self, request):
        extra, _ = UserExtraData.objects.get_or_create(user=request.user)
        s = UserExtraDataSerializer(extra, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)