import secrets

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

REFERENCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid mix-ups


def _new_reference():
    stamp = timezone.localdate().strftime("%y%m%d")
    suffix = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(4))
    return f"TG-{stamp}-{suffix}"


class Order(models.Model):
    """
    An order request from a visitor. There is no online payment: the creator contacts the buyer
    (phone or email) to arrange payment and delivery, then updates the status here.
    Prices and contact details are copied into the order, so later changes to a game or a
    visitor never alter an existing order.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        CONFIRMED = "confirmed", "Confirmed"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    reference = models.CharField(max_length=20, unique=True, editable=False)
    visitor = models.ForeignKey(
        "visitors.Visitor",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )

    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50)
    email = models.EmailField()
    phone = models.CharField(max_length=20)

    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80)
    address = models.CharField(max_length=250, help_text="Street, area, ward, house number.")
    landmark = models.CharField(max_length=150, blank=True)

    note = models.TextField(max_length=500, blank=True, help_text="Note written by the buyer.")
    internal_note = models.TextField(
        blank=True, help_text="Your own notes. Never shown to the buyer."
    )

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NPR")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.full_name}"

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        if not self.reference:
            for _ in range(20):
                candidate = _new_reference()
                if not Order.objects.filter(reference=candidate).exists():
                    self.reference = candidate
                    break
            else:
                raise RuntimeError("Could not generate a unique order reference.")
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    """One game in an order, with the name and price as they were when the order was placed."""

    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    game = models.ForeignKey(
        "games.Game",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="order_items",
    )
    game_name = models.CharField(max_length=150)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.game_name} x{self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity