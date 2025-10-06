from django.urls import path
from .views import VerifyPaymentView, CallbackView

urlpatterns = [
    path("verify/", VerifyPaymentView.as_view()),
    path("callback/", CallbackView.as_view()),
]