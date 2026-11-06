from django.db.models import Prefetch
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import viewsets

from visitors.permissions import IsVisitor

from .models import Game, GameRule
from .serializers import GameSerializer


@method_decorator(never_cache, name="dispatch")
class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only API for the website. Only registered visitors (valid visitor token) can read it.

      GET /api/games/          -> list of published games (with their cards and rules)
      GET /api/games/<slug>/   -> one published game

    Games, cards and rules can only be created or changed in the Django admin
    (superuser only). This API has no write endpoints at all.

    never_cache: the answer depends on who is signed in and changes whenever you edit a game
    in the admin, so browsers and proxies must not keep an old copy.

    To make the games public again, replace IsVisitor with AllowAny below.
    """

    serializer_class = GameSerializer
    permission_classes = [IsVisitor]
    lookup_field = "slug"
    pagination_class = None  # the frontend expects a plain array

    def get_queryset(self):
        return Game.objects.filter(is_published=True).prefetch_related(
            "cards",
            Prefetch("rules", queryset=GameRule.objects.order_by("order", "id")),
        )