from rest_framework import serializers

from visitors.serializers import PHONE_RE, clean_name


class CartAddSerializer(serializers.Serializer):
    """Input for POST /api/orders/cart/items/ : add this many of a game to the cart."""

    slug = serializers.SlugField(max_length=100)
    quantity = serializers.IntegerField(min_value=1, max_value=1000, default=1)


class CartQuantitySerializer(serializers.Serializer):
    """Input for PATCH /api/orders/cart/items/<slug>/ : set the quantity (0 removes the game)."""

    quantity = serializers.IntegerField(min_value=0, max_value=1000)


class CartDetailsSerializer(serializers.Serializer):
    """Input for PUT /api/orders/cart/details/ (camelCase, like the rest of the API)."""

    firstName = serializers.CharField(source="first_name", max_length=50)
    middleName = serializers.CharField(
        source="middle_name", max_length=50, required=False, allow_blank=True, default=""
    )
    lastName = serializers.CharField(source="last_name", max_length=50)
    email = serializers.EmailField(max_length=254)
    phone = serializers.CharField(max_length=20)
    country = serializers.CharField(max_length=80)
    city = serializers.CharField(max_length=80)
    address = serializers.CharField(max_length=250)
    landmark = serializers.CharField(
        max_length=150, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )

    def validate_firstName(self, value):
        return clean_name(value)

    def validate_middleName(self, value):
        return clean_name(value) if value.strip() else ""

    def validate_lastName(self, value):
        return clean_name(value)

    def validate_email(self, value):
        return value.strip().lower()

    def validate_phone(self, value):
        value = value.strip()
        if not PHONE_RE.match(value):
            raise serializers.ValidationError(
                "Enter a valid phone number, for example +977 9800000000."
            )
        return value

    def validate_country(self, value):
        return " ".join(value.split())

    def validate_city(self, value):
        return " ".join(value.split())

    def validate_address(self, value):
        value = " ".join(value.split())
        if len(value) < 5:
            raise serializers.ValidationError("Enter the full delivery address.")
        return value

    def validate_landmark(self, value):
        return " ".join(value.split())

    def validate_note(self, value):
        return value.strip()