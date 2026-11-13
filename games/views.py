from django.db.models import Prefetch
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Game, GameRule
from .serializers import GameSerializer


@method_decorator(never_cache, name="dispatch")
class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public, read-only API for the website.

      GET /api/games/          -> list of published games (with their cards and rules)
      GET /api/games/<slug>/   -> one published game

    Games, cards and rules can only be created or changed in the Django admin
    (superuser only). This API has no write endpoints at all.

    No authentication is attempted on these endpoints, so public browsing also works when a
    browser happens to send an expired or invalid visitor cookie.
    """

    serializer_class = GameSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = None  # the frontend expects a plain array

    def get_queryset(self):
        return Game.objects.filter(is_published=True).prefetch_related(
            "cards",
            Prefetch("rules", queryset=GameRule.objects.order_by("order", "id")),
        )