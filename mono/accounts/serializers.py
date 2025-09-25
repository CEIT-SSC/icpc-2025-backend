from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import UserExtraData

User = get_user_model()

class SignupStartSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_blank=True)

class LoginStartSerializer(serializers.Serializer):
    email = serializers.EmailField()

class OtpVerifySerializer(serializers.Serializer):
    token = serializers.CharField()
    code = serializers.CharField()

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone_number", "is_email_verified")
        read_only_fields = ("email", "is_email_verified")

class UserExtraDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserExtraData
        fields = ("codeforces_handle", "codeforces_score", "achievements", "answers", "updated_at")
        read_only_fields = ("updated_at",)