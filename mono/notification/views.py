from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from .serializers import (
    SingleEmailSerializer, OtpRequestSerializer, StatusChangeSerializer,
    BulkJobCreateSerializer, BulkJobSerializer,
)
from .services import queue_single_email, create_bulk_job, send_otp, send_status_change_email

class HealthView(APIView):
    permission_classes = []
    def get(self, request):
        return Response({"ok": True, "app": "notification"})

class SingleEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request):
        s = SingleEmailSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        queue_single_email(**s.validated_data)
        return Response(status=status.HTTP_202_ACCEPTED)

class OtpEmailView(APIView):
    permission_classes = []  # allow internal use or secure by shared secret / network rules
    def post(self, request):
        s = OtpRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        send_otp(destination=s.validated_data["to"], code=s.validated_data["code"], channel="email")
        return Response(status=status.HTTP_202_ACCEPTED)

class StatusChangeEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request):
        s = StatusChangeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        send_status_change_email(**s.validated_data)
        return Response(status=status.HTTP_202_ACCEPTED)

class BulkEmailView(APIView):
    permission_classes = [permissions.IsAdminUser]
    def post(self, request):
        s = BulkJobCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        job = create_bulk_job(**s.validated_data)
        return Response(BulkJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)