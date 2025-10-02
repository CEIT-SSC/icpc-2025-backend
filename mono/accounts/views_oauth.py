
import secrets
import requests
from typing import Tuple

from django.conf import settings
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

from .serializers_oauth import AccessTokenSerializer
from .views import set_refresh_cookie  

User = get_user_model()

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_API_USER = "https://api.github.com/user"
GITHUB_API_EMAILS = "https://api.github.com/user/emails"
SCOPE = "read:user user:email"



def split_full_name(full: str) -> Tuple[str, str]:
    if not full:
        return "", ""
    parts = full.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])

def issue_tokens_response(user: User) -> Response:
    rt = RefreshToken.for_user(user)
    at = str(rt.access_token)
    resp = Response({"access": at}, status=200)
    set_refresh_cookie(resp, str(rt))
    return resp

def _frontend_redirect(query: str) -> HttpResponseRedirect:
    """Redirect back to frontend with a query string, e.g. ?login=ok or ?login=error&reason=..."""
    target = getattr(settings, "FRONTEND_LOGIN_REDIRECT", None) or "https://aut-icpc.ir/login/success"
    sep = "&" if "?" in target else "?"
    return HttpResponseRedirect(f"{target}{sep}{query}")

def _settings_ok() -> Tuple[bool, str]:
    missing = []
    for key in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_REDIRECT_URI"):
        if not getattr(settings, key, None):
            missing.append(key)
    return (len(missing) == 0, ", ".join(missing))



class GithubLoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirect to GitHub OAuth")},
        description="Start GitHub OAuth; sets state cookie and 302s to GitHub."
    )
    def get(self, request):
        ok, missing = _settings_ok()
        if not ok:
            
            return HttpResponseBadRequest(f"Missing settings: {missing}")

        state = secrets.token_urlsafe(24)
        url = (
            f"{GITHUB_AUTH_URL}"
            f"?client_id={settings.GITHUB_CLIENT_ID}"
            f"&redirect_uri={settings.GITHUB_REDIRECT_URI}"
            f"&scope={SCOPE.replace(' ', '%20')}"
            f"&state={state}"
        )

        conf = settings.OAUTH_STATE_COOKIE
        resp = HttpResponseRedirect(url)
        resp.set_cookie(
            conf["key"], state,
            max_age=conf.get("max_age", 300),
            httponly=conf.get("httponly", True),
            secure=conf.get("secure", True),
            samesite=conf.get("samesite", "Lax"),
            path=conf.get("path", "/"),
        )
        return resp


@method_decorator(csrf_exempt, name="dispatch")
class GithubCallbackView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={200: AccessTokenSerializer, 302: OpenApiResponse(description="Redirect to frontend with result")},
        description="GitHub callback: exchanges code→token, creates/updates user, sets refresh cookie, redirects to frontend."
    )
    def get(self, request):
        
        code = request.GET.get("code")
        state = request.GET.get("state")
        state_cookie = request.COOKIES.get(settings.OAUTH_STATE_COOKIE["key"])
        if not code or not state or not state_cookie or state != state_cookie:
            
            return _frontend_redirect("login=error&reason=invalid_state")

        
        try:
            tok_resp = requests.post(
                GITHUB_TOKEN_URL,
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                    "state": state,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
        except requests.RequestException:
            return _frontend_redirect("login=error&reason=network")

        if tok_resp.status_code != 200:
            return _frontend_redirect(f"login=error&reason=token_http_{tok_resp.status_code}")

        try:
            gh_access = tok_resp.json().get("access_token")
        except ValueError:
            return _frontend_redirect("login=error&reason=token_parse")

        if not gh_access:
            return _frontend_redirect("login=error&reason=no_access_token")

        authz = {"Authorization": f"Bearer {gh_access}", "Accept": "application/json"}

        
        try:
            uresp = requests.get(GITHUB_API_USER, headers=authz, timeout=10)
        except requests.RequestException:
            return _frontend_redirect("login=error&reason=user_network")

        if uresp.status_code != 200:
            return _frontend_redirect(f"login=error&reason=user_http_{uresp.status_code}")

        try:
            u = uresp.json()
        except ValueError:
            return _frontend_redirect("login=error&reason=user_parse")

        gh_id = u.get("id")
        gh_login = u.get("login") or ""
        full_name = u.get("name") or ""
        pub_email = u.get("email")

        if not gh_id:
            return _frontend_redirect("login=error&reason=missing_github_id")

        
        primary_email = None
        primary_verified = False
        try:
            eresp = requests.get(GITHUB_API_EMAILS, headers=authz, timeout=10)
            if eresp.status_code == 200:
                emails = eresp.json() or []
                for e in emails:
                    if e.get("primary"):
                        primary_email = e.get("email")
                        primary_verified = bool(e.get("verified"))
                        break
                if not primary_email:
                    for e in emails:
                        if e.get("verified"):
                            primary_email = e.get("email"); primary_verified = True
                            break
                if not primary_email and emails:
                    primary_email = emails[0].get("email")
        except requests.RequestException:
            
            pass
        except ValueError:
            pass

        email = primary_email or pub_email
        if not email:
            
            email = f"{gh_id or gh_login}+oauth@users.noreply.github.com"

        first_name, last_name = split_full_name(full_name or gh_login)

        
        user = User.objects.filter(email__iexact=email).first()
        if user:
            update_fields = []
            if not user.first_name and first_name:
                user.first_name = first_name; update_fields.append("first_name")
            if not user.last_name and last_name:
                user.last_name = last_name; update_fields.append("last_name")
            if primary_verified and not getattr(user, "is_email_verified", False):
                user.is_email_verified = True; update_fields.append("is_email_verified")
            if update_fields:
                user.save(update_fields=update_fields)
        else:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_active=True,  
                is_email_verified=primary_verified,
            )
            user.set_unusable_password()
            user.save()

        
        rt = RefreshToken.for_user(user)
        resp = _frontend_redirect("login=ok")
        set_refresh_cookie(resp, str(rt))
        
        conf = settings.OAUTH_STATE_COOKIE
        resp.delete_cookie(conf["key"], path=conf.get("path", "/"))
        return resp
