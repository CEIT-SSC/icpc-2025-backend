# payment/views.py

from django.conf import settings
from django.http import HttpResponseRedirect
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .serializers import (
    InitiateSerializer,
    InitiateResponseSerializer,
    VerifySerializer,
    PaymentSerializer,
)
from .services import initiate_payment_for_target, verify_by_authority
from .models import Payment


class InitiatePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=InitiateSerializer,
        responses={
            201: InitiateResponseSerializer,
            401: OpenApiResponse(description="Unauthenticated"),
            409: OpenApiResponse(description="Conflict or gateway initiate error"),
        },
        description="Create a Zarinpal payment for a target (competition/course) and get the StartPay URL."
    )
    def post(self, request):
        s = InitiateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            result = initiate_payment_for_target(
                user=request.user,
                target_type=data["target_type"],
                target_id=data["target_id"],
                amount=data["amount"],
                description=data.get("description", ""),
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)

        resp = InitiateResponseSerializer({
            "startpay_url": result.url,
            "authority": result.payment.authority,
            "payment_id": result.payment.id,
        }).data
        return Response(resp, status=status.HTTP_201_CREATED)


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
