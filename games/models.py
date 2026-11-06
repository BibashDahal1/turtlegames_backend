from decimal import Decimal

from cloudinary.models import CloudinaryField
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

hex_colour_validator = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message="Enter a hex colour such as #6a1414.",
)


class Game(models.Model):
    """One game shown in the carousel and on /games/<slug>."""

    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Used in the URL: /games/<slug>. Lowercase letters, numbers and hyphens only.",
    )
    name = models.CharField(max_length=150)
    name_native = models.CharField(
        "name (native script)",
        max_length=150,
        blank=True,
        help_text="The name in its own script, e.g. भ्रष्ट नेता.",
    )
    tagline = models.CharField(max_length=255)
    blurb = models.TextField(
        help_text="The description. Separate paragraphs with a blank line."
    )

    players = models.CharField(max_length=20, help_text="e.g. 2–6")
    minutes = models.CharField(max_length=20, help_text="e.g. 15–20")
    age = models.CharField(max_length=20, help_text="e.g. 14+")
    language = models.CharField(max_length=100, help_text="e.g. Nepali / English")
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=(
            "Price of ONE game box. Leave empty if it is not for sale yet "
            "(visitors cannot order it). The currency is set in settings (SHOP_CURRENCY)."
        ),
    )

    color = models.CharField(
        "colour 1", max_length=7, validators=[hex_colour_validator], default="#000000"
    )
    color2 = models.CharField(
        "colour 2", max_length=7, validators=[hex_colour_validator], default="#000000"
    )
    accent = models.CharField(
        "accent colour", max_length=7, validators=[hex_colour_validator], default="#ffffff"
    )

    # The six faces of the box
    box_front = CloudinaryField("box front", folder="games/box")
    box_back = CloudinaryField("box back", folder="games/box")
    box_left = CloudinaryField("box left side", folder="games/box")
    box_right = CloudinaryField("box right side", folder="games/box")
    box_top = CloudinaryField("box top (lid)", folder="games/box")
    box_bottom = CloudinaryField("box bottom", folder="games/box")

    card_back = CloudinaryField(
        "card back",
        folder="games/card-backs",
        blank=True,
        null=True,
        help_text="Blurred and used behind the text on the back of every card.",
    )

    order = models.PositiveIntegerField(
        default=0, help_text="Lower numbers appear first in the carousel."
    )
    is_published = models.BooleanField(
        default=True, help_text="Untick to hide this game from the website."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    @property
    def blurb_paragraphs(self):
        text = self.blurb.replace("\r\n", "\n")
        return [p.strip() for p in text.split("\n\n") if p.strip()]


class GameCard(models.Model):
    """One flippable card of a game."""

    game = models.ForeignKey(Game, related_name="cards", on_delete=models.CASCADE)
    name = models.CharField(max_length=150)
    name_native = models.CharField(
        "name (native script)", max_length=150, blank=True
    )
    image = CloudinaryField(
        "card front",
        folder="games/cards",
        help_text="PNG with transparent rounded corners.",
    )
    description = models.TextField(
        max_length=300,
        help_text="Shown on the back of the card. Keep it short (about 150 characters).",
    )
    quote = models.CharField(
        max_length=255, blank=True, help_text="The line the character says, in its own script."
    )
    quote_en = models.CharField(
        "quote (English)", max_length=255, blank=True, help_text="English meaning of the quote."
    )
    order = models.PositiveIntegerField(
        default=0, help_text="Lower numbers appear first."
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.game.name} - {self.name}"


class GameRule(models.Model):
    """
    One numbered rule of a game, with an optional picture.
    The numbers 1, 2, 3... are NOT typed in: they are assigned automatically
    from the order of the rules.
    """

    game = models.ForeignKey(Game, related_name="rules", on_delete=models.CASCADE)
    order = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Position of the rule. Lower numbers come first. "
            "Rules are numbered 1, 2, 3... automatically in this order."
        ),
    )
    title = models.CharField(
        max_length=120,
        blank=True,
        help_text="Optional short heading for the rule, e.g. Setup.",
    )
    text = models.TextField(
        max_length=1500,
        help_text="The rule. Plain text only. A new line in the box becomes a new line on the site.",
    )
    image = CloudinaryField(
        "rule image",
        folder="games/rules",
        blank=True,
        null=True,
        help_text="Optional picture that shows this rule. Leave empty if the text is enough.",
    )
    image_caption = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional caption under the picture (also used as its alt text).",
    )

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        preview = self.title or self.text[:40]
        return f"{self.game.name} - rule: {preview}"