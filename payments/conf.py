"""
All payment settings come from ENVIRONMENT VARIABLES (or Django settings of the same name).
Going live later = changing these values only, no code change:

    PAYMENT_MODE        test (default) or live
    FRONTEND_URL        where visitors are sent back after paying, e.g. http://localhost:3000
    KHALTI_SECRET_KEY   Khalti secret key (test key from test-admin.khalti.com, live key from admin.khalti.com)
    ESEWA_PRODUCT_CODE  eSewa merchant code      (test default: EPAYTEST)
    ESEWA_SECRET_KEY    eSewa secret key         (test default: the public UAT key from eSewa's docs)
    PAYMENT_MIN_AMOUNT  smallest amount in whole rupees (default 10, Khalti's minimum)
    PAYMENT_MAX_AMOUNT  largest amount in whole rupees (default 100000)

Optional overrides if a provider ever changes its addresses:
    KHALTI_BASE_URL, ESEWA_FORM_URL, ESEWA_STATUS_URL
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from decouple import config as env_config

# Published by eSewa for its test (UAT) environment. Used ONLY when PAYMENT_MODE=test.
TEST_ESEWA_PRODUCT_CODE = "EPAYTEST"
TEST_ESEWA_SECRET_KEY = "8gBm/:&EnhH.1/q"


class NotConfigured(Exception):
    """A provider's keys are missing."""


def _get(name, default=""):
    value = getattr(settings, name, None)
    if value is not None:
        return value
    return env_config(name, default=default)


def mode():
    value = str(_get("PAYMENT_MODE", "test")).strip().lower()
    if value not in ("test", "live"):
        raise ImproperlyConfigured("PAYMENT_MODE must be 'test' or 'live'.")
    return value


def is_test():
    return mode() == "test"


def frontend_url():
    return str(_get("FRONTEND_URL", "http://localhost:3000")).rstrip("/")


def currency():
    return getattr(settings, "SHOP_CURRENCY", "NPR")


def min_amount():
    return int(_get("PAYMENT_MIN_AMOUNT", 10))


def max_amount():
    return int(_get("PAYMENT_MAX_AMOUNT", 100000))


def khalti():
    secret = str(_get("KHALTI_SECRET_KEY", "")).strip()
    if not secret:
        raise NotConfigured("Khalti is not set up yet (KHALTI_SECRET_KEY is missing).")
    default = "https://dev.khalti.com/api/v2" if is_test() else "https://khalti.com/api/v2"
    return {
        "base_url": str(_get("KHALTI_BASE_URL", default)).rstrip("/"),
        "secret_key": secret,
    }


def esewa():
    if is_test():
        product_code = str(_get("ESEWA_PRODUCT_CODE", TEST_ESEWA_PRODUCT_CODE)).strip()
        secret = str(_get("ESEWA_SECRET_KEY", TEST_ESEWA_SECRET_KEY)).strip()
        form_url = _get(
            "ESEWA_FORM_URL", "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
        )
        # eSewa's own page and its other published docs name two different test hosts for the
        # status check, so both are tried, in this order, unless ESEWA_STATUS_URL is set.
        status_urls = [
            "https://rc.esewa.com.np/api/epay/transaction/status/",
            "https://uat.esewa.com.np/api/epay/transaction/status/",
        ]
    else:
        product_code = str(_get("ESEWA_PRODUCT_CODE", "")).strip()
        secret = str(_get("ESEWA_SECRET_KEY", "")).strip()
        form_url = _get("ESEWA_FORM_URL", "https://epay.esewa.com.np/api/epay/main/v2/form")
        status_urls = ["https://epay.esewa.com.np/api/epay/transaction/status/"]

    if not product_code or not secret:
        raise NotConfigured(
            "eSewa is not set up yet (ESEWA_PRODUCT_CODE and ESEWA_SECRET_KEY are needed)."
        )

    override = str(_get("ESEWA_STATUS_URL", "")).strip()
    if override:
        status_urls = [override]

    return {
        "form_url": str(form_url),
        "status_urls": status_urls,
        "product_code": product_code,
        "secret_key": secret,
    }