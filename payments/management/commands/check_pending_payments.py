from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from payments import services
from payments.gateways import GatewayError
from payments.models import Payment


class Command(BaseCommand):
    help = (
        "Asks Khalti / eSewa about payments that were started but never confirmed, for example "
        "because the visitor closed the page. Safe to run often (for example every 15 minutes)."
    )

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=3)
        waiting = Payment.objects.filter(
            status__in=[Payment.Status.INITIATED, Payment.Status.PENDING],
            created_at__gte=since,
        ).exclude(provider_ref="", provider=Payment.Provider.KHALTI)

        done = 0
        for payment in waiting:
            try:
                updated, checked, _ = services.verify_payment(payment.pk)
            except GatewayError as error:
                self.stderr.write(f"{payment.reference}: {error}")
                continue
            if checked:
                done += 1
                self.stdout.write(f"{updated.reference}: {updated.status}")
        self.stdout.write(self.style.SUCCESS(f"Checked {done} payment(s)."))