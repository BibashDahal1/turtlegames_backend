import secrets

from django.db import models
from django.utils import timezone

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid mix-ups


def _new_reference():
    # Letters, digits and hyphens only: eSewa's transaction_uuid allows nothing else.
    stamp = timezone.localdate().strftime("%y%m%d")
    suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(6))
    return f"SUP-{stamp}-{suffix}"


class Payment(models.Model):
    """
    One attempt to support the organisation and creator with a payment of the visitor's chosen amount.
    The status here only ever changes after the PROVIDER's own server has confirmed it
    (Khalti lookup / eSewa status check), never because a browser said so.
    """

    class Provider(models.TextChoices):
        KHALTI = "khalti", "Khalti"
        ESEWA = "esewa", "eSewa"

    class Status(models.TextChoices):
        INITIATED = "initiated", "Started, not paid yet"
        PENDING = "pending", "Waiting for the provider"
        COMPLETED = "completed", "Paid"
        FAILED = "failed", "Not paid"

    reference = models.CharField(max_length=40, unique=True, editable=False)
    visitor = models.ForeignKey(
        "visitors.Visitor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payments",
    )
    provider = models.CharField(max_length=10, choices=Provider.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Whole rupees.")
    currency = models.CharField(max_length=3, default="NPR")
    is_test = models.BooleanField(
        default=True, help_text="True when made in test mode: no real money moved."
    )

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.INITIATED)
    status_note = models.CharField(max_length=200, blank=True, default="")
    provider_ref = models.CharField(
        max_length=100, blank=True, default="", help_text="Khalti pidx / eSewa transaction code."
    )
    provider_txn = models.CharField(
        max_length=100, blank=True, default="", help_text="Provider's transaction id."
    )
    raw_response = models.JSONField(default=dict, blank=True, help_text="Last answer from the provider.")

    # Copied from the visitor when the payment started, so the record stays readable on its own.
    payer_name = models.CharField(max_length=150, blank=True, default="")
    payer_email = models.EmailField(blank=True, default="")
    payer_phone = models.CharField(max_length=20, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.get_provider_display()} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.reference:
            for _ in range(20):
                candidate = _new_reference()
                if not Payment.objects.filter(reference=candidate).exists():
                    self.reference = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique payment reference.")
        super().save(*args, **kwargs)