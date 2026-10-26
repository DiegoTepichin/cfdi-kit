"""Monthly income, expenses and taxes for one RFC, on accrual or cash basis.

The result is an estimate to help review a period. It is not a tax return.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from cfdi_kit.export import Direction, direction
from cfdi_kit.models import ZERO, InvoiceType, TaxCode, TaxKind, sum_taxes

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date, datetime

    from cfdi_kit.models import Cfdi, Payment, PaymentDocument, Tax

CENT = Decimal("0.01")


class Basis(StrEnum):
    ACCRUAL = "accrual"
    """Invoices count on their issue date."""
    CASH = "cash"
    """PUE invoices count on their issue date; PPD invoices when a payment settles them."""


@dataclass(frozen=True, slots=True)
class Amounts:
    """Money in MXN for one side (issued or received) of a month."""

    net: Decimal = ZERO
    iva: Decimal = ZERO
    ieps: Decimal = ZERO
    iva_withheld: Decimal = ZERO
    isr_withheld: Decimal = ZERO

    def __add__(self, other: Amounts) -> Amounts:
        return Amounts(*(getattr(self, f.name) + getattr(other, f.name) for f in fields(self)))

    def scaled(self, factor: Decimal) -> Amounts:
        return Amounts(*(getattr(self, f.name) * factor for f in fields(self)))

    def rounded(self) -> Amounts:
        return Amounts(*(getattr(self, f.name).quantize(CENT) for f in fields(self)))


@dataclass(frozen=True, slots=True)
class MonthSummary:
    month: str
    income: Amounts
    expenses: Amounts
    payroll_received: Decimal
    payroll_paid: Decimal
    issued_count: int
    received_count: int

    @property
    def net_iva(self) -> Decimal:
        """VAT charged, minus VAT withheld by clients, minus creditable VAT. Positive is payable."""
        return self.income.iva - self.income.iva_withheld - self.expenses.iva


@dataclass(frozen=True, slots=True)
class Summary:
    rfc: str
    basis: Basis
    months: tuple[MonthSummary, ...]
    unmatched_payments: tuple[str, ...]
    """UUIDs settled by a payment complement whose amounts had to be taken as fully taxable base
    because neither the tax breakdown nor the original invoice was available."""


def summarize(cfdis: Sequence[Cfdi], rfc: str, basis: Basis = Basis.ACCRUAL) -> Summary:
    rfc = rfc.strip().upper()
    ledger = _Ledger()
    by_uuid = {c.uuid: c for c in cfdis if c.uuid}
    unmatched: list[str] = []
    for cfdi in cfdis:
        side = direction(cfdi, rfc)
        if side is Direction.OTHER:
            continue
        if cfdi.invoice_type is InvoiceType.PAYROLL:
            ledger.add_payroll(cfdi, side)
        elif cfdi.invoice_type in (InvoiceType.INCOME, InvoiceType.EXPENSE):
            if basis is Basis.ACCRUAL or cfdi.payment_method != "PPD":
                ledger.add(cfdi.issued_at, side, _invoice_amounts(cfdi), counted=True)
            else:
                ledger.count(cfdi.issued_at, side)
        elif cfdi.invoice_type is InvoiceType.PAYMENT and basis is Basis.CASH:
            for payment in cfdi.payments:
                for document in payment.documents:
                    amounts, matched = _paid_amounts(payment, document, by_uuid.get(document.uuid))
                    ledger.add(payment.paid_at, side, amounts, counted=False)
                    if not matched:
                        unmatched.append(document.uuid)
    return Summary(rfc, basis, ledger.months(), tuple(unmatched))


def summary_frame(summary: Summary) -> pd.DataFrame:
    """One row per month with every amount as a float column."""
    rows = [
        {
            "month": m.month,
            "income": float(m.income.net),
            "iva_charged": float(m.income.iva),
            "iva_withheld_by_clients": float(m.income.iva_withheld),
            "isr_withheld_by_clients": float(m.income.isr_withheld),
            "expenses": float(m.expenses.net),
            "iva_creditable": float(m.expenses.iva),
            "iva_withheld_from_suppliers": float(m.expenses.iva_withheld),
            "isr_withheld_from_suppliers": float(m.expenses.isr_withheld),
            "net_iva": float(m.net_iva),
            "payroll_received": float(m.payroll_received),
            "payroll_paid": float(m.payroll_paid),
            "issued_count": m.issued_count,
            "received_count": m.received_count,
        }
        for m in summary.months
    ]
    return pd.DataFrame(rows, columns=SUMMARY_COLUMNS)


SUMMARY_COLUMNS = [
    "month",
    "income",
    "iva_charged",
    "iva_withheld_by_clients",
    "isr_withheld_by_clients",
    "expenses",
    "iva_creditable",
    "iva_withheld_from_suppliers",
    "isr_withheld_from_suppliers",
    "net_iva",
    "payroll_received",
    "payroll_paid",
    "issued_count",
    "received_count",
]


def _month(moment: date) -> str:
    return f"{moment.year:04d}-{moment.month:02d}"


def _invoice_amounts(cfdi: Cfdi) -> Amounts:
    sign = Decimal(-1) if cfdi.invoice_type is InvoiceType.EXPENSE else Decimal(1)
    amounts = Amounts(
        net=cfdi.subtotal - cfdi.discount,
        iva=cfdi.iva_transferred,
        ieps=cfdi.ieps_transferred,
        iva_withheld=cfdi.iva_withheld,
        isr_withheld=cfdi.isr_withheld,
    )
    return amounts.scaled(sign * cfdi.rate_to_mxn)


def _taxes_amounts(taxes: Sequence[Tax], paid: Decimal) -> Amounts:
    iva = sum_taxes(taxes, TaxKind.TRANSFERRED, TaxCode.IVA)
    ieps = sum_taxes(taxes, TaxKind.TRANSFERRED, TaxCode.IEPS)
    iva_withheld = sum_taxes(taxes, TaxKind.WITHHELD, TaxCode.IVA)
    isr_withheld = sum_taxes(taxes, TaxKind.WITHHELD, TaxCode.ISR)
    return Amounts(
        net=paid - iva - ieps + iva_withheld + isr_withheld,
        iva=iva,
        ieps=ieps,
        iva_withheld=iva_withheld,
        isr_withheld=isr_withheld,
    )


def _document_to_mxn(payment: Payment, document: PaymentDocument) -> Decimal:
    """Factor that converts amounts in the settled invoice's currency to MXN at the payment date."""
    payment_rate = Decimal(1) if payment.currency == "MXN" else payment.exchange_rate or Decimal(1)
    same_currency = document.currency in (None, payment.currency)
    equivalence = Decimal(1) if same_currency else document.exchange_rate or Decimal(1)
    return payment_rate / equivalence


def _paid_amounts(
    payment: Payment, document: PaymentDocument, original: Cfdi | None
) -> tuple[Amounts, bool]:
    to_mxn = _document_to_mxn(payment, document)
    paid = document.amount_paid
    if document.taxes:
        return _taxes_amounts(document.taxes, paid).scaled(to_mxn), True
    if original is not None and original.total:
        share = paid / original.total
        return _invoice_amounts(original).scaled(share / original.rate_to_mxn * to_mxn), True
    return Amounts(net=paid).scaled(to_mxn), False


class _Ledger:
    def __init__(self) -> None:
        self._amounts: dict[tuple[str, Direction], Amounts] = defaultdict(Amounts)
        self._counts: dict[tuple[str, Direction], int] = defaultdict(int)
        self._payroll: dict[tuple[str, Direction], Decimal] = defaultdict(Decimal)
        self._months: set[str] = set()

    def add(self, moment: datetime, side: Direction, amounts: Amounts, *, counted: bool) -> None:
        key = (_month(moment), side)
        self._amounts[key] = self._amounts[key] + amounts
        self._months.add(key[0])
        if counted:
            self._counts[key] += 1

    def count(self, moment: datetime, side: Direction) -> None:
        key = (_month(moment), side)
        self._counts[key] += 1
        self._months.add(key[0])

    def add_payroll(self, cfdi: Cfdi, side: Direction) -> None:
        payroll = cfdi.payroll
        moment = cfdi.issued_at if payroll is None else payroll.payment_date
        key = (_month(moment), side)
        gross = (
            cfdi.subtotal
            if payroll is None
            else (payroll.total_perceptions + payroll.total_other_payments)
        )
        self._payroll[key] += gross * cfdi.rate_to_mxn
        self._months.add(key[0])

    def months(self) -> tuple[MonthSummary, ...]:
        return tuple(self._month_summary(m) for m in sorted(self._months))

    def _month_summary(self, month: str) -> MonthSummary:
        issued = (month, Direction.ISSUED)
        received = (month, Direction.RECEIVED)
        return MonthSummary(
            month=month,
            income=self._amounts.get(issued, Amounts()).rounded(),
            expenses=self._amounts.get(received, Amounts()).rounded(),
            payroll_received=self._payroll.get(received, ZERO).quantize(CENT),
            payroll_paid=self._payroll.get(issued, ZERO).quantize(CENT),
            issued_count=self._counts.get(issued, 0),
            received_count=self._counts.get(received, 0),
        )
