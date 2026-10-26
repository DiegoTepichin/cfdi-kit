"""Typed, immutable model of a CFDI and its supported complements."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

ZERO = Decimal(0)


class InvoiceType(StrEnum):
    """`c_TipoDeComprobante`."""

    INCOME = "I"
    EXPENSE = "E"
    TRANSFER = "T"
    PAYROLL = "N"
    PAYMENT = "P"


class TaxKind(StrEnum):
    TRANSFERRED = "transferred"
    WITHHELD = "withheld"


class TaxCode(StrEnum):
    """`c_Impuesto`."""

    ISR = "001"
    IVA = "002"
    IEPS = "003"


@dataclass(frozen=True, slots=True)
class Tax:
    kind: TaxKind
    code: str
    factor_type: str | None
    rate: Decimal | None
    base: Decimal | None
    amount: Decimal | None

    @property
    def amount_or_zero(self) -> Decimal:
        return self.amount if self.amount is not None else ZERO


@dataclass(frozen=True, slots=True)
class Issuer:
    rfc: str
    name: str | None
    tax_regime: str | None


@dataclass(frozen=True, slots=True)
class Receiver:
    rfc: str
    name: str | None
    cfdi_use: str | None
    tax_regime: str | None
    postal_code: str | None


@dataclass(frozen=True, slots=True)
class Concept:
    product_key: str
    quantity: Decimal
    unit_key: str | None
    unit: str | None
    description: str
    unit_value: Decimal
    amount: Decimal
    discount: Decimal
    tax_object: str | None
    taxes: tuple[Tax, ...] = ()


@dataclass(frozen=True, slots=True)
class Stamp:
    """`TimbreFiscalDigital`: the SAT certification that makes the invoice valid."""

    uuid: str
    stamped_at: datetime
    sat_certificate: str | None
    provider_rfc: str | None


@dataclass(frozen=True, slots=True)
class PaymentDocument:
    """A previously issued invoice settled (fully or partially) by a payment."""

    uuid: str
    series: str | None
    folio: str | None
    currency: str | None
    exchange_rate: Decimal | None
    installment: int | None
    previous_balance: Decimal | None
    amount_paid: Decimal
    remaining_balance: Decimal | None
    taxes: tuple[Tax, ...] = ()


@dataclass(frozen=True, slots=True)
class Payment:
    paid_at: datetime
    payment_form: str
    currency: str
    exchange_rate: Decimal | None
    amount: Decimal
    documents: tuple[PaymentDocument, ...] = ()
    taxes: tuple[Tax, ...] = ()


@dataclass(frozen=True, slots=True)
class Payroll:
    payroll_type: str
    payment_date: date
    period_start: date
    period_end: date
    days_paid: Decimal
    total_perceptions: Decimal
    total_deductions: Decimal
    total_other_payments: Decimal
    isr_withheld: Decimal


@dataclass(frozen=True, slots=True)
class Relation:
    relation_type: str
    uuids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Cfdi:
    version: str
    invoice_type: InvoiceType
    issued_at: datetime
    series: str | None
    folio: str | None
    issuer: Issuer
    receiver: Receiver
    currency: str
    exchange_rate: Decimal | None
    subtotal: Decimal
    discount: Decimal
    total: Decimal
    payment_form: str | None
    payment_method: str | None
    place_of_issue: str | None
    concepts: tuple[Concept, ...]
    taxes: tuple[Tax, ...]
    total_transferred: Decimal | None
    total_withheld: Decimal | None
    stamp: Stamp | None
    relations: tuple[Relation, ...] = ()
    payments: tuple[Payment, ...] = ()
    payroll: Payroll | None = None
    source: str | None = field(default=None, compare=False)

    @property
    def uuid(self) -> str | None:
        return self.stamp.uuid if self.stamp else None

    @property
    def rate_to_mxn(self) -> Decimal:
        if self.currency in ("MXN", "XXX") or self.exchange_rate is None:
            return Decimal(1)
        return self.exchange_rate

    def tax_total(self, kind: TaxKind, code: TaxCode) -> Decimal:
        return sum(
            (t.amount_or_zero for t in self.taxes if t.kind is kind and t.code == code),
            ZERO,
        )

    @property
    def iva_transferred(self) -> Decimal:
        return self.tax_total(TaxKind.TRANSFERRED, TaxCode.IVA)

    @property
    def iva_withheld(self) -> Decimal:
        return self.tax_total(TaxKind.WITHHELD, TaxCode.IVA)

    @property
    def isr_withheld(self) -> Decimal:
        if self.payroll is not None:
            return self.payroll.isr_withheld
        return self.tax_total(TaxKind.WITHHELD, TaxCode.ISR)

    @property
    def ieps_transferred(self) -> Decimal:
        return self.tax_total(TaxKind.TRANSFERRED, TaxCode.IEPS)
