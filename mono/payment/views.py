# payment/views.py

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .serializers import (
    VerifySerializer,
    PaymentSerializer, StartPaymentSerializer,
)
from .services import verify_by_authority, startpay


class VerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=VerifySerializer,
        responses={
            200: PaymentSerializer,
            401: OpenApiResponse(description="Unauthenticated or invalid/foreign authority"),
        },
        description="Verify a payment by authority (frontend sends authority after the gateway redirect)."
    )
    def post(self, request):
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        p = verify_by_authority(user=request.user, authority=s.validated_data["authority"])
        return Response(PaymentSerializer(p).data, status=status.HTTP_200_OK)


class CallbackView(APIView):
    permission_classes = []

    @extend_schema(
        request=None,
        responses={302: OpenApiResponse(description="Redirects to frontend with ?authority=...")},
        description="Gateway callback. Redirects the user to the frontend, which then calls /api/payment/verify/."
    )
    def get(self, request):
        authority = request.GET.get("Authority")
        url = f"{settings.PAYMENT_FRONTEND_RETURN}?authority={authority}" if authority else settings.PAYMENT_FRONTEND_RETURN
        return HttpResponseRedirect(url)


class StartpaymentView(APIView):
    permission_classes = []
    @extend_schema(
        parameters=[StartPaymentSerializer],
        responses={302: OpenApiResponse(description="Redirects to new payment page")}
    )
    def get(self, request):
        authority = request.GET.get("authority")
        redirection_url = startpay(authority)
        return HttpResponseRedirect(redirection_url)