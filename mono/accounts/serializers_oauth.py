from rest_framework import serializers

class AccessTokenSerializer(serializers.Serializer):
    access = serializers.CharField()
