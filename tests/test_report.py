import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from cfdi_kit.cli import main
from cfdi_kit.export import Direction
from cfdi_kit.models import Cfdi
from cfdi_kit.report import _ceil_to, _nice_step, build_report, open_balances, top_parties
from cfdi_kit.summary import Basis
from tests.conftest import FIXTURES, MY_RFC, load

GENERATED = datetime(2026, 3, 1, 9, 0)


def test_report_is_self_contained(all_valid: list[Cfdi]) -> None:
    html = build_report(all_valid, MY_RFC, generated_at=GENERATED)

    assert html.startswith("<!doctype html>")
    assert not re.search(r"""(src|href)=["']https?://""", html)
    assert "<script" not in html
    assert "generated 2026-03-01 09:00:00" in html


def test_report_contains_every_section(all_valid: list[Cfdi]) -> None:
    html = build_report(all_valid, MY_RFC, Basis.CASH, generated_at=GENERATED)

    for title in (
        "Income and expenses by month",
        "Monthly detail (MXN)",
        "Top clients",
        "Top suppliers",
        "Open PPD balances",
        "Validation (0 issue(s))",
    ):
        assert title in html
    assert "cash basis" in html
    assert html.count('<rect class="bar') == 6


def test_report_escapes_text(all_valid: list[Cfdi]) -> None:
    html = build_report(all_valid, "<b>", generated_at=GENERATED)

    assert "<b>" not in html
    assert "&lt;B&gt;" in html


def test_report_handles_no_matching_invoices(all_valid: list[Cfdi]) -> None:
    html = build_report(all_valid, "XAXX010101000", generated_at=GENERATED)

    assert "Nothing to show." in html


def test_top_parties_ranks_by_net(all_valid: list[Cfdi]) -> None:
    (client,) = top_parties(all_valid, MY_RFC, Direction.ISSUED)

    assert client.rfc == "EKU9003173C9"
    assert client.count == 3
    assert client.net == Decimal("29500.00")


def test_open_balances_lists_partially_paid_ppd(all_valid: list[Cfdi]) -> None:
    (balance,) = open_balances(all_valid, MY_RFC)

    assert balance.uuid == "6F1C2A7E-1B2C-4D3E-9F40-0A1B2C3D4E07"
    assert balance.side is Direction.RECEIVED
    assert balance.remaining == Decimal("145.00")


def test_open_balances_without_payments() -> None:
    (balance,) = open_balances([load("income_ppd_40.xml")], MY_RFC)

    assert balance.paid == Decimal(0)


def test_report_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "report.html"

    assert main(["report", str(FIXTURES), "--rfc", MY_RFC, "-o", str(output)]) == 0

    assert "CFDI report · CACX7605101P8" in output.read_text(encoding="utf-8")
    assert f"wrote {output}" in capsys.readouterr().err


def test_report_command_without_input(tmp_path: Path) -> None:
    assert main(["report", str(tmp_path), "--rfc", MY_RFC, "-o", str(tmp_path / "r.html")]) == 1


@pytest.mark.parametrize(
    ("span", "step"),
    [("95000", "20000"), ("40000", "10000"), ("3", "1"), ("120", "50"), ("1000000", "200000")],
)
def test_nice_step(span: str, step: str) -> None:
    assert _nice_step(Decimal(span)) == Decimal(step)


def test_ceil_to_rounds_up_for_any_sign() -> None:
    assert _ceil_to(Decimal(95000), Decimal(20000)) == Decimal(100000)
    assert _ceil_to(Decimal(500), Decimal(1000)) == Decimal(1000)
    assert _ceil_to(Decimal(0), Decimal(1000)) == Decimal(0)


def test_bars_stay_inside_the_plot(all_valid: list[Cfdi]) -> None:
    html = build_report(all_valid, MY_RFC, generated_at=GENERATED)

    tops = [float(v) for v in re.findall(r'<rect class="bar[^"]*" x="[^"]+" y="([^"]+)"', html)]
    assert min(tops) >= 12
