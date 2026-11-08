from django.http import HttpResponse
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from visitors.permissions import IsVisitor

from . import conf, gateways, services
from .invoices import build_payment_invoice
from .models import Payment
from .serializers import StartSerializer, VerifySerializer


class PaymentThrottle(UserRateThrottle):
    """Per visitor. The rate is set here, so no change to settings.py is needed."""

    scope = "payments"
    rate = "120/hour"


def payment_payload(payment, checked=True, message=""):
    return {
        "reference": payment.reference,
        "provider": payment.provider,
        "amount": int(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "note": payment.status_note,
        "isTest": payment.is_test,
        "checked": checked,
        "message": message,
        "invoiceUrl": (
            reverse("payments-invoice", kwargs={"reference": payment.reference})
            if payment.status == Payment.Status.COMPLETED
            else None
        ),
    }


class ConfigView(APIView):
    """GET /api/payments/config/ : what the support page needs to know."""

    permission_classes = [IsVisitor]
    throttle_classes = [PaymentThrottle]

    def get(self, request):
        providers = {}
        for name, getter in (("khalti", conf.khalti), ("esewa", conf.esewa)):
            try:
                getter()
                providers[name] = True
            except conf.NotConfigured:
                providers[name] = False

        return Response(
            {
                "minAmount": conf.min_amount(),
                "maxAmount": conf.max_amount(),
                "currency": conf.currency(),
                "isTest": conf.is_test(),
                "providers": providers,
            }
        )


class StartView(APIView):
    """
    POST /api/payments/start/ {provider: "khalti" | "esewa", amount: whole rupees}

    Khalti: replies {redirectUrl}  -> send the browser there.
    eSewa:  replies {form: {action, fields}} -> the browser POSTs those fields to `action`.
    """

    permission_classes = [IsVisitor]
    throttle_classes = [PaymentThrottle]

    def post(self, request):
        serializer = StartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider = serializer.validated_data["provider"]
        amount = serializer.validated_data["amount"]
        label = Payment.Provider(provider).label

        try:
            result = services.start_payment(request.user, provider, amount)
        except conf.NotConfigured as error:
            return Response({"detail": str(error)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except gateways.GatewayUnavailable:
            return Response(
                {"detail": f"Could not reach {label} right now. Please try again in a moment."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except gateways.GatewayError as error:
            return Response(
                {"detail": f"{label} could not start the payment: {error}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result, status=status.HTTP_201_CREATED)


class VerifyView(APIView):
    """
    POST /api/payments/verify/ {reference, data?}

    Called by the page the visitor lands on after paying (and by "Check again"). It asks the PROVIDER
    what happened and replies with the real status. Only the visitor who started the payment can ask.
    """

    permission_classes = [IsVisitor]
    throttle_classes = [PaymentThrottle]

    def post(self, request):
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payment = Payment.objects.filter(
            reference=serializer.validated_data["reference"], visitor=request.user
        ).first()
        if payment is None:
            raise NotFound("Payment not found.")

        try:
            payment, checked, message = services.verify_payment(
                payment.pk, serializer.validated_data["data"]
            )
        except gateways.GatewayError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(payment_payload(payment, checked, message))


class InvoiceView(APIView):
    """GET /api/payments/<reference>/invoice/ : download the visitor's confirmed payment invoice."""

    permission_classes = [IsVisitor]
    throttle_classes = [PaymentThrottle]

    def get(self, request, reference):
        payment = Payment.objects.filter(reference=reference, visitor=request.user).first()
        if payment is None or payment.status != Payment.Status.COMPLETED:
            raise NotFound("A confirmed payment invoice was not found.")

        response = HttpResponse(build_payment_invoice(payment), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="invoice-{payment.reference}.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response