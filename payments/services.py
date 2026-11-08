from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from . import conf, gateways
from .models import Payment

PURCHASE_NAME = "Support Turtle Games"
# How long eSewa may answer "not found" before we treat a payment as never completed.
ESEWA_NOT_FOUND_GRACE = timedelta(minutes=30)


def _amount_of(value):
    """Reads a rupee amount the provider sent (may be text like '1,000.0'). None if unreadable."""
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _set(payment, status, note="", **fields):
    payment.status = status
    payment.status_note = note[:200]
    payment.last_checked_at = timezone.now()
    for name, value in fields.items():
        setattr(payment, name, value)
    if status == Payment.Status.COMPLETED and payment.completed_at is None:
        payment.completed_at = timezone.now()
    payment.save()


# ------------------------------------------------------------------------------------------
# Starting a payment
# ------------------------------------------------------------------------------------------


def start_payment(visitor, provider, amount):
    """
    Creates the payment record and asks the provider to start it. `amount` is a whole number of rupees.
    Returns what the browser needs to take the visitor to the provider.
    Raises conf.NotConfigured, gateways.GatewayError or gateways.GatewayUnavailable if it cannot start.
    """
    payment = Payment.objects.create(
        visitor=visitor,
        provider=provider,
        amount=amount,
        currency=conf.currency(),
        is_test=conf.is_test(),
        payer_name=visitor.full_name,
        payer_email=visitor.email,
        payer_phone=visitor.phone,
    )
    # One page on the website handles the return from both providers. eSewa adds "?data=..." to the
    # success address, so no query string is put in these addresses.
    return_url = f"{conf.frontend_url()}/support/return/{provider}/{payment.reference}"

    try:
        if provider == Payment.Provider.KHALTI:
            pidx, payment_url = gateways.khalti_initiate(
                reference=payment.reference,
                paisa=int(amount) * 100,
                name=PURCHASE_NAME,
                return_url=return_url,
                website_url=conf.frontend_url(),
            )
            payment.provider_ref = pidx
            payment.save(update_fields=["provider_ref", "updated_at"])
            return {
                "provider": provider,
                "reference": payment.reference,
                "redirectUrl": payment_url,
            }

        action, fields = gateways.esewa_form(
            reference=payment.reference,
            amount=amount,
            success_url=return_url,
            failure_url=return_url,
        )
        return {
            "provider": provider,
            "reference": payment.reference,
            "form": {"action": action, "fields": fields},
        }
    except (conf.NotConfigured, gateways.GatewayError, gateways.GatewayUnavailable) as error:
        _set(payment, Payment.Status.FAILED, f"Could not start: {error}")
        raise


# ------------------------------------------------------------------------------------------
# Checking a payment with the provider
# ------------------------------------------------------------------------------------------


def _check_khalti(payment):
    if not payment.provider_ref:
        _set(payment, Payment.Status.FAILED, "The payment was never started with Khalti.")
        return

    result = gateways.khalti_lookup(payment.provider_ref)
    status = result["status"]
    payment.raw_response = result["raw"]
    expected_paisa = int(Decimal(payment.amount)) * 100

    if status == "Completed":
        if result["amount"] != expected_paisa:
            _set(
                payment,
                Payment.Status.PENDING,
                "Khalti reports a different amount than expected. Check it by hand.",
            )
        else:
            _set(
                payment,
                Payment.Status.COMPLETED,
                "Confirmed by Khalti.",
                provider_txn=result["transaction_id"],
            )
    elif status == "Initiated":
        _set(payment, Payment.Status.INITIATED, "Khalti is waiting for the payment.")
    elif status == "Pending":
        _set(payment, Payment.Status.PENDING, "Khalti is still processing the payment.")
    elif status in ("Expired", "User canceled"):
        _set(payment, Payment.Status.FAILED, f"Khalti: {status.lower()}.")
    elif status in ("Refunded", "Partially Refunded"):
        _set(payment, Payment.Status.FAILED, f"Khalti: {status.lower()}.")
    else:
        # Khalti's docs: for any other status, hold the transaction and contact Khalti.
        _set(payment, Payment.Status.PENDING, f"Unexpected Khalti status: {status}.")


def _check_esewa(payment, redirect_data):
    cfg = conf.esewa()

    if redirect_data:
        decoded = gateways.esewa_decode(redirect_data)  # raises VerificationError if tampered
        paid = _amount_of(decoded.get("total_amount"))
        if (
            decoded.get("transaction_uuid") != payment.reference
            or decoded.get("product_code") != cfg["product_code"]
            or paid is None
            or paid != Decimal(payment.amount)
        ):
            raise gateways.VerificationError("The payment response does not match this payment.")
        payment.provider_ref = str(decoded.get("transaction_code") or "")[:100]

    # The redirect is only a hint (the visitor's browser carries it). eSewa's own answer decides.
    result = gateways.esewa_status(payment.reference, payment.amount)
    status = result["status"]
    payment.raw_response = result["raw"]

    if status == "COMPLETE":
        reported = _amount_of(result["amount"]) if result["amount"] is not None else None
        if reported is not None and reported != Decimal(payment.amount):
            _set(
                payment,
                Payment.Status.PENDING,
                "eSewa reports a different amount than expected. Check it by hand.",
            )
        else:
            _set(
                payment,
                Payment.Status.COMPLETED,
                "Confirmed by eSewa.",
                provider_txn=result["ref_id"],
            )
    elif status in ("PENDING", "AMBIGUOUS"):
        _set(payment, Payment.Status.PENDING, f"eSewa status: {status.lower()}.")
    elif status in ("FULL_REFUND", "PARTIAL_REFUND", "CANCELED"):
        _set(payment, Payment.Status.FAILED, f"eSewa status: {status.lower().replace('_', ' ')}.")
    elif status == "NOT_FOUND":
        if timezone.now() - payment.created_at < ESEWA_NOT_FOUND_GRACE:
            _set(payment, Payment.Status.INITIATED, "eSewa has no completed payment yet.")
        else:
            _set(payment, Payment.Status.FAILED, "The payment was not completed at eSewa.")
    else:
        _set(payment, Payment.Status.PENDING, f"Unexpected eSewa status: {status}.")


def verify_payment(payment_id, esewa_data=""):
    """
    Asks the provider what really happened and updates the payment. Safe to call again and again:
    a payment that is already confirmed is never changed or re-sent.
    Returns (payment, checked, message). `checked` is False when the provider could not be reached
    (the payment is left as it was). Raises gateways.GatewayError if a response failed its security check.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment_id)
        if payment.status == Payment.Status.COMPLETED:
            return payment, True, ""

        try:
            if payment.provider == Payment.Provider.KHALTI:
                _check_khalti(payment)
            else:
                _check_esewa(payment, esewa_data)
        except (gateways.GatewayUnavailable, conf.NotConfigured):
            payment.last_checked_at = timezone.now()
            payment.save(update_fields=["last_checked_at", "updated_at"])
            return (
                payment,
                False,
                f"Could not reach {payment.get_provider_display()} right now. Please check again in a moment.",
            )

    return payment, True, ""