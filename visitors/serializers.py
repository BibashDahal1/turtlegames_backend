import re
import unicodedata

from django.conf import settings
from rest_framework import serializers

PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")
NAME_PUNCTUATION = set(" -'’.")


def clean_name(value: str) -> str:
    """
    Accepts names in any script, including Nepali (Devanagari vowel signs are
    "marks", not letters, so a plain \\w regex would wrongly reject them).
    """
    value = " ".join(value.split())
    has_letter = False

    for ch in value:
        category = unicodedata.category(ch)
        if category[0] == "L":
            has_letter = True
        elif category[0] != "M" and ch not in NAME_PUNCTUATION:
            raise serializers.ValidationError(
                "Use letters only (spaces, hyphens and apostrophes are fine)."
            )

    if not has_letter:
        raise serializers.ValidationError("Enter a valid name.")
    return value


class RegisterSerializer(serializers.Serializer):
    """Input for POST /api/visitors/register/ (camelCase, like the rest of the API)."""

    firstName = serializers.CharField(source="first_name", max_length=50)
    middleName = serializers.CharField(
        source="middle_name", max_length=50, required=False, allow_blank=True, default=""
    )
    lastName = serializers.CharField(source="last_name", max_length=50)
    age = serializers.IntegerField()
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )
    country = serializers.CharField(max_length=80)
    city = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    consent = serializers.BooleanField()

    def validate_firstName(self, value):
        return clean_name(value)

    def validate_middleName(self, value):
        return clean_name(value) if value.strip() else ""

    def validate_lastName(self, value):
        return clean_name(value)

    def validate_age(self, value):
        minimum = getattr(settings, "VISITOR_MIN_AGE", 13)
        if value < minimum:
            raise serializers.ValidationError(f"You must be at least {minimum} to enter.")
        if value > 120:
            raise serializers.ValidationError("Enter a valid age.")
        return value

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        value = value.strip()
        if value and not PHONE_RE.match(value):
            raise serializers.ValidationError("Enter a valid phone number.")
        return value

    def validate_country(self, value):
        return " ".join(value.split())

    def validate_city(self, value):
        return " ".join(value.split())

    def validate_consent(self, value):
        if value is not True:
            raise serializers.ValidationError("You need to agree to continue.")
        return value