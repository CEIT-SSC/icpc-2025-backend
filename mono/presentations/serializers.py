from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Course, Presenter, ScheduleRule, Registration, RegistrationItem

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


class ChildCourseSerializer(serializers.ModelSerializer):
    schedule = ScheduleRuleSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ("id", "name", "capacity", "price", "slug", "is_active", "schedule")


class CourseSerializer(serializers.ModelSerializer):
    presenters = PresenterSerializer(many=True, read_only=True)
    schedule = ScheduleRuleSerializer(many=True, read_only=True)
    children = ChildCourseSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "name",
            "subtitle",
            "description",
            "presenters",
            "start_date",
            "online",
            "onsite",
            "classes_count",
            "capacity",
            "remained_capacity",
            "price",
            "requires_approval",
            "slug",
            "is_active",
            "schedule",
            "children",
        )


class RegistrationItemSerializer(serializers.ModelSerializer):
    child = ChildCourseSerializer(source="child_course", read_only=True)

    class Meta:
        model = RegistrationItem
        fields = ("id", "child", "price", "created_at")


class RegistrationCreateSerializer(serializers.Serializer):
    course_id = serializers.IntegerField()
    child_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    extra_answers = serializers.DictField(
        child=serializers.JSONField(), required=False
    )


class RegistrationSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    items = RegistrationItemSerializer(many=True, read_only=True)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Registration
        fields = (
            "id",
            "course",
            "user",
            "status",
            "resume_url",
            "payment_link",
            "rejection_reason",
            "submitted_at",
            "decided_at",
            "items",
            "total_amount",
        )
        read_only_fields = (
            "user",
            "status",
            "payment_link",
            "rejection_reason",
            "submitted_at",
            "decided_at",
            "items",
            "total_amount",
        )

    def get_total_amount(self, obj: Registration) -> int:
        base = obj.course.price or 0
        extra = sum((i.price or 0) for i in obj.items.all())
        return base + extra
