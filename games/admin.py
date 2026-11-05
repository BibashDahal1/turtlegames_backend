from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from .models import Game, GameCard


def thumb(resource, height=120):
    """Small preview image for the admin, served resized by Cloudinary."""
    if not resource or not hasattr(resource, "build_url"):
        return "—"
    url = resource.build_url(height=height * 2, crop="limit")
    return format_html(
        '<img src="{}" style="height:{}px;border-radius:6px;background:#eee;">',
        url,
        height,
    )


class GameCardInline(admin.StackedInline):
    model = GameCard
    extra = 0
    fields = (
        ("order", "name", "name_native"),
        ("image", "image_preview"),
        "description",
        ("quote", "quote_en"),
    )
    readonly_fields = ("image_preview",)

    @admin.display(description="Preview")
    def image_preview(self, obj):
        return thumb(obj.image) if obj and obj.pk else "—"


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "order",
        "is_published",
        "card_count",
        "front_preview",
    )
    list_editable = ("order", "is_published")
    list_filter = ("is_published",)
    search_fields = ("name", "name_native", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [GameCardInline]

    fieldsets = (
        ("Basics", {"fields": ("slug", "name", "name_native", "tagline", "blurb")}),
        ("Details", {"fields": (("players", "minutes", "age"), "language")}),
        ("Colours", {"fields": (("color", "color2", "accent"),)}),
        (
            "Box images (all six faces)",
            {
                "fields": (
                    ("box_front", "box_front_preview"),
                    ("box_back", "box_back_preview"),
                    ("box_left", "box_left_preview"),
                    ("box_right", "box_right_preview"),
                    ("box_top", "box_top_preview"),
                    ("box_bottom", "box_bottom_preview"),
                )
            },
        ),
        ("Card back", {"fields": (("card_back", "card_back_preview"),)}),
        ("Publishing", {"fields": ("order", "is_published")}),
    )
    readonly_fields = (
        "box_front_preview",
        "box_back_preview",
        "box_left_preview",
        "box_right_preview",
        "box_top_preview",
        "box_bottom_preview",
        "card_back_preview",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_card_count=Count("cards"))

    @admin.display(description="Cards", ordering="_card_count")
    def card_count(self, obj):
        return obj._card_count

    @admin.display(description="Box front")
    def front_preview(self, obj):
        return thumb(obj.box_front, height=60)

    def _preview(self, obj, field):
        return thumb(getattr(obj, field)) if obj and obj.pk else "—"

    @admin.display(description="Preview")
    def box_front_preview(self, obj):
        return self._preview(obj, "box_front")

    @admin.display(description="Preview")
    def box_back_preview(self, obj):
        return self._preview(obj, "box_back")

    @admin.display(description="Preview")
    def box_left_preview(self, obj):
        return self._preview(obj, "box_left")

    @admin.display(description="Preview")
    def box_right_preview(self, obj):
        return self._preview(obj, "box_right")

    @admin.display(description="Preview")
    def box_top_preview(self, obj):
        return self._preview(obj, "box_top")

    @admin.display(description="Preview")
    def box_bottom_preview(self, obj):
        return self._preview(obj, "box_bottom")

    @admin.display(description="Preview")
    def card_back_preview(self, obj):
        return self._preview(obj, "card_back")