from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Game
from .serializers import GameSerializer


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Public, read-only API for the website.

      GET /api/games/          -> list of published games (with their cards)
      GET /api/games/<slug>/   -> one published game

    Games and cards can only be created or changed in the Django admin
    (superuser only). This API has no write endpoints at all.
    """

    serializer_class = GameSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"
    pagination_class = None  # the frontend expects a plain array

    def get_queryset(self):
        return Game.objects.filter(is_published=True).prefetch_related("cards")