from django.urls import path
from .views import (
    SignupStartView, SignupVerifyView,
    LoginStartView, LoginVerifyView,
    RefreshView, LogoutView,
    MeView, ExtraDataView,
)

urlpatterns = [
    path("signup/start/", SignupStartView.as_view()),
    path("signup/verify/", SignupVerifyView.as_view()),
    path("login/start/", LoginStartView.as_view()),
    path("login/verify/", LoginVerifyView.as_view()),

    path("token/refresh/", RefreshView.as_view()),
    path("logout/", LogoutView.as_view()),

    path("me/", MeView.as_view()),
    path("me/extra/", ExtraDataView.as_view()),
]