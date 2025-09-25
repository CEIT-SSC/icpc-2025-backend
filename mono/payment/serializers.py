from rest_framework import serializers
from .models import Payment

class InitiateSerializer(serializers.Serializer):
    target_type = serializers.ChoiceField(choices=Payment.TargetType.choices)
    target_id = serializers.IntegerField()
    amount = serializers.IntegerField(min_value=1)
    currency = serializers.CharField(required=False, allow_blank=True, default="IRR")
    description = serializers.CharField(required=False, allow_blank=True)

class InitiateResponseSerializer(serializers.Serializer):
    startpay_url = serializers.URLField()
    authority = serializers.CharField()
    payment_id = serializers.IntegerField()

class VerifySerializer(serializers.Serializer):
    authority = serializers.CharField()

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ("id","status","authority","ref_id","amount","currency","zarinpal_code","zarinpal_message","target_type","target_id")