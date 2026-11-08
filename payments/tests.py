import base64
import json
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from visitors.models import Visitor

from . import conf, gateways
from .models import Payment


def make_visitor(email="sita@example.com"):
    return Visitor.objects.create(
        first_name="Sita", last_name="Rai", age=30, email=email, phone="+977 9800000000",
        country="Nepal", consent_given_at=timezone.now(),
    )


def esewa_redirect(reference, amount, *, status="COMPLETE", secret=None, tamper=False):
    """What eSewa puts in ?data= after a payment, signed the way eSewa signs it."""
    secret = secret or conf.TEST_ESEWA_SECRET_KEY
    body = {
        "transaction_code": "000AWEO",
        "status": status,
        "total_amount": f"{amount}.0",
        "transaction_uuid": reference,
        "product_code": "EPAYTEST",
        "signed_field_names": "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names",
    }
    message = ",".join(f"{n}={body[n]}" for n in body["signed_field_names"].split(","))
    body["signature"] = gateways.esewa_sign(secret, message)
    if tamper:
        body["total_amount"] = "1.0"
    return base64.b64encode(json.dumps(body).encode()).decode()


@override_settings(
    PAYMENT_MODE="test",
    KHALTI_SECRET_KEY="test_key",
    FRONTEND_URL="http://localhost:3000",
    PAYMENT_RETURN_URL="",
    ESEWA_SUCCESS_URL="",
    ESEWA_FAILURE_URL="",
)
class PaymentTests(TestCase):
    def setUp(self):
        self.visitor = make_visitor()
        self.client = APIClient()
        self.client.force_authenticate(user=self.visitor)

    # ---- eSewa signature ----
    def test_signature_is_standard_hmac_sha256_base64(self):
        # RFC 4231 test case 2 for HMAC-SHA256. eSewa's docs ask for HMAC-SHA256 with a base64 result.
        # (The example values printed on eSewa's page do not reproduce with the published test key,
        # so the real check is a sandbox payment; this proves the signing primitive itself is right.)
        signature = gateways.esewa_sign("Jefe", "what do you want for nothing?".replace("you", "ya"))
        expected_hex = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
        self.assertEqual(base64.b64decode(signature).hex(), expected_hex)

    def test_signed_fields_are_joined_in_the_documented_order(self):
        _, fields = gateways.esewa_form(
            reference="SUP-1", amount=100, success_url="http://x/s", failure_url="http://x/f"
        )
        expected = gateways.esewa_sign(
            conf.TEST_ESEWA_SECRET_KEY, "total_amount=100,transaction_uuid=SUP-1,product_code=EPAYTEST"
        )
        self.assertEqual(fields["signature"], expected)

    # ---- config ----
    def test_config_reports_test_mode_and_providers(self):
        data = self.client.get("/api/payments/config/").json()
        self.assertTrue(data["isTest"])
        self.assertEqual(data["providers"], {"khalti": True, "esewa": True})
        self.assertEqual((data["minAmount"], data["maxAmount"]), (10, 100000))

    @override_settings(KHALTI_SECRET_KEY=None)
    def test_khalti_config_reads_key_from_environment_config(self):
        with mock.patch("payments.conf.env_config", return_value="test_key") as env_config:
            self.assertEqual(conf.khalti()["secret_key"], "test_key")
        env_config.assert_any_call("KHALTI_SECRET_KEY", default="")

    def test_payment_return_urls_use_configurable_templates(self):
        with override_settings(
            PAYMENT_RETURN_URL="https://frontend.example/return/{provider}/{reference}",
            ESEWA_SUCCESS_URL="https://frontend.example/success/{reference}",
            ESEWA_FAILURE_URL="https://frontend.example/failure/{reference}",
        ):
            self.assertEqual(
                conf.payment_return_url("khalti", "SUP-1"),
                "https://frontend.example/return/khalti/SUP-1",
            )
            self.assertEqual(
                conf.esewa_success_url("SUP-1"),
                "https://frontend.example/success/SUP-1",
            )
            self.assertEqual(
                conf.esewa_failure_url("SUP-1"),
                "https://frontend.example/failure/SUP-1",
            )

    def test_invalid_payment_return_url_template_is_reported(self):
        with override_settings(PAYMENT_RETURN_URL="https://frontend.example/{missing}"):
            with self.assertRaises(conf.ImproperlyConfigured):
                conf.payment_return_url("khalti", "SUP-1")

    @override_settings(PAYMENT_MODE="live", KHALTI_SECRET_KEY="", ESEWA_PRODUCT_CODE="", ESEWA_SECRET_KEY="")
    def test_live_mode_never_falls_back_to_test_keys(self):
        data = self.client.get("/api/payments/config/").json()
        self.assertFalse(data["isTest"])
        self.assertEqual(data["providers"], {"khalti": False, "esewa": False})
        response = self.client.post("/api/payments/start/", {"provider": "esewa", "amount": 100}, format="json")
        self.assertEqual(response.status_code, 503)

    def test_login_is_required(self):
        response = APIClient().post("/api/payments/start/", {"provider": "khalti", "amount": 100}, format="json")
        self.assertIn(response.status_code, (401, 403))

    # ---- starting ----
    def test_amount_limits(self):
        for bad in (9, 100001, 0, -5):
            response = self.client.post("/api/payments/start/", {"provider": "khalti", "amount": bad}, format="json")
            self.assertEqual(response.status_code, 400, bad)
            self.assertIn("amount", response.json())
        response = self.client.post("/api/payments/start/", {"provider": "khalti", "amount": "12.5"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_start_khalti_sends_paisa_and_returns_redirect(self):
        captured = {}

        def fake_request(method, url, headers=None, payload=None, timeout=20):
            captured.update(method=method, url=url, headers=headers, payload=payload)
            return 200, {"pidx": "PIDX123", "payment_url": "https://test-pay.khalti.com/?pidx=PIDX123"}

        with mock.patch.object(gateways, "_request", fake_request):
            response = self.client.post("/api/payments/start/", {"provider": "khalti", "amount": 250}, format="json")

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["redirectUrl"], "https://test-pay.khalti.com/?pidx=PIDX123")
        payment = Payment.objects.get(reference=body["reference"])
        self.assertEqual((payment.status, payment.provider_ref, payment.is_test), ("initiated", "PIDX123", True))
        self.assertEqual(payment.visitor, self.visitor)
        self.assertEqual(captured["url"], "https://dev.khalti.com/api/v2/epayment/initiate/")
        self.assertEqual(captured["headers"], {"Authorization": "Key test_key"})
        self.assertEqual(captured["payload"]["amount"], 25000)  # Rs 250 = 25000 paisa
        self.assertEqual(captured["payload"]["purchase_order_id"], payment.reference)
        self.assertEqual(
            captured["payload"]["return_url"],
            f"http://localhost:3000/support/return/khalti/{payment.reference}",
        )

    def test_start_khalti_provider_error_is_reported_and_recorded(self):
        with mock.patch.object(gateways, "_request", lambda *a, **k: (400, {"amount": ["Amount should be greater than Rs. 10"], "error_key": "validation_error"})):
            response = self.client.post("/api/payments/start/", {"provider": "khalti", "amount": 100}, format="json")
        self.assertEqual(response.status_code, 502)
        self.assertIn("Amount should be greater", response.json()["detail"])
        self.assertEqual(Payment.objects.get().status, "failed")

    def test_start_esewa_returns_signed_form(self):
        response = self.client.post("/api/payments/start/", {"provider": "esewa", "amount": 500}, format="json")
        self.assertEqual(response.status_code, 201)
        form = response.json()["form"]
        fields = form["fields"]
        self.assertEqual(form["action"], "https://rc-epay.esewa.com.np/api/epay/main/v2/form")
        reference = response.json()["reference"]
        self.assertEqual(
            (fields["total_amount"], fields["amount"], fields["transaction_uuid"], fields["product_code"]),
            ("500", "500", reference, "EPAYTEST"),
        )
        expected = gateways.esewa_sign(
            conf.TEST_ESEWA_SECRET_KEY, f"total_amount=500,transaction_uuid={reference},product_code=EPAYTEST"
        )
        self.assertEqual(fields["signature"], expected)
        self.assertEqual(fields["signed_field_names"], "total_amount,transaction_uuid,product_code")
        self.assertEqual(fields["success_url"], f"http://localhost:3000/support/return/esewa/{reference}")
        self.assertEqual(fields["failure_url"], f"http://localhost:3000/support/return/esewa/{reference}")
        self.assertNotIn("?", fields["success_url"])
        self.assertRegex(reference, r"^[A-Za-z0-9-]+$")  # eSewa: letters, digits, hyphen only

    # ---- verifying: Khalti ----
    def khalti_payment(self, amount=250):
        return Payment.objects.create(
            visitor=self.visitor, provider="khalti", amount=amount, provider_ref="PIDX123", is_test=True
        )

    def verify(self, reference, data=""):
        return self.client.post("/api/payments/verify/", {"reference": reference, "data": data}, format="json")

    def test_khalti_completed_is_confirmed_by_lookup_and_not_checked_twice(self):
        payment = self.khalti_payment(250)
        lookup = {"pidx": "PIDX123", "total_amount": 25000, "status": "Completed", "transaction_id": "TX9", "fee": 0, "refunded": False}
        with mock.patch.object(gateways, "_request", return_value=(200, lookup)) as call:
            body = self.verify(payment.reference).json()
            self.assertEqual((body["status"], body["checked"], body["amount"], body["isTest"]), ("completed", True, 250, True))
            self.assertEqual(body["invoiceUrl"], f"/api/payments/{payment.reference}/invoice/")
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args[0][1], "https://dev.khalti.com/api/v2/epayment/lookup/")
            self.assertEqual(call.call_args[0][3], {"pidx": "PIDX123"})
            self.verify(payment.reference)
            self.assertEqual(call.call_count, 1)  # already paid: the provider is not asked again
        payment.refresh_from_db()
        self.assertEqual((payment.status, payment.provider_txn), ("completed", "TX9"))
        self.assertIsNotNone(payment.completed_at)

    def test_khalti_amount_mismatch_is_not_marked_paid(self):
        payment = self.khalti_payment(250)
        lookup = {"pidx": "PIDX123", "total_amount": 1000, "status": "Completed", "transaction_id": "TX9"}
        with mock.patch.object(gateways, "_request", return_value=(200, lookup)):
            body = self.verify(payment.reference).json()
        self.assertEqual(body["status"], "pending")

    def test_khalti_other_statuses(self):
        cases = {"Pending": "pending", "Initiated": "initiated", "Expired": "failed", "User canceled": "failed", "Refunded": "failed", "Something new": "pending"}
        for khalti_status, expected in cases.items():
            payment = self.khalti_payment()
            http = 400 if khalti_status in ("Expired", "User canceled") else 200
            with mock.patch.object(gateways, "_request", return_value=(http, {"pidx": "PIDX123", "total_amount": 25000, "status": khalti_status})):
                self.assertEqual(self.verify(payment.reference).json()["status"], expected, khalti_status)

    def test_provider_unreachable_leaves_payment_alone(self):
        payment = self.khalti_payment()
        with mock.patch.object(gateways, "_request", side_effect=gateways.GatewayUnavailable("timeout")):
            response = self.verify(payment.reference)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["checked"])
        self.assertEqual(body["status"], "initiated")
        self.assertIn("check again", body["message"])

    def test_cannot_verify_someone_elses_payment(self):
        payment = self.khalti_payment()
        other = APIClient()
        other.force_authenticate(user=make_visitor("other@example.com"))
        self.assertEqual(other.post("/api/payments/verify/", {"reference": payment.reference}, format="json").status_code, 404)

    def test_completed_payment_invoice_is_downloadable_only_by_its_payer(self):
        payment = self.khalti_payment()
        payment.status = Payment.Status.COMPLETED
        payment.payer_name = self.visitor.full_name
        payment.payer_email = self.visitor.email
        payment.payer_phone = self.visitor.phone
        payment.provider_txn = "TX9"
        payment.completed_at = timezone.now()
        payment.save()

        response = self.client.get(f"/api/payments/{payment.reference}/invoice/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="invoice-{payment.reference}.pdf"',
        )
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertTrue(response.content.startswith(b"%PDF-"))

        other = APIClient()
        other.force_authenticate(user=make_visitor("other@example.com"))
        self.assertEqual(other.get(f"/api/payments/{payment.reference}/invoice/").status_code, 404)

    def test_invoice_is_unavailable_until_payment_is_confirmed(self):
        payment = self.khalti_payment()
        self.assertEqual(self.client.get(f"/api/payments/{payment.reference}/invoice/").status_code, 404)

    # ---- verifying: eSewa ----
    def esewa_payment(self, amount=500):
        return Payment.objects.create(visitor=self.visitor, provider="esewa", amount=amount, is_test=True)

    def test_esewa_signed_redirect_plus_status_check_confirms(self):
        payment = self.esewa_payment(500)
        status_body = {"product_code": "EPAYTEST", "transaction_uuid": payment.reference, "total_amount": 500.0, "status": "COMPLETE", "ref_id": "0001TS9"}
        with mock.patch.object(gateways, "_request", return_value=(200, status_body)) as call:
            body = self.verify(payment.reference, esewa_redirect(payment.reference, 500)).json()
        self.assertEqual((body["status"], body["checked"]), ("completed", True))
        url = call.call_args[0][1]
        self.assertTrue(url.startswith("https://rc.esewa.com.np/api/epay/transaction/status/?"))
        self.assertIn(f"transaction_uuid={payment.reference}", url)
        self.assertIn("total_amount=500", url)
        payment.refresh_from_db()
        self.assertEqual((payment.provider_ref, payment.provider_txn), ("000AWEO", "0001TS9"))

    def test_esewa_tampered_redirect_is_rejected_and_changes_nothing(self):
        payment = self.esewa_payment(500)
        with mock.patch.object(gateways, "_request") as call:
            response = self.verify(payment.reference, esewa_redirect(payment.reference, 500, tamper=True))
            self.assertEqual(response.status_code, 400)
            call.assert_not_called()
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, "initiated")

    def test_esewa_redirect_signed_with_wrong_key_or_for_another_payment_is_rejected(self):
        payment = self.esewa_payment(500)
        self.assertEqual(self.verify(payment.reference, esewa_redirect(payment.reference, 500, secret="not-the-key")).status_code, 400)
        self.assertEqual(self.verify(payment.reference, esewa_redirect("SUP-OTHER-ONE", 500)).status_code, 400)
        self.assertEqual(self.verify(payment.reference, esewa_redirect(payment.reference, 20)).status_code, 400)  # different amount
        self.assertEqual(self.verify(payment.reference, "%%%not-base64%%%").status_code, 400)

    def test_esewa_redirect_says_complete_but_status_api_says_otherwise(self):
        payment = self.esewa_payment(500)
        body = {"status": "PENDING", "total_amount": 500.0}
        with mock.patch.object(gateways, "_request", return_value=(200, body)):
            result = self.verify(payment.reference, esewa_redirect(payment.reference, 500)).json()
        self.assertEqual(result["status"], "pending")  # the redirect alone is never trusted

    def test_esewa_failure_return_without_data_uses_status_api(self):
        payment = self.esewa_payment(500)
        with mock.patch.object(gateways, "_request", return_value=(200, {"status": "NOT_FOUND", "total_amount": 500.0})):
            self.assertEqual(self.verify(payment.reference).json()["status"], "initiated")  # just started: still waiting
        Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timezone.timedelta(hours=2))
        with mock.patch.object(gateways, "_request", return_value=(200, {"status": "NOT_FOUND", "total_amount": 500.0})):
            self.assertEqual(self.verify(payment.reference).json()["status"], "failed")

    def test_esewa_status_check_tries_second_test_host(self):
        payment = self.esewa_payment(500)
        calls = []

        def fake(method, url, headers=None, payload=None, timeout=20):
            calls.append(url)
            if "rc.esewa" in url:
                raise gateways.GatewayUnavailable("no route")
            return 200, {"product_code": "EPAYTEST", "total_amount": 500.0, "status": "COMPLETE", "ref_id": "R1"}

        with mock.patch.object(gateways, "_request", fake):
            self.assertEqual(self.verify(payment.reference).json()["status"], "completed")
        self.assertEqual(len(calls), 2)
        self.assertIn("uat.esewa.com.np", calls[1])

    def test_esewa_amounts_with_thousands_commas_still_verify(self):
        payment = self.esewa_payment(1500)
        body = {
            "transaction_code": "T1", "status": "COMPLETE", "total_amount": "1,500.0",
            "transaction_uuid": payment.reference, "product_code": "EPAYTEST",
            "signed_field_names": "transaction_code,status,total_amount,transaction_uuid,product_code,signed_field_names",
        }
        msg = ",".join(f"{n}={body[n]}" for n in body["signed_field_names"].split(","))
        body["signature"] = gateways.esewa_sign(conf.TEST_ESEWA_SECRET_KEY, msg)
        data = base64.b64encode(json.dumps(body).encode()).decode()
        with mock.patch.object(gateways, "_request", return_value=(200, {"status": "COMPLETE", "total_amount": 1500.0, "ref_id": "R2"})):
            self.assertEqual(self.verify(payment.reference, data).json()["status"], "completed")

    # ---- admin / command ----
    def test_management_command_rechecks_waiting_payments(self):
        from django.core.management import call_command
        payment = self.khalti_payment(250)
        lookup = {"pidx": "PIDX123", "total_amount": 25000, "status": "Completed", "transaction_id": "TX1"}
        with mock.patch.object(gateways, "_request", return_value=(200, lookup)):
            call_command("check_pending_payments", verbosity=0)
        self.assertEqual(Payment.objects.get(pk=payment.pk).status, "completed")