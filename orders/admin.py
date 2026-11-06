import csv

from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone

from .models import Order, OrderItem


def _safe(value):
    """Stops spreadsheet formula injection from text a buyer typed (=, +, -, @)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _status_action(status_value, label):
    @admin.action(description=f"Mark selected orders as {label}")
    def action(modeladmin, request, queryset):
        updated = queryset.update(status=status_value, updated_at=timezone.now())
        modeladmin.message_user(request, f"{updated} order(s) marked as {label}.")

    action.__name__ = f"mark_{status_value}"
    return action


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("game_name", "unit_price", "quantity", "line_total")
    readonly_fields = ("game_name", "unit_price", "quantity", "line_total")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "full_name",
        "phone",
        "email",
        "city",
        "total_display",
        "status",
        "created_at",
    )
    list_filter = ("status", "country", "created_at")
    search_fields = (
        "reference",
        "first_name",
        "middle_name",
        "last_name",
        "email",
        "phone",
        "city",
    )
    date_hierarchy = "created_at"
    inlines = [OrderItemInline]
    fieldsets = (
        ("Order", {"fields": ("reference", "status", "total", "currency", "created_at", "updated_at")}),
        ("Buyer", {"fields": ("visitor", "first_name", "middle_name", "last_name", "email", "phone")}),
        ("Delivery", {"fields": ("country", "city", "address", "landmark")}),
        ("Notes", {"fields": ("note", "internal_note")}),
    )
    actions = [
        _status_action(Order.Status.CONFIRMED, "confirmed"),
        _status_action(Order.Status.SHIPPED, "shipped"),
        _status_action(Order.Status.DELIVERED, "delivered"),
        _status_action(Order.Status.CANCELLED, "cancelled"),
        "export_csv",
    ]

    def has_add_permission(self, request):
        return False  # orders come from the website

    def get_readonly_fields(self, request, obj=None):
        # What the buyer entered stays exactly as entered. Only the status and your own note change.
        editable = {"status", "internal_note"}
        return [f.name for f in self.model._meta.fields if f.name not in editable]

    @admin.display(description="Total", ordering="total")
    def total_display(self, obj):
        return f"{obj.currency} {obj.total:,.2f}"

    @admin.action(description="Export selected orders to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="orders.csv"'
        response.write("\ufeff")  # byte-order mark so Excel shows Nepali text correctly

        writer = csv.writer(response)
        writer.writerow(
            [
                "Reference",
                "Status",
                "Ordered at",
                "Name",
                "Email",
                "Phone",
                "Country",
                "City",
                "Address",
                "Landmark",
                "Buyer note",
                "Items",
                "Total",
                "Currency",
            ]
        )
        for order in queryset.prefetch_related("items"):
            items = "; ".join(f"{i.game_name} x{i.quantity}" for i in order.items.all())
            writer.writerow(
                [
                    order.reference,
                    order.get_status_display(),
                    order.created_at.isoformat(),
                    _safe(order.full_name),
                    _safe(order.email),
                    _safe(order.phone),
                    _safe(order.country),
                    _safe(order.city),
                    _safe(order.address),
                    _safe(order.landmark),
                    _safe(order.note),
                    _safe(items),
                    order.total,
                    order.currency,
                ]
            )
        return response