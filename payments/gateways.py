"""
Talks to Khalti and eSewa. Uses only the Python standard library (no extra packages).
Written from the providers' official documentation:
  Khalti ePayment (KPG-2):  https://docs.khalti.com/khalti-epayment/
  eSewa ePay v2:            https://developer.esewa.com.np/pages/Epay-V2
"""

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request

from . import conf


class GatewayError(Exception):
    """The provider refused the request, or answered something we cannot trust or understand."""


class VerificationError(GatewayError):
    """A payment response failed its security check."""


class GatewayUnavailable(Exception):
    """The provider could not be reached (network problem or timeout)."""


def _request(method, url, headers=None, payload=None, timeout=20):
    """Returns (http_status, parsed_json). Error statuses are returned, not raised."""
    all_headers = {"Accept": "application/json"}
    if headers:
        all_headers.update(headers)

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        all_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=all_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, body = response.status, response.read()
    except urllib.error.HTTPError as error:  # must come before URLError (it is a subclass)
        status, body = error.code, error.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise GatewayUnavailable(str(error)) from error

    try:
        parsed = json.loads(body.decode("utf-8") or "{}")
    except ValueError:
        parsed = {"raw": body[:300].decode("utf-8", "replace")}
    return status, parsed


def _describe(body):
    """A short, readable version of a provider's error body."""
    if isinstance(body, dict):
        parts = []
        for key, value in body.items():
            if key in ("error_key", "status_code"):
                continue
            if isinstance(value, list):
                parts.append(" ".join(str(item) for item in value))
            else:
                parts.append(str(value))
        if parts:
            return " ".join(parts)[:300]
    return "unexpected answer"


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------
# Khalti
# ------------------------------------------------------------------------------------------


def khalti_initiate(*, reference, paisa, name, return_url, website_url):
    """Starts a payment. Returns (pidx, payment_url). `paisa` is an integer (Rs 1 = 100 paisa)."""
    cfg = conf.khalti()
    status, body = _request(
        "POST",
        f"{cfg['base_url']}/epayment/initiate/",
        {"Authorization": f"Key {cfg['secret_key']}"},
        {
            "return_url": return_url,
            "website_url": website_url,
            "amount": paisa,
            "purchase_order_id": reference,
            "purchase_order_name": name,
        },
    )
    if status == 401:
        raise GatewayError("Khalti rejected the secret key (check KHALTI_SECRET_KEY).")
    if status != 200 or not isinstance(body, dict) or not body.get("pidx") or not body.get("payment_url"):
        raise GatewayError(_describe(body))
    return str(body["pidx"]), str(body["payment_url"])


def khalti_lookup(pidx):
    """
    Asks Khalti for the real status of a payment. This, not the browser redirect, decides.
    Returns {"status", "amount" (paisa), "transaction_id", "raw"}.
    Khalti answers 400 for expired and cancelled payments but still includes the status.
    """
    cfg = conf.khalti()
    status, body = _request(
        "POST",
        f"{cfg['base_url']}/epayment/lookup/",
        {"Authorization": f"Key {cfg['secret_key']}"},
        {"pidx": pidx},
    )
    if status == 401:
        raise GatewayError("Khalti rejected the secret key (check KHALTI_SECRET_KEY).")
    if not isinstance(body, dict) or "status" not in body:
        raise GatewayError("Khalti could not find this payment: " + _describe(body))
    return {
        "status": str(body["status"]),
        "amount": _to_int(body.get("total_amount")),
        "transaction_id": str(body.get("transaction_id") or ""),
        "raw": body,
    }


# ------------------------------------------------------------------------------------------
# eSewa
# ------------------------------------------------------------------------------------------


def esewa_sign(secret_key, message):
    """HMAC-SHA256 of `message`, base64 encoded (as eSewa's docs describe)."""
    digest = hmac.new(secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def esewa_form(*, reference, amount, success_url, failure_url):
    """
    The fields the browser must POST to eSewa to start a payment. `amount` is a whole number of rupees.
    Returns (form_action_url, fields).
    """
    cfg = conf.esewa()
    total = str(int(amount))
    signed_names = "total_amount,transaction_uuid,product_code"
    fields = {
        "amount": total,
        "tax_amount": "0",
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "total_amount": total,
        "transaction_uuid": reference,
        "product_code": cfg["product_code"],
        "success_url": success_url,
        "failure_url": failure_url,
        "signed_field_names": signed_names,
    }
    message = ",".join(f"{name}={fields[name]}" for name in signed_names.split(","))
    fields["signature"] = esewa_sign(cfg["secret_key"], message)
    return cfg["form_url"], fields


def esewa_decode(data):
    """
    Reads the Base64 `data` eSewa adds to the success redirect and checks its signature.
    Raises VerificationError if it was tampered with. Returns the decoded fields (all text).
    """
    cfg = conf.esewa()
    try:
        padded = data + "=" * (-len(data) % 4)
        raw = base64.b64decode(padded)
        # parse_int / parse_float keep numbers as the exact text eSewa signed
        body = json.loads(raw.decode("utf-8"), parse_float=str, parse_int=str)
    except (ValueError, UnicodeDecodeError) as error:
        raise VerificationError("The payment response could not be read.") from error

    if not isinstance(body, dict) or "signature" not in body or "signed_field_names" not in body:
        raise VerificationError("The payment response is incomplete.")

    names = [name.strip() for name in str(body["signed_field_names"]).split(",") if name.strip()]
    try:
        message = ",".join(f"{name}={body[name]}" for name in names)
    except KeyError as error:
        raise VerificationError("The payment response is incomplete.") from error

    expected = esewa_sign(cfg["secret_key"], message)
    if not hmac.compare_digest(expected, str(body["signature"])):
        raise VerificationError("The payment response failed its security check.")
    return body


def esewa_status(reference, amount):
    """
    Asks eSewa for the real status of a payment (the redirect alone is never trusted).
    Returns {"status", "amount", "ref_id", "raw"}.
    """
    cfg = conf.esewa()
    query = urllib.parse.urlencode(
        {
            "product_code": cfg["product_code"],
            "total_amount": str(int(amount)),
            "transaction_uuid": reference,
        }
    )

    last_problem = "no answer"
    for base in cfg["status_urls"]:
        try:
            status, body = _request("GET", f"{base}?{query}")
        except GatewayUnavailable as error:
            last_problem = str(error)
            continue
        if status == 200 and isinstance(body, dict) and body.get("status"):
            return {
                "status": str(body["status"]).upper(),
                "amount": body.get("total_amount", body.get("totalAmount")),
                "ref_id": str(body.get("ref_id") or body.get("refId") or ""),
                "raw": body,
            }
        last_problem = f"{base} answered {status}"

    raise GatewayUnavailable(last_problem)