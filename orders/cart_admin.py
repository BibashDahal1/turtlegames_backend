from decimal import Decimal

from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .models import Cart, CartItem


def money(amount):
    return f"{amount:,.2f} {getattr(settings, 'SHOP_CURRENCY', 'NPR')}"


class HasItemsFilter(admin.SimpleListFilter):
    title = "games in cart"
    parameter_name = "has_items"

    def lookups(self, request, model_admin):
        return [("yes", "Has games"), ("no", "Empty")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(items__isnull=False).distinct()
        if self.value() == "no":
            return queryset.filter(items__isnull=True)
        return queryset


class HasDetailsFilter(admin.SimpleListFilter):
    title = "contact details"
    parameter_name = "has_details"

    def lookups(self, request, model_admin):
        return [("yes", "Given (ready to contact)"), ("no", "Not given yet")]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(details_updated_at__isnull=False)
        if self.value() == "no":
            return queryset.filter(details_updated_at__isnull=True)
        return queryset


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    can_delete = False
    fields = ("game", "quantity", "unit_price", "line_total")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Price each")
    def unit_price(self, item):
        price = item.game.price
        return money(price) if price is not None else "no price"

    @admin.display(description="Line total")
    def line_total(self, item):
        price = item.game.price
        return money(price * item.quantity) if price is not None else "-"


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    """
    Every visitor's cart. Open the ones that have games AND contact details, contact the visitor by
    phone or email, agree payment and delivery offline, then set the status here.
    Prices shown are the games' CURRENT prices.
    """

    list_display = (
        "id",
        "who",
        "contact",
        "games",
        "total",
        "status",
        "details_updated_at",
        "updated_at",
    )
    list_filter = ("status", HasDetailsFilter, HasItemsFilter)
    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "city",
        "address",
        "visitor__email",
    )
    ordering = ("-updated_at",)
    list_select_related = ("visitor",)
    inlines = [CartItemInline]

    readonly_fields = ("visitor", "contact_links", "cart_total", "details_updated_at", "updated_at")
    fieldsets = (
        ("Visitor", {"fields": ("visitor", "contact_links", "cart_total")}),
        (
            "Details the visitor gave",
            {
                "fields": (
                    "first_name",
                    "middle_name",
                    "last_name",
                    "email",
                    "phone",
                    "country",
                    "city",
                    "address",
                    "landmark",
                    "note",
                    "details_updated_at",
                )
            },
        ),
        ("Your follow-up (the visitor never sees this)", {"fields": ("status", "internal_note")}),
        ("Last change", {"fields": ("updated_at",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("items__game")

    def has_add_permission(self, request):
        return False

    # ---- columns ----

    @admin.display(description="Who")
    def who(self, cart):
        return cart.full_name or str(cart.visitor.email)

    @admin.display(description="Contact")
    def contact(self, cart):
        return self._links(cart)

    @admin.display(description="Contact")
    def contact_links(self, cart):
        return self._links(cart)

    @staticmethod
    def _links(cart):
        parts = []
        if cart.phone:
            parts.append(format_html('<a href="tel:{}">{}</a>', cart.phone, cart.phone))
        if cart.email:
            parts.append(format_html('<a href="mailto:{}">{}</a>', cart.email, cart.email))
        if not parts:
            return "no details yet"
        return format_html_join(mark_safe("<br>"), "{}", ((part,) for part in parts))

    @admin.display(description="Games")
    def games(self, cart):
        items = list(cart.items.all())
        if not items:
            return "empty"
        return ", ".join(f"{item.game.name} x{item.quantity}" for item in items)

    @admin.display(description="Total")
    def total(self, cart):
        return self._total(cart)

    @admin.display(description="Cart total (current prices)")
    def cart_total(self, cart):
        return self._total(cart)

    @staticmethod
    def _total(cart):
        items = list(cart.items.all())
        priced = [i for i in items if i.game.price is not None]
        if not items:
            return "-"
        total = sum((Decimal(i.game.price) * i.quantity for i in priced), Decimal("0"))
        note = "" if len(priced) == len(items) else " (some games have no price)"
        return money(total) + note