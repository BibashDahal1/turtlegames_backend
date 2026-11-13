from django.test import TestCase
from rest_framework.test import APIClient

from visitors.cookies import cookie_name

from .models import Game


class PublicGameAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.game = Game.objects.create(
            slug="public-game",
            name="Public Game",
            tagline="A public game",
            blurb="Game details.",
            players="2-4",
            minutes="30",
            age="12+",
            language="English",
        )
        Game.objects.create(
            slug="unpublished-game",
            name="Unpublished Game",
            tagline="Not listed",
            blurb="Hidden details.",
            players="2-4",
            minutes="30",
            age="12+",
            language="English",
            is_published=False,
        )

    def test_anonymous_visitor_can_list_published_games(self):
        response = self.client.get("/api/games/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([game["slug"] for game in response.json()], [self.game.slug])

    def test_anonymous_visitor_can_read_published_game_details(self):
        response = self.client.get(f"/api/games/{self.game.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], self.game.name)

    def test_unpublished_game_details_remain_hidden(self):
        response = self.client.get("/api/games/unpublished-game/")

        self.assertEqual(response.status_code, 404)

    def test_invalid_visitor_cookie_does_not_block_public_browsing(self):
        self.client.cookies[cookie_name()] = "invalid-token"

        response = self.client.get("/api/games/")

        self.assertEqual(response.status_code, 200)
