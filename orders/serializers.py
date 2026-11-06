from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from games.models import Game
from visitors.serializers import PHONE_RE, clean_name

from .models import Order, OrderItem

MAX_LINES_PER_ORDER = 20


class OrderItemInputSerializer(serializers.Serializer):
    slug = serializers.SlugField(max_length=100)
    quantity = serializers.IntegerField(min_value=1)


class OrderCreateSerializer(serializers.Serializer):
    """
    Input for POST /api/orders/ (camelCase, like the rest of the API).
    Prices are NEVER taken from the request: they are read from the database.
    """

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
    items = OrderItemInputSerializer(many=True, allow_empty=False)

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

    def validate_items(self, items):
        if len(items) > MAX_LINES_PER_ORDER:
            raise serializers.ValidationError(
                f"An order can have at most {MAX_LINES_PER_ORDER} different games."
            )

        # The same game listed twice is added together.
        quantities = {}
        for item in items:
            quantities[item["slug"]] = quantities.get(item["slug"], 0) + item["quantity"]

        max_quantity = getattr(settings, "SHOP_MAX_QUANTITY_PER_ITEM", 10)
        games = {
            g.slug: g
            for g in Game.objects.filter(
                slug__in=quantities, is_published=True, price__isnull=False
            )
        }

        lines, errors = [], []
        for slug, quantity in quantities.items():
            game = games.get(slug)
            if game is None:
                errors.append(f"'{slug}' is not available to order.")
            elif quantity > max_quantity:
                errors.append(f"You can order at most {max_quantity} of {game.name}.")
            else:
                lines.append((game, quantity))

        if errors:
            raise serializers.ValidationError(errors)
        return lines

    @transaction.atomic
    def create(self, validated_data):
        visitor = self.context["request"].user
        lines = validated_data.pop("items")
        currency = getattr(settings, "SHOP_CURRENCY", "NPR")
        total = sum((game.price * quantity for game, quantity in lines), Decimal("0"))

        order = Order.objects.create(
            visitor=visitor, total=total, currency=currency, **validated_data
        )
        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    game=game,
                    game_name=game.name,
                    unit_price=game.price,
                    quantity=quantity,
                )
                for game, quantity in lines
            ]
        )
        return order


def order_confirmation(order: Order) -> dict:
    """What the buyer sees right after ordering."""
    return {
        "reference": order.reference,
        "status": order.status,
        "currency": order.currency,
        "total": float(order.total),
        "createdAt": order.created_at.isoformat(),
        "items": [
            {
                "name": item.game_name,
                "quantity": item.quantity,
                "unitPrice": float(item.unit_price),
                "lineTotal": float(item.line_total),
            }
            for item in order.items.all()
        ],
    }