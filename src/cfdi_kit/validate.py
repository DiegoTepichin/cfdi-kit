"""Consistency checks that catch capture errors and suspicious invoices before they reach a report.

These checks read only the XML. They do not verify the digital seals or ask the SAT whether an
invoice was cancelled.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import pandas as pd

from cfdi_kit.models import ZERO, InvoiceType, TaxKind

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from cfdi_kit.models import Cfdi

CENT = Decimal("0.01")
RFC_PATTERN = re.compile(r"^([A-ZÑ&]{3,4})(\d{2})(\d{2})(\d{2})([A-Z\d]{3})$")
GENERIC_RFCS = frozenset({"XAXX010101000", "XEXX010101000"})


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Issue:
    severity: Severity
    code: str
    message: str
    uuid: str | None
    source: str | None


def is_valid_rfc(rfc: str) -> bool:
    """Structure of a persona moral (12 characters) or física (13) RFC, including its date."""
    if rfc in GENERIC_RFCS:
        return True
    match = RFC_PATTERN.match(rfc)
    if match is None:
        return False
    yy, mm, dd = (int(g) for g in match.group(2, 3, 4))
    try:
        date(2000 + yy, mm, dd)
    except ValueError:
        return False
    return True


def validate(cfdis: Sequence[Cfdi]) -> list[Issue]:
    issues = [issue for cfdi in cfdis for check in CHECKS for issue in check(cfdi)]
    issues.extend(_duplicates(cfdis))
    return issues


def issues_frame(issues: Iterable[Issue]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "severity": i.severity.value,
                "code": i.code,
                "message": i.message,
                "uuid": i.uuid,
                "source": i.source,
            }
            for i in issues
        ],
        columns=["severity", "code", "message", "uuid", "source"],
    )


def _issue(cfdi: Cfdi, severity: Severity, code: str, message: str) -> Issue:
    return Issue(severity, code, message, cfdi.uuid, cfdi.source)


def _tolerance(cfdi: Cfdi) -> Decimal:
    """SAT rounding allows one cent of drift per line item."""
    return CENT * max(len(cfdi.concepts), 1)


def _check_stamp(cfdi: Cfdi) -> Iterator[Issue]:
    if cfdi.stamp is None:
        yield _issue(
            cfdi, Severity.ERROR, "missing-stamp", "no TimbreFiscalDigital: not a valid CFDI"
        )


def _check_total(cfdi: Cfdi) -> Iterator[Issue]:
    if cfdi.invoice_type is InvoiceType.PAYMENT:
        return
    expected = (
        cfdi.subtotal
        - cfdi.discount
        + (cfdi.total_transferred or ZERO)
        - (cfdi.total_withheld or ZERO)
    )
    if abs(expected - cfdi.total) > _tolerance(cfdi):
        yield _issue(
            cfdi,
            Severity.ERROR,
            "total-mismatch",
            f"Total is {cfdi.total} but SubTotal - Descuento + taxes is {expected}",
        )


def _check_concepts(cfdi: Cfdi) -> Iterator[Issue]:
    if not cfdi.concepts:
        return
    amounts = sum((c.amount for c in cfdi.concepts), ZERO)
    if abs(amounts - cfdi.subtotal) > _tolerance(cfdi):
        yield _issue(
            cfdi,
            Severity.ERROR,
            "subtotal-mismatch",
            f"SubTotal is {cfdi.subtotal} but line items add up to {amounts}",
        )
    discounts = sum((c.discount for c in cfdi.concepts), ZERO)
    if abs(discounts - cfdi.discount) > _tolerance(cfdi):
        yield _issue(
            cfdi,
            Severity.ERROR,
            "discount-mismatch",
            f"Descuento is {cfdi.discount} but line items add up to {discounts}",
        )


def _check_tax_breakdown(cfdi: Cfdi) -> Iterator[Issue]:
    for kind, declared in (
        (TaxKind.TRANSFERRED, cfdi.total_transferred),
        (TaxKind.WITHHELD, cfdi.total_withheld),
    ):
        if declared is None:
            continue
        lines = sum(
            (t.amount_or_zero for c in cfdi.concepts for t in c.taxes if t.kind is kind),
            ZERO,
        )
        if abs(lines - declared) > _tolerance(cfdi):
            yield _issue(
                cfdi,
                Severity.WARNING,
                f"{kind.value}-taxes-mismatch",
                f"{kind.value} taxes total {declared} but line items add up to {lines}",
            )


def _check_rfcs(cfdi: Cfdi) -> Iterator[Issue]:
    for role, rfc in (("issuer", cfdi.issuer.rfc), ("receiver", cfdi.receiver.rfc)):
        if not is_valid_rfc(rfc):
            yield _issue(cfdi, Severity.ERROR, "invalid-rfc", f"{role} RFC {rfc!r} is malformed")


def _check_payment_method(cfdi: Cfdi) -> Iterator[Issue]:
    if cfdi.version == "4.0" and cfdi.payment_method == "PPD" and cfdi.payment_form != "99":
        yield _issue(
            cfdi,
            Severity.WARNING,
            "ppd-payment-form",
            f"PPD invoices should use FormaPago 99 (Por definir), found {cfdi.payment_form}",
        )


def _check_exchange_rate(cfdi: Cfdi) -> Iterator[Issue]:
    if cfdi.currency not in ("MXN", "XXX") and cfdi.exchange_rate is None:
        yield _issue(
            cfdi,
            Severity.ERROR,
            "missing-exchange-rate",
            f"currency {cfdi.currency} requires TipoCambio",
        )


def _duplicates(cfdis: Sequence[Cfdi]) -> Iterator[Issue]:
    counts = Counter(c.uuid for c in cfdis if c.uuid)
    for cfdi in cfdis:
        if cfdi.uuid and counts[cfdi.uuid] > 1:
            yield _issue(
                cfdi,
                Severity.WARNING,
                "duplicate-uuid",
                f"UUID appears {counts[cfdi.uuid]} times",
            )


CHECKS: tuple[Callable[[Cfdi], Iterator[Issue]], ...] = (
    _check_stamp,
    _check_total,
    _check_concepts,
    _check_tax_breakdown,
    _check_rfcs,
    _check_payment_method,
    _check_exchange_rate,
)
