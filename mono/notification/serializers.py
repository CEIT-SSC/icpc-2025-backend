from rest_framework import serializers
from .models import EmailTemplate, BulkJob

class SingleEmailSerializer(serializers.Serializer):
    to = serializers.EmailField()
    template_code = serializers.CharField()
    context = serializers.JSONField(default=dict)

class HealthResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    app = serializers.CharField()

class OtpRequestSerializer(serializers.Serializer):
    to = serializers.EmailField()
    code = serializers.CharField()

class StatusChangeSerializer(serializers.Serializer):
    to = serializers.EmailField()
    status_code = serializers.CharField()
    extra = serializers.JSONField(required=False)

class BulkJobCreateSerializer(serializers.Serializer):
    template_code = serializers.CharField()
    recipients = serializers.ListField(child=serializers.DictField(), min_length=1)
    job_type = serializers.ChoiceField(choices=["generic", "reminder", "invite"], default="generic")

class BulkJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = BulkJob
        fields = ("id", "job_type", "status", "total", "sent", "failed", "created_at", "started_at", "finished_at")