from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from games.models import Game
from visitors.permissions import IsVisitor

from .cart_serializers import (
    CartAddSerializer,
    CartDetailsSerializer,
    CartQuantitySerializer,
)
from .models import Cart, CartItem

MAX_GAMES_IN_CART = 20

# ---------------------------------------------------------------------------------------------
# The cart. There is no separate order: the server keeps ONE cart per visitor (games, quantities
# and delivery details) and you read it in the admin. The server is the single source of truth:
# every change is one small request and every reply is the WHOLE cart as it now stands.
# Only game slugs and quantities are stored; prices are always read from the games.
# ---------------------------------------------------------------------------------------------


class CartThrottle(UserRateThrottle):
    """Per visitor. The rate is set here, so no change to settings.py is needed."""

    scope = "cart"
    rate = "1200/hour"


def max_quantity():
    return getattr(settings, "SHOP_MAX_QUANTITY_PER_ITEM", 10)


def details_payload(cart):
    """The visitor's saved details, or None until they have saved some."""
    if cart.details_updated_at is None:
        return None
    return {
        "firstName": cart.first_name,
        "middleName": cart.middle_name,
        "lastName": cart.last_name,
        "email": cart.email,
        "phone": cart.phone,
        "country": cart.country,
        "city": cart.city,
        "address": cart.address,
        "landmark": cart.landmark,
        "note": cart.note,
    }


def cart_payload(cart):
    if cart is None:
        return {"items": [], "details": None}
    return {
        "items": [
            {"slug": item.game.slug, "quantity": item.quantity}
            for item in cart.items.select_related("game")
        ],
        "details": details_payload(cart),
    }


def touch(cart):
    cart.save(update_fields=["updated_at"])


def set_quantity(cart, game, quantity):
    """Sets one game's quantity in the cart (0 or less removes it). Call inside a transaction."""
    item = cart.items.select_for_update().filter(game=game).first()

    if quantity <= 0:
        if item:
            item.delete()
        return

    quantity = min(quantity, max_quantity())
    if item:
        item.quantity = quantity
        item.save(update_fields=["quantity"])
        return

    if cart.items.count() >= MAX_GAMES_IN_CART:
        raise ValidationError(
            {"slug": [f"A cart can hold at most {MAX_GAMES_IN_CART} different games."]}
        )
    CartItem.objects.create(cart=cart, game=game, quantity=quantity)


class CartView(APIView):
    """GET /api/orders/cart/ : the signed-in visitor's cart (games and saved details)."""

    permission_classes = [IsVisitor]
    throttle_classes = [CartThrottle]

    def get(self, request):
        cart = Cart.objects.filter(visitor=request.user).first()
        return Response(cart_payload(cart))


class CartItemsView(APIView):
    """POST /api/orders/cart/items/ {slug, quantity=1} : adds to the cart. Replies with the whole cart."""

    permission_classes = [IsVisitor]
    throttle_classes = [CartThrottle]

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        slug = serializer.validated_data["slug"]
        quantity = serializer.validated_data["quantity"]

        game = Game.objects.filter(slug=slug).first()
        if game is None:
            raise ValidationError({"slug": ["This game does not exist."]})

        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(visitor=request.user)
            existing = cart.items.filter(game=game).first()
            current = existing.quantity if existing else 0
            set_quantity(cart, game, current + quantity)
            touch(cart)

        return Response(cart_payload(cart))


class CartItemDetailView(APIView):
    """
    PATCH  /api/orders/cart/items/<slug>/ {quantity} : sets the quantity (0 removes the game).
    DELETE /api/orders/cart/items/<slug>/            : removes the game.
    Both reply with the whole cart.
    """

    permission_classes = [IsVisitor]
    throttle_classes = [CartThrottle]

    def patch(self, request, slug):
        serializer = CartQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quantity = serializer.validated_data["quantity"]

        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(visitor=request.user)
            game = Game.objects.filter(slug=slug).first()
            if game is not None:  # a game that no longer exists has nothing left to change
                set_quantity(cart, game, quantity)
            touch(cart)

        return Response(cart_payload(cart))

    def delete(self, request, slug):
        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(visitor=request.user)
            cart.items.filter(game__slug=slug).delete()
            touch(cart)

        return Response(cart_payload(cart))


class CartDetailsView(APIView):
    """
    PUT /api/orders/cart/details/ : saves the delivery details the visitor gives so you can contact
    them (by phone or email) and arrange payment and delivery. They appear on the cart in the admin.
    """

    permission_classes = [IsVisitor]
    throttle_classes = [CartThrottle]

    def put(self, request):
        serializer = CartDetailsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            cart, _ = Cart.objects.get_or_create(visitor=request.user)
            if not cart.items.exists():
                raise ValidationError({"items": ["Your cart is empty. Add a game first."]})

            for field, value in serializer.validated_data.items():
                setattr(cart, field, value)
            cart.details_updated_at = timezone.now()
            cart.save()

        return Response(cart_payload(cart))