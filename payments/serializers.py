from rest_framework import serializers

from . import conf
from .models import Payment


class StartSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=Payment.Provider.choices)
    # Whole rupees only: it keeps the amount identical in every message sent to the providers.
    amount = serializers.IntegerField()

    def validate_amount(self, value):
        low, high = conf.min_amount(), conf.max_amount()
        if value < low or value > high:
            raise serializers.ValidationError(
                f"Enter a whole amount between Rs {low:,} and Rs {high:,}."
            )
        return value


class VerifySerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=40)
    # eSewa's Base64 `data` from the success redirect (absent for Khalti and for failures).
    data = serializers.CharField(required=False, allow_blank=True, default="", max_length=8000)