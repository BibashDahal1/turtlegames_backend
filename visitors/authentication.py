from datetime import timedelta

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .cookies import cookie_name
from .models import Visitor, VisitorToken

LAST_SEEN_EVERY = timedelta(minutes=5)


class CookieTokenAuthentication(BaseAuthentication):
    """
    Signs a visitor in from the HttpOnly cookie set by /api/visitors/register/.
    Only the SHA-256 hash of the token is looked up, exactly as before.
    """

    def authenticate(self, request):
        raw_key = request.COOKIES.get(cookie_name())
        if not raw_key:
            return None  # no cookie: anonymous, IsVisitor will refuse

        try:
            token = VisitorToken.objects.select_related("visitor").get(
                key_hash=VisitorToken.hash_key(raw_key)
            )
        except VisitorToken.DoesNotExist:
            raise AuthenticationFailed("Invalid token.")

        visitor = token.visitor
        if not visitor.is_active:
            raise AuthenticationFailed("This visitor has been blocked.")

        # Record activity, but at most once every few minutes (not on every request).
        now = timezone.now()
        if visitor.last_seen_at is None or now - visitor.last_seen_at > LAST_SEEN_EVERY:
            Visitor.objects.filter(pk=visitor.pk).update(last_seen_at=now)

        return (visitor, token)

    def authenticate_header(self, request):
        # Makes DRF answer 401 (not 403) when nobody is signed in, which the frontend relies on.
        return "Cookie"