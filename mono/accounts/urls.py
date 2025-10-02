from django.urls import path
from .views import (
    SignupStartView, SignupVerifyView,
    LoginStartView, LoginVerifyView,
    RefreshView, LogoutView,
    MeView, ExtraDataView,
)
from .views_oauth import GithubLoginView, GithubCallbackView

urlpatterns = [
    path("signup/start/", SignupStartView.as_view()),
    path("signup/verify/", SignupVerifyView.as_view()),
    path("login/start/", LoginStartView.as_view()),
    path("login/verify/", LoginVerifyView.as_view()),

    path("token/refresh/", RefreshView.as_view()),
    path("logout/", LogoutView.as_view()),

    path("me/", MeView.as_view()),
    path("me/extra/", ExtraDataView.as_view()),

    # oauth
    path("github/login/", GithubLoginView.as_view(), name="github-login"),
    path("github/callback/", GithubCallbackView.as_view(), name="github-callback"),
]