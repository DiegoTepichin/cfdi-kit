"""Flatten CFDIs into pandas tables and write them as CSV or Excel."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from cfdi_kit.catalogs import Catalog, label
from cfdi_kit.models import TaxCode, TaxKind, sum_taxes

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from decimal import Decimal
    from pathlib import Path

    from cfdi_kit.models import Cfdi, Concept, Payment, PaymentDocument

Row = dict[str, str | float | int | datetime | None]


class Direction(StrEnum):
    ISSUED = "issued"
    RECEIVED = "received"
    OTHER = "other"


def direction(cfdi: Cfdi, rfc: str) -> Direction:
    """Whether `rfc` issued or received the invoice."""
    rfc = rfc.strip().upper()
    if cfdi.issuer.rfc == rfc:
        return Direction.ISSUED
    if cfdi.receiver.rfc == rfc:
        return Direction.RECEIVED
    return Direction.OTHER


def invoices_frame(cfdis: Iterable[Cfdi], rfc: str | None = None) -> pd.DataFrame:
    """One row per CFDI."""
    return _frame([_invoice_row(c, rfc) for c in cfdis], INVOICE_COLUMNS)


def concepts_frame(cfdis: Iterable[Cfdi]) -> pd.DataFrame:
    """One row per line item (`Concepto`)."""
    rows = [_concept_row(c, concept) for c in cfdis for concept in c.concepts]
    return _frame(rows, CONCEPT_COLUMNS)


def payments_frame(cfdis: Iterable[Cfdi]) -> pd.DataFrame:
    """One row per invoice settled in a payment complement."""
    rows = [
        _payment_row(c, payment, document)
        for c in cfdis
        for payment in c.payments
        for document in payment.documents
    ]
    return _frame(rows, PAYMENT_COLUMNS)


def to_csv(cfdis: Sequence[Cfdi], path: str | Path, rfc: str | None = None) -> None:
    invoices_frame(cfdis, rfc).to_csv(path, index=False)


def to_excel(cfdis: Sequence[Cfdi], path: str | Path, rfc: str | None = None) -> None:
    """Write `invoices`, `line_items` and `payments` sheets."""
    sheets = {
        "invoices": invoices_frame(cfdis, rfc),
        "line_items": concepts_frame(cfdis),
        "payments": payments_frame(cfdis),
    }
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
            sheet = writer.sheets[name]
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for column, header in zip(sheet.columns, frame.columns, strict=True):
                width = max([len(str(header)), *(len(str(c.value or "")) for c in column[1:200])])
                sheet.column_dimensions[column[0].column_letter].width = min(width + 2, 60)


INVOICE_COLUMNS = (
    "uuid",
    "direction",
    "version",
    "type",
    "type_label",
    "issued_at",
    "stamped_at",
    "series",
    "folio",
    "issuer_rfc",
    "issuer_name",
    "issuer_tax_regime",
    "receiver_rfc",
    "receiver_name",
    "cfdi_use",
    "payment_method",
    "payment_form",
    "payment_form_label",
    "currency",
    "exchange_rate",
    "subtotal",
    "discount",
    "iva_transferred",
    "ieps_transferred",
    "iva_withheld",
    "isr_withheld",
    "total",
    "total_mxn",
    "related_uuids",
    "source",
)

CONCEPT_COLUMNS = (
    "uuid",
    "issued_at",
    "type",
    "issuer_rfc",
    "receiver_rfc",
    "product_key",
    "description",
    "quantity",
    "unit_key",
    "unit_value",
    "amount",
    "discount",
    "iva_transferred",
    "iva_withheld",
    "isr_withheld",
)

PAYMENT_COLUMNS = (
    "payment_uuid",
    "paid_at",
    "issuer_rfc",
    "receiver_rfc",
    "payment_form",
    "currency",
    "exchange_rate",
    "payment_amount",
    "document_uuid",
    "document_currency",
    "installment",
    "previous_balance",
    "amount_paid",
    "remaining_balance",
    "iva_paid",
)


def _frame(rows: list[Row], columns: tuple[str, ...]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=list(columns))
    for column in columns:
        if column.endswith("_at"):
            frame[column] = pd.to_datetime(frame[column])
    return frame


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _invoice_row(cfdi: Cfdi, rfc: str | None) -> Row:
    return {
        "uuid": cfdi.uuid,
        "direction": direction(cfdi, rfc).value if rfc else None,
        "version": cfdi.version,
        "type": cfdi.invoice_type.value,
        "type_label": label(Catalog.INVOICE_TYPE, cfdi.invoice_type.value),
        "issued_at": cfdi.issued_at,
        "stamped_at": cfdi.stamp.stamped_at if cfdi.stamp else None,
        "series": cfdi.series,
        "folio": cfdi.folio,
        "issuer_rfc": cfdi.issuer.rfc,
        "issuer_name": cfdi.issuer.name,
        "issuer_tax_regime": cfdi.issuer.tax_regime,
        "receiver_rfc": cfdi.receiver.rfc,
        "receiver_name": cfdi.receiver.name,
        "cfdi_use": cfdi.receiver.cfdi_use,
        "payment_method": cfdi.payment_method,
        "payment_form": cfdi.payment_form,
        "payment_form_label": label(Catalog.PAYMENT_FORM, cfdi.payment_form),
        "currency": cfdi.currency,
        "exchange_rate": _money(cfdi.exchange_rate),
        "subtotal": _money(cfdi.subtotal),
        "discount": _money(cfdi.discount),
        "iva_transferred": _money(cfdi.iva_transferred),
        "ieps_transferred": _money(cfdi.ieps_transferred),
        "iva_withheld": _money(cfdi.iva_withheld),
        "isr_withheld": _money(cfdi.isr_withheld),
        "total": _money(cfdi.total),
        "total_mxn": _money(cfdi.total * cfdi.rate_to_mxn),
        "related_uuids": " ".join(u for r in cfdi.relations for u in r.uuids) or None,
        "source": cfdi.source,
    }


def _concept_row(cfdi: Cfdi, concept: Concept) -> Row:
    return {
        "uuid": cfdi.uuid,
        "issued_at": cfdi.issued_at,
        "type": cfdi.invoice_type.value,
        "issuer_rfc": cfdi.issuer.rfc,
        "receiver_rfc": cfdi.receiver.rfc,
        "product_key": concept.product_key,
        "description": concept.description,
        "quantity": _money(concept.quantity),
        "unit_key": concept.unit_key,
        "unit_value": _money(concept.unit_value),
        "amount": _money(concept.amount),
        "discount": _money(concept.discount),
        "iva_transferred": _money(sum_taxes(concept.taxes, TaxKind.TRANSFERRED, TaxCode.IVA)),
        "iva_withheld": _money(sum_taxes(concept.taxes, TaxKind.WITHHELD, TaxCode.IVA)),
        "isr_withheld": _money(sum_taxes(concept.taxes, TaxKind.WITHHELD, TaxCode.ISR)),
    }


def _payment_row(cfdi: Cfdi, payment: Payment, document: PaymentDocument) -> Row:
    iva_paid = sum_taxes(document.taxes, TaxKind.TRANSFERRED, TaxCode.IVA)
    return {
        "payment_uuid": cfdi.uuid,
        "paid_at": payment.paid_at,
        "issuer_rfc": cfdi.issuer.rfc,
        "receiver_rfc": cfdi.receiver.rfc,
        "payment_form": payment.payment_form,
        "currency": payment.currency,
        "exchange_rate": _money(payment.exchange_rate),
        "payment_amount": _money(payment.amount),
        "document_uuid": document.uuid,
        "document_currency": document.currency,
        "installment": document.installment,
        "previous_balance": _money(document.previous_balance),
        "amount_paid": _money(document.amount_paid),
        "remaining_balance": _money(document.remaining_balance),
        "iva_paid": _money(iva_paid) if document.taxes else None,
    }
