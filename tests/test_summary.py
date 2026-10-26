from decimal import Decimal

import pytest

from cfdi_kit.models import Cfdi
from cfdi_kit.summary import SUMMARY_COLUMNS, Amounts, Basis, summarize, summary_frame
from tests.conftest import MY_RFC, load


def months(cfdis: list[Cfdi], basis: Basis) -> dict[str, object]:
    return {m.month: m for m in summarize(cfdis, MY_RFC, basis).months}


def test_accrual_counts_invoices_on_their_issue_date(all_valid: list[Cfdi]) -> None:
    result = months(all_valid, Basis.ACCRUAL)

    assert list(result) == ["2025-12", "2026-01", "2026-02"]
    january = summarize(all_valid, MY_RFC).months[1]
    assert january.income == Amounts(
        net=Decimal("30000.00"),
        iva=Decimal("4800.00"),
        iva_withheld=Decimal("1066.67"),
        isr_withheld=Decimal("1000.00"),
    )
    assert january.expenses == Amounts(net=Decimal("1000.00"), iva=Decimal("160.00"))
    assert (january.issued_count, january.received_count) == (2, 1)
    assert january.net_iva == Decimal("3573.33")


def test_foreign_currency_is_converted_with_the_invoice_rate(all_valid: list[Cfdi]) -> None:
    december = summarize(all_valid, MY_RFC).months[0]

    assert december.expenses.net == Decimal("4625.00")
    assert december.expenses.iva == Decimal("740.00")


def test_credit_notes_subtract(all_valid: list[Cfdi]) -> None:
    february = summarize(all_valid, MY_RFC).months[2]

    assert february.income.net == Decimal("-500.00")
    assert february.income.iva == Decimal("-80.00")


def test_cash_basis_moves_ppd_invoices_to_their_payment_date(all_valid: list[Cfdi]) -> None:
    december, january, february = summarize(all_valid, MY_RFC, Basis.CASH).months

    assert december.expenses == Amounts()
    assert december.received_count == 1
    assert january.income.net == Decimal("10000.00")
    assert january.income.iva == Decimal("1600.00")
    assert february.income.net == Decimal("19500.00")
    assert february.income.iva == Decimal("3120.00")


def test_cash_basis_prorates_pagos_10_with_the_original_invoice(all_valid: list[Cfdi]) -> None:
    summary = summarize(all_valid, MY_RFC, Basis.CASH)
    january = summary.months[1]

    assert january.expenses.net == Decimal("1000.00") + Decimal("2250.00")
    assert january.expenses.iva == Decimal("160.00") + Decimal("360.00")
    assert summary.unmatched_payments == ()


def test_cash_basis_flags_payments_without_breakdown_or_original() -> None:
    summary = summarize([load("payment_10.xml")], MY_RFC, Basis.CASH)

    assert summary.unmatched_payments == ("6F1C2A7E-1B2C-4D3E-9F40-0A1B2C3D4E07",)
    assert summary.months[0].expenses.net == Decimal("2610.00")


def test_payroll_is_tracked_separately() -> None:
    payroll = load("payroll_40.xml")

    employee = summarize([payroll], "FUNK671228PH6").months[0]
    employer = summarize([payroll], "EKU9003173C9").months[0]

    assert employee.payroll_received == Decimal("15500.00")
    assert employee.income == Amounts()
    assert employer.payroll_paid == Decimal("15500.00")


def test_invoices_of_other_rfcs_are_ignored() -> None:
    assert summarize([load("payroll_40.xml")], MY_RFC).months == ()


def test_rfc_is_case_insensitive() -> None:
    summary = summarize([load("income_pue_40.xml")], f" {MY_RFC.lower()} ")

    assert summary.rfc == MY_RFC
    assert summary.months[0].issued_count == 1


def test_summary_frame(all_valid: list[Cfdi]) -> None:
    frame = summary_frame(summarize(all_valid, MY_RFC))

    assert list(frame.columns) == SUMMARY_COLUMNS
    assert frame["month"].tolist() == ["2025-12", "2026-01", "2026-02"]
    assert frame["net_iva"].iloc[1] == pytest.approx(3573.33)
