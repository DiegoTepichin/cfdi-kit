from datetime import date, datetime
from decimal import Decimal

import pytest

from cfdi_kit.models import InvoiceType, TaxKind
from cfdi_kit.parser import CfdiParseError, parse_bytes, parse_file
from tests.conftest import FIXTURES, load


def test_parses_income_invoice_header() -> None:
    cfdi = load("income_pue_40.xml")

    assert cfdi.version == "4.0"
    assert cfdi.invoice_type is InvoiceType.INCOME
    assert cfdi.issued_at == datetime(2026, 1, 15, 10, 30)
    assert (cfdi.series, cfdi.folio) == ("A", "101")
    assert cfdi.subtotal == Decimal("10000.00")
    assert cfdi.total == Decimal("9533.33")
    assert cfdi.payment_method == "PUE"
    assert cfdi.payment_form == "03"
    assert cfdi.source is not None
    assert cfdi.source.endswith("income_pue_40.xml")


def test_parses_parties() -> None:
    cfdi = load("income_pue_40.xml")

    assert cfdi.issuer.rfc == "CACX7605101P8"
    assert cfdi.issuer.tax_regime == "612"
    assert cfdi.receiver.rfc == "EKU9003173C9"
    assert cfdi.receiver.cfdi_use == "G03"
    assert cfdi.receiver.postal_code == "42501"


def test_parses_invoice_level_taxes() -> None:
    cfdi = load("income_pue_40.xml")

    assert cfdi.iva_transferred == Decimal("1600.00")
    assert cfdi.iva_withheld == Decimal("1066.67")
    assert cfdi.isr_withheld == Decimal("1000.00")
    assert cfdi.total_withheld == Decimal("2066.67")
    assert cfdi.total_transferred == Decimal("1600.00")


def test_parses_concepts_with_their_taxes() -> None:
    (concept,) = load("income_pue_40.xml").concepts

    assert concept.product_key == "81111500"
    assert concept.quantity == Decimal(1)
    assert concept.amount == Decimal("10000.00")
    assert concept.tax_object == "02"
    kinds = [(t.kind, t.code) for t in concept.taxes]
    assert kinds == [
        (TaxKind.TRANSFERRED, "002"),
        (TaxKind.WITHHELD, "001"),
        (TaxKind.WITHHELD, "002"),
    ]
    assert concept.taxes[0].rate == Decimal("0.160000")


def test_uuid_is_normalized_to_upper_case() -> None:
    assert load("income_pue_40.xml").uuid == "6F1C2A7E-1B2C-4D3E-9F40-0A1B2C3D4E01"


def test_parses_stamp() -> None:
    stamp = load("income_pue_40.xml").stamp

    assert stamp is not None
    assert stamp.stamped_at == datetime(2026, 1, 15, 10, 31, 12)
    assert stamp.provider_rfc == "SAT970701NN3"


def test_parses_discount_and_relations() -> None:
    assert load("expense_pue_40.xml").discount == Decimal("100.00")

    (relation,) = load("credit_note_40.xml").relations
    assert relation.relation_type == "01"
    assert relation.uuids == ("6F1C2A7E-1B2C-4D3E-9F40-0A1B2C3D4E01",)


def test_parses_cfdi_33_in_foreign_currency() -> None:
    cfdi = load("expense_ppd_usd_33.xml")

    assert cfdi.version == "3.3"
    assert cfdi.currency == "USD"
    assert cfdi.rate_to_mxn == Decimal("18.50")
    assert cfdi.receiver.tax_regime is None
    assert cfdi.iva_transferred == Decimal("40.00")


def test_rate_to_mxn_is_one_for_pesos() -> None:
    assert load("income_pue_40.xml").rate_to_mxn == Decimal(1)


def test_parses_pagos_20() -> None:
    cfdi = load("payment_20.xml")

    assert cfdi.invoice_type is InvoiceType.PAYMENT
    (payment,) = cfdi.payments
    assert payment.paid_at == datetime(2026, 2, 10, 12)
    assert payment.amount == Decimal("23200.00")
    assert payment.taxes[0].amount == Decimal("3200.00")
    (document,) = payment.documents
    assert document.uuid == "6F1C2A7E-1B2C-4D3E-9F40-0A1B2C3D4E02"
    assert document.installment == 1
    assert document.amount_paid == Decimal("23200.00")
    assert document.remaining_balance == Decimal("0.00")
    assert document.taxes[0].base == Decimal("20000.00")


def test_parses_pagos_10() -> None:
    (payment,) = load("payment_10.xml").payments

    assert payment.currency == "USD"
    assert payment.exchange_rate == Decimal("18.00")
    (document,) = payment.documents
    assert document.amount_paid == Decimal("145.00")
    assert document.taxes == ()


def test_parses_payroll() -> None:
    cfdi = load("payroll_40.xml")

    assert cfdi.payroll is not None
    assert cfdi.payroll.payment_date == date(2026, 1, 31)
    assert cfdi.payroll.days_paid == Decimal(16)
    assert cfdi.payroll.total_perceptions == Decimal("15500.00")
    assert cfdi.isr_withheld == Decimal("1900.00")


def test_parse_bytes_tolerates_leading_whitespace() -> None:
    data = b"\n\n  " + (FIXTURES / "income_pue_40.xml").read_bytes()

    assert parse_bytes(data).uuid is not None


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("truncated.xml", "invalid XML"),
        ("not_a_cfdi.xml", "expected a CFDI"),
        ("cfdi_32.xml", "unsupported CFDI version '3.2'"),
    ],
)
def test_rejects_unsupported_documents(name: str, message: str) -> None:
    path = FIXTURES / "invalid" / name

    with pytest.raises(CfdiParseError, match=message) as error:
        parse_file(path)
    assert error.value.source == str(path)


def test_reports_bad_numbers() -> None:
    data = (
        (FIXTURES / "income_pue_40.xml").read_bytes().replace(b'Total="9533.33"', b'Total="9,533"')
    )

    with pytest.raises(CfdiParseError, match="'9,533' is not a number"):
        parse_bytes(data, source="x.xml")


def test_reports_missing_required_attribute() -> None:
    data = (FIXTURES / "income_pue_40.xml").read_bytes().replace(b' Moneda="MXN"', b"")

    with pytest.raises(CfdiParseError, match="missing attribute Moneda"):
        parse_bytes(data)
