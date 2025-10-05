# accounts/views_oauth_cf.py

import secrets
import base64
import json
from typing import Tuple

from django.utils.crypto import constant_time_compare
import requests

from accounts.models import UserExtraData

from django.conf import settings
from django.db import transaction
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.utils import extend_schema, OpenApiResponse

from django.contrib.auth import get_user_model
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

# if you already have this serializer (used in your GitHub flow), keep using it:
try:
    from .serializers_oauth import AccessTokenSerializer  # type: ignore
except Exception:
    # fallback minimal serializer (won't break OpenAPI)
    from rest_framework import serializers
    class AccessTokenSerializer(serializers.Serializer):
        access = serializers.CharField()

from .views import set_refresh_cookie  # reuse your existing helper

User = get_user_model()

# ---- Codeforces OIDC constants (from discovery) ----
CF_ISSUER = "https://codeforces.com"
CF_AUTHORIZE = "https://codeforces.com/oauth/authorize"
CF_TOKEN = "https://codeforces.com/oauth/token"
CF_SCOPE = "openid"  # discovery shows only 'openid'
# id_token is HS256-signed (per discovery). We'll verify with client secret.

# ---- tiny helpers ------------------------------------------------------------
CF_TOKEN = "https://codeforces.com/oauth/token"

def _safe_equal(a: str | None, b: str | None) -> bool:
    a = (a or "").strip()
    b = (b or "").strip()
    # constant-time compare to avoid subtle mismatches
    return bool(a) and bool(b) and constant_time_compare(a, b)
def _split_name_from_handle(handle: str) -> Tuple[str, str]:
    # Codeforces doesn't give first/last — we keep handle as first_name
    h = (handle or "").strip()
    return (h, "")

def _decode_jwt_no_verify(id_token: str) -> dict:
    """
    We prefer to VERIFY (HS256) with client secret below. This helper is only
    used for robust error messages if verification fails early.
    """
    try:
        parts = id_token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception:
        return {}

def _verify_id_token_hs256(id_token: str, client_secret: str) -> dict:
    """
    Verify HS256 signature of the Codeforces id_token using CLIENT SECRET
    (Codeforces discovery lists HS256 as the signing alg).
    We avoid adding heavy JWT libs; for production you can use `pyjwt`.
    """
    try:
        import hmac, hashlib
        header_b64, payload_b64, sig_b64 = id_token.split(".")
        signed = f"{header_b64}.{payload_b64}".encode()
        expected_sig = hmac.new(
            key=client_secret.encode(),
            msg=signed,
            digestmod=hashlib.sha256
        ).digest()
        # Compare signature
        calc = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode()
        if calc != sig_b64:
            raise AuthenticationFailed("Invalid id_token signature")

        # decode payload
        payload_dec = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_dec))
        # quick issuer check
        if payload.get("iss") != CF_ISSUER:
            raise AuthenticationFailed("id_token issuer mismatch")
        return payload
    except AuthenticationFailed:
        raise
    except Exception:
        # Fall back to a best-effort decode for better error logs
        payload = _decode_jwt_no_verify(id_token)
        raise AuthenticationFailed("id_token verification failed")

def _issue_tokens_response(user: User) -> Response:
    rt = RefreshToken.for_user(user)
    at = str(rt.access_token)
    resp = Response({"access": at}, status=status.HTTP_200_OK)
    set_refresh_cookie(resp, str(rt))
    return resp

# ---- Views -------------------------------------------------------------------

class CodeforcesLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirect to Codeforces OAuth (OIDC)")},
        description="Start Codeforces login (OIDC Authorization Code). Sets state cookie and 302s to Codeforces."
    )
    def get(self, request):
        state = secrets.token_urlsafe(24)

        # read config from settings / env
        client_id = settings.CODEFORCES_CLIENT_ID
        redirect_uri = settings.CODEFORCES_REDIRECT_URI

        url = (
            f"{CF_AUTHORIZE}"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&scope={CF_SCOPE}"
            f"&state={state}"
        )

        conf = settings.OAUTH_STATE_COOKIE
        resp = Response(status=302)
        resp["Location"] = url
        resp.set_cookie(
            conf["key"], state,
            max_age=conf["max_age"],
            httponly=conf["httponly"],
            secure=conf["secure"],
            samesite=conf["samesite"],
            path=conf["path"],
            domain=conf.get("domain"),
        )
        return resp


@method_decorator(csrf_exempt, name="dispatch")
class CodeforcesCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirect to frontend with login=ok")},
        description="Codeforces OAuth callback: verifies state, exchanges code, upserts user, saves CF extras, sets refresh cookie, redirects to frontend."
    )
    @transaction.atomic
    def get(self, request):
        # --- 1) Validate state ---
        code = request.GET.get("code")
        state = request.GET.get("state")
        state_cookie = request.COOKIES.get(settings.OAUTH_STATE_COOKIE["key"])

        if not code:
            return HttpResponseBadRequest("missing code")
        if not _safe_equal(state, state_cookie):
            return HttpResponseBadRequest("invalid state")

        client_id = settings.CODEFORCES_CLIENT_ID
        client_secret = settings.CODEFORCES_CLIENT_SECRET
        redirect_uri = settings.CODEFORCES_REDIRECT_URI

        # --- 2) Exchange code -> tokens ---
        try:
            data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            }
            tok = requests.post(CF_TOKEN, data=data, timeout=15)
        except requests.RequestException:
            raise AuthenticationFailed("network error contacting Codeforces")

        if tok.status_code != 200:
            raise AuthenticationFailed("code→token failed")

        payload = {}
        try:
            payload = tok.json() or {}
        except Exception:
            raise AuthenticationFailed("token response not JSON")

        id_token = payload.get("id_token")
        access_token = payload.get("access_token")  # optional
        if not id_token:
            raise AuthenticationFailed("no id_token returned")

        # --- 3) Verify and parse id_token (HS256 with client_secret) ---
        claims = _verify_id_token_hs256(id_token, client_secret)

        # Common claims Codeforces publishes (as per your note): sub, handle, rating, avatar
        sub = str(claims.get("sub", "")).strip()
        handle = (claims.get("handle") or "").strip()
        rating = claims.get("rating")
        try:
            rating = int(rating) if rating is not None else 0
        except Exception:
            rating = 0
        avatar = (claims.get("avatar") or "").strip()
        rank = (claims.get("rank") or "").strip()  # sometimes present

        # Derive first/last name from handle (you can make this smarter if desired)
        first_name, last_name = _split_name_from_handle(handle)

        # Codeforces doesn’t give email — synthesize a stable pseudo-email
        email = f"{handle or sub or 'user'}+cf@users.noreply.codeforces.com"

        # --- 4) Upsert User ---
        user = User.objects.filter(email__iexact=email).first()
        if user:
            update_fields = []
            if not user.first_name and first_name:
                user.first_name = first_name; update_fields.append("first_name")
            if not user.last_name and last_name:
                user.last_name = last_name; update_fields.append("last_name")
            if update_fields:
                user.save(update_fields=update_fields)
        else:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_email_verified=False,  # still unverified (no real email)
            )
            user.set_unusable_password()
            user.save()

        # --- 5) Merge/record Codeforces extras ---
        extra, _ = UserExtraData.objects.get_or_create(user=user)
        # keep dedicated columns in sync
        extra.codeforces_handle = handle or extra.codeforces_handle
        extra.codeforces_score = rating
        # merge into answers dict without replacing existing keys
        answers = dict(extra.answers or {})
        cf_answers = dict(answers.get("codeforces", {}))
        cf_answers.update({
            "sub": sub,
            "handle": handle,
            "rating": rating,
            "rank": rank,
            "avatar": avatar,
            "token_present": bool(access_token),
        })
        answers["codeforces"] = cf_answers
        extra.answers = answers
        extra.save(update_fields=["codeforces_handle", "codeforces_score", "answers", "updated_at"])

        # --- 6) Issue refresh cookie and redirect to frontend ---
        rt = RefreshToken.for_user(user)
        # You can add any extras you want the frontend to read from query
        redirect_to = (
            f"{settings.FRONTEND_LOGIN_REDIRECT}"
            f"?login=ok&provider=codeforces&handle={handle}&rating={rating}"
        )
        resp = HttpResponseRedirect(redirect_to)
        set_refresh_cookie(resp, str(rt))

        # clean up state cookie
        conf = settings.OAUTH_STATE_COOKIE
        # include domain if you set one in settings
        resp.delete_cookie(
            conf["key"],
            path=conf.get("path", "/"),
            domain=conf.get("domain"),
        )
        return resp
