from django.conf import settings

# Optional overrides in settings.py: VISITOR_COOKIE_NAME, VISITOR_COOKIE_MAX_AGE, VISITOR_COOKIE_SECURE.
# Browsers cap a cookie's life at about 400 days, so that is the longest "stay signed in" can last.


def cookie_name() -> str:
    return getattr(settings, "VISITOR_COOKIE_NAME", "visitor_token")


def cookie_max_age() -> int:
    return getattr(settings, "VISITOR_COOKIE_MAX_AGE", 60 * 60 * 24 * 400)


def cookie_secure() -> bool:
    # HTTPS only in production; plain http is fine while DEBUG is on (local development).
    return getattr(settings, "VISITOR_COOKIE_SECURE", not settings.DEBUG)


def set_token_cookie(response, raw_key: str) -> None:
    """
    HttpOnly: JavaScript on the page cannot read the token, so an injected script cannot steal it.
    SameSite=Lax: the browser does not send it on cross-site POST requests (blocks CSRF).
    """
    response.set_cookie(
        cookie_name(),
        raw_key,
        max_age=cookie_max_age(),
        httponly=True,
        secure=cookie_secure(),
        samesite="Lax",
        path="/",
    )


def clear_token_cookie(response) -> None:
    response.delete_cookie(cookie_name(), path="/", samesite="Lax")