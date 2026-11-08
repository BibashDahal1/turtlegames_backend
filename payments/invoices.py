from html import escape
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _display_time(value):
    if value is None:
        return "N/A"
    local_value = timezone.localtime(value)
    return local_value.strftime("%Y-%m-%d %H:%M %Z").strip()


def build_payment_invoice(payment):
    """Render a confirmed support payment as a downloadable PDF invoice."""
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Support payment invoice {payment.reference}",
        author="Turtle Games",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#174c3c"),
        spaceAfter=8 * mm,
    )
    label_style = ParagraphStyle(
        "InvoiceLabel",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#555555"),
    )
    value_style = styles["BodyText"]

    def row(label, value):
        return [
            Paragraph(escape(label), label_style),
            Paragraph(escape(str(value)) if value not in (None, "") else "N/A", value_style),
        ]

    details = [
        row("Invoice number", payment.reference),
        row("Payment status", "Paid"),
        row("Payer", payment.payer_name),
        row("Email", payment.payer_email),
        row("Phone", payment.payer_phone),
        row("Payment method", payment.get_provider_display()),
        row("Amount", f"{payment.currency} {payment.amount:.2f}"),
        row("Payment reference", payment.provider_ref),
        row("Provider transaction ID", payment.provider_txn),
        row("Status details", payment.status_note),
        row("Started at", _display_time(payment.created_at)),
        row("Last checked at", _display_time(payment.last_checked_at)),
        row("Paid at", _display_time(payment.completed_at)),
    ]

    story = [
        Paragraph("Turtle Games", styles["Heading2"]),
        Paragraph("Support payment invoice", title_style),
    ]
    if payment.is_test:
        story.extend(
            [
                Paragraph(
                    "<b>Test payment:</b> No real funds were transferred.",
                    styles["BodyText"],
                ),
                Spacer(1, 5 * mm),
            ]
        )
    story.append(
        Table(
            details,
            colWidths=[48 * mm, 112 * mm],
            hAlign="LEFT",
            style=TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9e2dd")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            ),
        )
    )
    document.build(story)
    return buffer.getvalue()
