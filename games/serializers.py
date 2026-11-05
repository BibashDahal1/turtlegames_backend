from rest_framework import serializers

from .models import Game, GameCard


def image_url(resource):
    """Full https Cloudinary URL for an image field, or None if empty."""
    if resource and hasattr(resource, "url"):
        return resource.url
    return None


class GameCardSerializer(serializers.ModelSerializer):
    """Matches the frontend GameCardInfo interface (camelCase keys)."""

    nameNative = serializers.CharField(source="name_native", read_only=True)
    quoteEn = serializers.CharField(source="quote_en", read_only=True)
    image = serializers.SerializerMethodField()

    class Meta:
        model = GameCard
        fields = ["name", "nameNative", "image", "description", "quote", "quoteEn"]

    def get_image(self, obj):
        return image_url(obj.image)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # The frontend treats these as optional: leave the key out when empty.
        for key in ("nameNative", "quote", "quoteEn"):
            if not data.get(key):
                data.pop(key, None)
        return data


class GameSerializer(serializers.ModelSerializer):
    """Matches the frontend Game interface (camelCase keys)."""

    nameNative = serializers.CharField(source="name_native", read_only=True)
    blurb = serializers.SerializerMethodField()
    box = serializers.SerializerMethodField()
    cardBack = serializers.SerializerMethodField()
    cards = GameCardSerializer(many=True, read_only=True)

    class Meta:
        model = Game
        fields = [
            "slug",
            "name",
            "nameNative",
            "tagline",
            "blurb",
            "players",
            "minutes",
            "age",
            "language",
            "color",
            "color2",
            "accent",
            "box",
            "cardBack",
            "cards",
        ]

    def get_blurb(self, obj):
        return obj.blurb_paragraphs

    def get_box(self, obj):
        return {
            "front": image_url(obj.box_front),
            "back": image_url(obj.box_back),
            "left": image_url(obj.box_left),
            "right": image_url(obj.box_right),
            "top": image_url(obj.box_top),
            "bottom": image_url(obj.box_bottom),
        }

    def get_cardBack(self, obj):
        return image_url(obj.card_back)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for key in ("nameNative", "cardBack"):
            if not data.get(key):
                data.pop(key, None)
        return data