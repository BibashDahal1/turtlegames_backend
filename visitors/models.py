import hashlib
import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Visitor(models.Model):
    """A person who registered to enter the site. Not related to Django's admin users."""

    first_name = models.CharField(max_length=50)
    middle_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50)
    age = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        help_text="Age at the time of registration.",
    )
    email = models.EmailField(unique=True, help_text="Stored in lowercase. Not verified.")
    phone = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=80)
    city = models.CharField(max_length=80, blank=True)

    consent_given_at = models.DateTimeField(
        help_text="When the visitor agreed to the data collection."
    )
    is_active = models.BooleanField(
        default=True, help_text="Untick to block this visitor from the site."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    # Lets Django REST Framework treat a Visitor as an authenticated "user".
    is_authenticated = True
    is_anonymous = False

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)


class VisitorToken(models.Model):
    """
    A long-lived sign-in token for one browser/device of a visitor.
    Only a SHA-256 hash is stored, so a database leak does not expose usable tokens.
    A visitor can have several (phone, laptop...). Tokens never expire on their own;
    delete them, or untick "is active" on the visitor, to cut access.
    """

    MAX_PER_VISITOR = 10

    visitor = models.ForeignKey(Visitor, related_name="tokens", on_delete=models.CASCADE)
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, visitor: Visitor) -> str:
        """Create a token and return the raw value. It is shown once and never stored."""
        raw_key = secrets.token_urlsafe(32)
        cls.objects.create(visitor=visitor, key_hash=cls.hash_key(raw_key))

        # Keep only the newest few tokens per visitor.
        old_ids = list(
            visitor.tokens.order_by("-created_at", "-id").values_list("id", flat=True)[
                cls.MAX_PER_VISITOR :
            ]
        )
        if old_ids:
            visitor.tokens.filter(id__in=old_ids).delete()

        return raw_key

    def __str__(self):
        return f"Token for visitor {self.visitor_id}"