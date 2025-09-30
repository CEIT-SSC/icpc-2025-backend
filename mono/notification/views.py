from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import (
    SingleEmailSerializer, OtpRequestSerializer, StatusChangeSerializer,
    BulkJobCreateSerializer, BulkJobSerializer,
)
from .services import queue_single_email, create_bulk_job, send_otp, send_status_change_email


class SingleEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=SingleEmailSerializer,
        responses={202: OpenApiResponse(description="Queued")},
        description="Queue a single templated email."
    )
    def post(self, request):
        s = SingleEmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        queue_single_email(**s.validated_data)
        return Response(status=status.HTTP_202_ACCEPTED)


class OtpEmailView(APIView):
    permission_classes = []

    @extend_schema(
        request=OtpRequestSerializer,
        responses={202: OpenApiResponse(description="Queued")},
        description="Send an OTP email (delegates to provider/queue)."
    )
    def post(self, request):
        s = OtpRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        send_otp(destination=s.validated_data["to"], code=s.validated_data["code"], channel="email")
        return Response(status=status.HTTP_202_ACCEPTED)

class StatusChangeEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=StatusChangeSerializer,
        responses={202: OpenApiResponse(description="Queued")},
        description="Send a status-change email using a template code."
    )
    def post(self, request):
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        send_status_change_email(**s.validated_data)
        return Response(status=status.HTTP_202_ACCEPTED)

class BulkEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    @extend_schema(
        request=BulkJobCreateSerializer,
        responses={202: BulkJobSerializer},
        description="Create and enqueue a bulk email job (chunked + retried)."
    )
    def post(self, request):
        s = BulkJobCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        job = create_bulk_job(**s.validated_data)
        return Response(BulkJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)