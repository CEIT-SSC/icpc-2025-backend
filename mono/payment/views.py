from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from django.conf import settings
from django.http import HttpResponseRedirect
from .serializers import InitiateSerializer, InitiateResponseSerializer, VerifySerializer, PaymentSerializer
from .services import initiate_payment_for_target, verify_by_authority
from .models import Payment

class InitiatePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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
                currency=data.get("currency", "IRR"),
                description=data.get("description", ""),
            )
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        resp = InitiateResponseSerializer({
            "startpay_url": result.url,
            "authority": result.payment.authority,
            "payment_id": result.payment.id,
        }).data
        return Response(resp, status=201)

class VerifyPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = VerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        p = verify_by_authority(user=request.user, authority=s.validated_data["authority"])
        return Response(PaymentSerializer(p).data)

class CallbackView(APIView):
    permission_classes = []  # Zarinpal will hit this URL

    def get(self, request):
        authority = request.GET.get("Authority")
        # We cannot verify by user context here; redirect frontend with authority
        # so frontend calls /verify with the logged-in user.
        url = f"{settings.PAYMENT_FRONTEND_RETURN}?authority={authority}"
        return HttpResponseRedirect(url)