from django.urls import path

from .views import ConfigView, InvoiceView, StartView, VerifyView

urlpatterns = [
    path("config/", ConfigView.as_view(), name="payments-config"),
    path("start/", StartView.as_view(), name="payments-start"),
    path("verify/", VerifyView.as_view(), name="payments-verify"),
    path("<str:reference>/invoice/", InvoiceView.as_view(), name="payments-invoice"),
]