import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import Visitor


def _safe(value):
    """Stops spreadsheet formula injection from text a visitor typed (=, +, -, @)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "email",
        "age",
        "country",
        "city",
        "is_active",
        "created_at",
        "last_seen_at",
    )
    list_filter = ("is_active", "country")
    search_fields = (
        "first_name",
        "middle_name",
        "last_name",
        "email",
        "phone",
        "country",
        "city",
    )
    date_hierarchy = "created_at"
    actions = ["export_csv"]

    def has_add_permission(self, request):
        return False  # visitors register themselves on the site

    def get_readonly_fields(self, request, obj=None):
        # Collected data stays exactly as the visitor entered it. Only "is active" can be changed.
        return [f.name for f in self.model._meta.fields if f.name != "is_active"]

    @admin.action(description="Export selected visitors to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="visitors.csv"'
        response.write("\ufeff")  # byte-order mark so Excel shows Nepali names correctly

        writer = csv.writer(response)
        writer.writerow(
            [
                "First name",
                "Middle name",
                "Last name",
                "Age",
                "Email",
                "Phone",
                "Country",
                "City",
                "Consent given at",
                "Registered at",
                "Last seen at",
                "Active",
            ]
        )
        for v in queryset:
            writer.writerow(
                [
                    _safe(v.first_name),
                    _safe(v.middle_name),
                    _safe(v.last_name),
                    v.age,
                    _safe(v.email),
                    _safe(v.phone),
                    _safe(v.country),
                    _safe(v.city),
                    v.consent_given_at.isoformat() if v.consent_given_at else "",
                    v.created_at.isoformat(),
                    v.last_seen_at.isoformat() if v.last_seen_at else "",
                    "yes" if v.is_active else "no",
                ]
            )
        return response