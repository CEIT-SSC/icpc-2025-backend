from django.urls import path
from .views import VerifyPaymentView, CallbackView, StartpaymentView

urlpatterns = [
    path("verify/", VerifyPaymentView.as_view()),
    path("callback/", CallbackView.as_view()),
    path("startpay/", StartpaymentView.as_view())
]