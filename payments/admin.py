from django.contrib import admin, messages

from . import services
from .gateways import GatewayError
from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """
    Every support payment. Records are read-only: they change only when the provider confirms something.
    Payments with "Test" ticked were made in test mode and moved no real money.
    """

    list_display = (
        "reference",
        "who",
        "provider",
        "amount",
        "status",
        "is_test",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "provider", "is_test")
    search_fields = (
        "reference",
        "payer_name",
        "payer_email",
        "payer_phone",
        "provider_ref",
        "provider_txn",
    )
    ordering = ("-created_at",)
    list_select_related = ("visitor",)
    readonly_fields = (
        "reference",
        "visitor",
        "provider",
        "amount",
        "currency",
        "is_test",
        "status",
        "status_note",
        "provider_ref",
        "provider_txn",
        "raw_response",
        "payer_name",
        "payer_email",
        "payer_phone",
        "created_at",
        "updated_at",
        "last_checked_at",
        "completed_at",
    )
    actions = ["recheck"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Who")
    def who(self, payment):
        return payment.payer_name or payment.payer_email or "-"

    @admin.action(description="Re-check selected payments with Khalti / eSewa")
    def recheck(self, request, queryset):
        checked = 0
        for payment in queryset.exclude(status=Payment.Status.COMPLETED):
            try:
                _, ok, message = services.verify_payment(payment.pk)
            except GatewayError as error:
                self.message_user(request, f"{payment.reference}: {error}", messages.ERROR)
                continue
            if ok:
                checked += 1
            else:
                self.message_user(request, f"{payment.reference}: {message}", messages.WARNING)
        self.message_user(request, f"Re-checked {checked} payment(s).", messages.SUCCESS)