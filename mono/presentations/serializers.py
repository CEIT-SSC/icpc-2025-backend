from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Course, Presenter, ScheduleRule, Registration

User = get_user_model()

class PresenterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Presenter
        fields = ("id", "full_name", "bio", "email", "website")

class ScheduleRuleSerializer(serializers.ModelSerializer):
    weekday_display = serializers.CharField(source="get_weekday_display", read_only=True)
    class Meta:
        model = ScheduleRule
        fields = ("weekday", "weekday_display", "start_time", "end_time")

class CourseSerializer(serializers.ModelSerializer):
    presenters = PresenterSerializer(many=True, read_only=True)
    schedule = ScheduleRuleSerializer(many=True, read_only=True)
    class Meta:
        model = Course
        fields = (
            "id", "name", "subtitle", "description", "presenters",
            "start_date", "online", "onsite", "classes_count",
            "capacity", "price", "slug", "is_active",
            "schedule",
        )

class RegistrationCreateSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    extra_answers = serializers.DictField(child=serializers.JSONField(), required=False)

class RegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = ("id", "course", "user", "status", "resume_url", "payment_link", "rejection_reason", "submitted_at", "decided_at")
        read_only_fields = ("user", "status", "payment_link", "rejection_reason", "submitted_at", "decided_at")