from django.urls import path
from .views import SingleEmailView, OtpEmailView, StatusChangeEmailView, BulkEmailView

urlpatterns = [
    path("email/single/", SingleEmailView.as_view()),
    path("email/otp/", OtpEmailView.as_view()),  # optional internal endpoint
    path("email/status/", StatusChangeEmailView.as_view()),
    path("email/bulk/", BulkEmailView.as_view()),
]