from django.urls import path
from .views import InitiatePaymentView, VerifyPaymentView, CallbackView

urlpatterns = [
    path("initiate/", InitiatePaymentView.as_view()),
    path("verify/", VerifyPaymentView.as_view()),
    path("callback/", CallbackView.as_view()),
]