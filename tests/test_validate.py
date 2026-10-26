from dataclasses import replace
from decimal import Decimal

import pytest

from cfdi_kit.models import Cfdi, Issuer
from cfdi_kit.validate import Severity, is_valid_rfc, issues_frame, validate
from tests.conftest import load


def codes(cfdis: list[Cfdi]) -> list[str]:
    return [issue.code for issue in validate(cfdis)]


def test_fixtures_are_clean(all_valid: list[Cfdi]) -> None:
    assert validate(all_valid) == []


@pytest.mark.parametrize(
    "rfc",
    ["EKU9003173C9", "CACX7605101P8", "XAXX010101000", "&ÑA0101011A1"],
)
def test_valid_rfcs(rfc: str) -> None:
    assert is_valid_rfc(rfc)


@pytest.mark.parametrize("rfc", ["EKU900317", "CACX761305AB1", "cacx7605101p8", "1234567890123"])
def test_invalid_rfcs(rfc: str) -> None:
    assert not is_valid_rfc(rfc)


def test_detects_wrong_total() -> None:
    cfdi = replace(load("income_pue_40.xml"), total=Decimal("9600.00"))

    (issue,) = validate([cfdi])
    assert issue.code == "total-mismatch"
    assert issue.severity is Severity.ERROR
    assert "9533.33" in issue.message


def test_tolerates_one_cent_of_rounding() -> None:
    cfdi = replace(load("income_pue_40.xml"), total=Decimal("9533.34"))

    assert validate([cfdi]) == []


def test_detects_subtotal_and_discount_mismatch() -> None:
    cfdi = load("expense_pue_40.xml")
    broken = replace(
        cfdi, subtotal=Decimal("1200.00"), discount=Decimal(0), total=Decimal("1360.00")
    )

    assert codes([broken]) == ["subtotal-mismatch", "discount-mismatch"]


def test_detects_tax_breakdown_mismatch() -> None:
    cfdi = load("expense_pue_40.xml")
    broken = replace(cfdi, total_transferred=Decimal("200.00"), total=Decimal("1200.00"))

    assert codes([broken]) == ["transferred-taxes-mismatch"]


def test_detects_missing_stamp_and_bad_rfc() -> None:
    cfdi = load("income_pue_40.xml")
    broken = replace(cfdi, stamp=None, issuer=Issuer("NOT-AN-RFC", None, None))

    assert codes([broken]) == ["missing-stamp", "invalid-rfc"]


def test_detects_ppd_with_concrete_payment_form() -> None:
    cfdi = replace(load("income_ppd_40.xml"), payment_form="03")

    assert codes([cfdi]) == ["ppd-payment-form"]


def test_detects_missing_exchange_rate() -> None:
    cfdi = replace(load("expense_ppd_usd_33.xml"), exchange_rate=None)

    assert codes([cfdi]) == ["missing-exchange-rate"]


def test_detects_duplicates() -> None:
    cfdi = load("income_pue_40.xml")

    assert codes([cfdi, cfdi]) == ["duplicate-uuid", "duplicate-uuid"]


def test_issues_frame() -> None:
    frame = issues_frame(validate([replace(load("income_pue_40.xml"), stamp=None)]))

    assert frame.to_dict("records")[0]["code"] == "missing-stamp"
    assert issues_frame([]).empty
