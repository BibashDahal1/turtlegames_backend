from django.test import SimpleTestCase
from rest_framework.test import APIClient


class AnonymousCartAccessTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()

    def test_cart_requires_sign_in(self):
        response = self.client.get("/api/orders/cart/")

        self.assertEqual(response.status_code, 401)

    def test_adding_to_cart_requires_sign_in(self):
        response = self.client.post(
            "/api/orders/cart/items/",
            {"slug": "a-game", "quantity": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
