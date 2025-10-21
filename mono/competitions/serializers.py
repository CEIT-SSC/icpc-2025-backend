from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Competition, CompetitionFieldConfig, TeamRequest, TeamMember, FieldRequirement

User = get_user_model()

class CompetitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Competition
        fields = ("id","name","slug","description","min_team_size","max_team_size","signup_fee","requires_backoffice_approval","is_active")

class MemberApproveResponseSerializer(serializers.Serializer):
    member = serializers.IntegerField()
    status = serializers.CharField()


class FieldConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompetitionFieldConfig
        fields = ("first_name","last_name","national_id","student_card_image","national_id_image","tshirt_size","phone_number","email", 'student_number', 'university_name')

class ParticipantPayloadSerializer(serializers.Serializer):
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    email = serializers.EmailField()
    phone_number = serializers.CharField()
    national_id = serializers.CharField(required=False, allow_blank=True)
    student_card_image = serializers.URLField(required=False, allow_blank=True)
    national_id_image = serializers.URLField(required=False, allow_blank=True)
    tshirt_size = serializers.CharField(required=False, allow_blank=True)
    student_number = serializers.CharField(required=False, allow_blank=True)
    university_name = serializers.CharField(required=False, allow_blank=True)

class TeamRequestCreateSerializer(serializers.Serializer):
    competition_id = serializers.IntegerField()
    team_name = serializers.CharField(required=False, allow_blank=True)
    participants = serializers.ListField(child=ParticipantPayloadSerializer(), min_length=1)

class TeamMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamMember
        fields = ("id", "first_name", "last_name", "email", "phone_number", "national_id", "student_card_image",
                  "national_id_image", "tshirt_size", "approval_status", "approval_at", "student_number", "university_name")

class TeamRequestSerializer(serializers.ModelSerializer):
    members = TeamMemberSerializer(many=True, read_only=True)
    class Meta:
        model = TeamRequest
        fields = ("id","competition","team_name","status","payment_link","created_at","members")
        read_only_fields = ("status","payment_link","created_at")

class ApproveTokenSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()
    token = serializers.CharField()
    accept = serializers.BooleanField()

class CancelRequestSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()