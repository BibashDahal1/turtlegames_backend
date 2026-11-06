from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .cookies import clear_token_cookie, cookie_name, set_token_cookie
from .models import Visitor, VisitorToken
from .permissions import IsVisitor
from .serializers import RegisterSerializer


class RegisterView(APIView):
    """
    POST /api/visitors/register/

    First visit: creates the visitor and signs them in (201).
    Same email again (cleared browser, new phone...): signs that visitor in on this browser (200)
    and does NOT change the stored details. The reply only echoes what was just typed,
    so nobody can read someone else's stored name by guessing their email.

    The sign-in token is sent ONLY as an HttpOnly cookie. It is never in the response body.

    Note: emails are not verified. This gate collects visitor details; it is not strong security.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "visitor_register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = dict(serializer.validated_data)
        data.pop("consent")
        email = data.pop("email")

        with transaction.atomic():
            visitor, created = Visitor.objects.get_or_create(
                email=email,
                defaults={**data, "consent_given_at": timezone.now()},
            )
            if not visitor.is_active:
                return Response(
                    {"detail": "This visitor has been blocked."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            raw_key = VisitorToken.issue(visitor)

        response = Response(
            {
                "returning": not created,
                "visitor": {
                    "firstName": data["first_name"],
                    "middleName": data.get("middle_name", ""),
                    "lastName": data["last_name"],
                },
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
        set_token_cookie(response, raw_key)
        return response


class MeView(APIView):
    """
    GET /api/visitors/me/ : who is signed in? The frontend calls this on every page load.
    It also renews the cookie, so a visitor who keeps coming back stays signed in.
    """

    permission_classes = [IsVisitor]

    def get(self, request):
        visitor = request.user
        response = Response(
            {
                "id": visitor.pk,
                "firstName": visitor.first_name,
                "middleName": visitor.middle_name,
                "lastName": visitor.last_name,
                # The visitor's own saved details: the shop uses them to pre-fill the order form.
                "email": visitor.email,
                "phone": visitor.phone,
                "country": visitor.country,
                "city": visitor.city,
            }
        )
        set_token_cookie(response, request.COOKIES[cookie_name()])
        return response


class LogoutView(APIView):
    """
    POST /api/visitors/logout/ : forgets this browser's token only (other devices stay signed in).
    Always succeeds and always clears the cookie, even if the token was already deleted in the admin.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_key = request.COOKIES.get(cookie_name())
        if raw_key:
            VisitorToken.objects.filter(key_hash=VisitorToken.hash_key(raw_key)).delete()

        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_token_cookie(response)
        return response