"""A single self-contained HTML report: no scripts from the internet, no data leaves the file."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from html import escape
from importlib.resources import files
from typing import TYPE_CHECKING

from cfdi_kit import __version__
from cfdi_kit.export import Direction, direction
from cfdi_kit.models import ZERO, InvoiceType
from cfdi_kit.summary import Basis, MonthSummary, Summary, summarize
from cfdi_kit.validate import Issue, validate

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from cfdi_kit.models import Cfdi

TOP_PARTIES = 10


@dataclass(frozen=True, slots=True)
class PartyTotal:
    rfc: str
    name: str
    net: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class OpenBalance:
    uuid: str
    side: Direction
    counterparty: str
    issued_at: datetime
    total: Decimal
    paid: Decimal
    currency: str

    @property
    def remaining(self) -> Decimal:
        return self.total - self.paid


def build_report(
    cfdis: Sequence[Cfdi],
    rfc: str,
    basis: Basis = Basis.ACCRUAL,
    generated_at: datetime | None = None,
) -> str:
    summary = summarize(cfdis, rfc, basis)
    issues = validate(cfdis)
    moment = generated_at or datetime.now().replace(microsecond=0)
    sections = [
        _kpis(summary),
        _section("Income and expenses by month", _bar_chart(summary.months)),
        _section("Monthly detail (MXN)", _month_table(summary)),
        _section("Top clients", _party_table(top_parties(cfdis, summary.rfc, Direction.ISSUED))),
        _section(
            "Top suppliers", _party_table(top_parties(cfdis, summary.rfc, Direction.RECEIVED))
        ),
        _section("Open PPD balances", _balances_table(open_balances(cfdis, summary.rfc))),
        _section(f"Validation ({len(issues)} issue(s))", _issues_table(issues)),
    ]
    return PAGE.format(
        title=escape(f"CFDI report · {summary.rfc}"),
        rfc=escape(summary.rfc),
        basis=escape(summary.basis.value),
        count=len(cfdis),
        generated=escape(moment.isoformat(sep=" ")),
        version=escape(__version__),
        css=files("cfdi_kit").joinpath("report.css").read_text(encoding="utf-8"),
        body="\n".join(sections),
    )


def top_parties(cfdis: Iterable[Cfdi], rfc: str, side: Direction) -> list[PartyTotal]:
    """Counterparties ranked by net amount (MXN) of income and credit-note invoices."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    counts: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for cfdi in cfdis:
        if direction(cfdi, rfc) is not side or cfdi.invoice_type not in (
            InvoiceType.INCOME,
            InvoiceType.EXPENSE,
        ):
            continue
        party = cfdi.receiver if side is Direction.ISSUED else cfdi.issuer
        sign = -1 if cfdi.invoice_type is InvoiceType.EXPENSE else 1
        totals[party.rfc] += sign * (cfdi.subtotal - cfdi.discount) * cfdi.rate_to_mxn
        counts[party.rfc] += 1
        names.setdefault(party.rfc, party.name or "")
    ranked = sorted(totals, key=lambda key: totals[key], reverse=True)[:TOP_PARTIES]
    return [PartyTotal(key, names[key], totals[key], counts[key]) for key in ranked]


def open_balances(cfdis: Sequence[Cfdi], rfc: str) -> list[OpenBalance]:
    """PPD invoices whose loaded payment complements do not cover the total."""
    paid: dict[str, Decimal] = defaultdict(Decimal)
    for cfdi in cfdis:
        for payment in cfdi.payments:
            for document in payment.documents:
                paid[document.uuid] += document.amount_paid
    balances = []
    for cfdi in cfdis:
        side = direction(cfdi, rfc)
        if cfdi.payment_method != "PPD" or side is Direction.OTHER or cfdi.uuid is None:
            continue
        counterparty = cfdi.receiver if side is Direction.ISSUED else cfdi.issuer
        balance = OpenBalance(
            uuid=cfdi.uuid,
            side=side,
            counterparty=counterparty.name or counterparty.rfc,
            issued_at=cfdi.issued_at,
            total=cfdi.total,
            paid=paid.get(cfdi.uuid, ZERO),
            currency=cfdi.currency,
        )
        if balance.remaining > Decimal("0.005"):
            balances.append(balance)
    return sorted(balances, key=lambda b: b.issued_at)


def _money(value: Decimal) -> str:
    return f"{value:,.2f}"


def _section(title: str, content: str) -> str:
    return f"<section><h2>{escape(title)}</h2>\n{content}\n</section>"


def _table(headers: Sequence[str], rows: Iterable[Sequence[str]], numeric_from: int) -> str:
    body = "\n".join(
        "<tr>"
        + "".join(
            f'<td class="num">{cell}</td>' if i >= numeric_from else f"<td>{cell}</td>"
            for i, cell in enumerate(row)
        )
        + "</tr>"
        for row in rows
    )
    head = "".join(
        f'<th class="num">{escape(h)}</th>' if i >= numeric_from else f"<th>{escape(h)}</th>"
        for i, h in enumerate(headers)
    )
    if not body:
        return '<p class="empty">Nothing to show.</p>'
    table = f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    return f'<div class="scroll">{table}</div>'


def _kpis(summary: Summary) -> str:
    income = sum((m.income.net for m in summary.months), ZERO)
    expenses = sum((m.expenses.net for m in summary.months), ZERO)
    charged = sum((m.income.iva for m in summary.months), ZERO)
    creditable = sum((m.expenses.iva for m in summary.months), ZERO)
    net_iva = sum((m.net_iva for m in summary.months), ZERO)
    tiles = [
        ("Income", income),
        ("Expenses", expenses),
        ("VAT charged", charged),
        ("VAT creditable", creditable),
        ("Net VAT", net_iva),
    ]
    period = f"{summary.months[0].month} to {summary.months[-1].month}" if summary.months else "—"
    cells = "".join(
        f'<div class="tile"><div class="tile-label">{escape(name)}</div>'
        f'<div class="tile-value">{_money(value)}</div></div>'
        for name, value in tiles
    )
    heading = f'<p class="period">Period: {escape(period)} · MXN</p>'
    return f'<section>{heading}<div class="tiles">{cells}</div></section>'


def _bar_chart(months: Sequence[MonthSummary]) -> str:
    if not months:
        return '<p class="empty">Nothing to show.</p>'
    values = [(m.month, m.income.net, m.expenses.net) for m in months]
    step = _nice_step(
        max([Decimal(1), *(max(i, e) for _, i, e in values)])
        - min([ZERO, *(min(i, e) for _, i, e in values)])
    )
    top = _ceil_to(max([Decimal(1), *(max(i, e) for _, i, e in values)]), step)
    bottom = -_ceil_to(-min([ZERO, *(min(i, e) for _, i, e in values)]), step)
    width, height, left, pad_top, pad_bottom = 720, 260, 72, 12, 28
    plot_h = height - pad_top - pad_bottom
    group = (width - left) / len(values)
    bar = min(28.0, (group - 12) / 2)

    def y(value: Decimal) -> float:
        return pad_top + float((top - value) / (top - bottom)) * plot_h

    grid = []
    ticks = int((top - bottom) / step)
    for index in range(ticks + 1):
        tick = bottom + step * index
        grid.append(
            f'<line class="grid" x1="{left}" x2="{width}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>'
            f'<text class="axis" x="{left - 8}" y="{y(tick) + 4:.1f}" text-anchor="end">'
            f"{_short(tick)}</text>"
        )
    bars = []
    for index, (month, income, expenses) in enumerate(values):
        center = left + group * index + group / 2
        for offset, value, css, name in (
            (-bar - 1, income, "income", "Income"),
            (1, expenses, "expenses", "Expenses"),
        ):
            y_top, y_base = sorted((y(value), y(ZERO)))
            bars.append(
                f'<rect class="bar {css}" x="{center + offset:.1f}" y="{y_top:.1f}" '
                f'width="{bar:.1f}" height="{max(y_base - y_top, 0.5):.1f}" rx="4">'
                f"<title>{month} · {name}: {_money(value)} MXN</title></rect>"
            )
        bars.append(
            f'<text class="axis" x="{center:.1f}" y="{height - 8}" text-anchor="middle">'
            f"{month}</text>"
        )
    baseline = (
        f'<line class="baseline" x1="{left}" x2="{width}" y1="{y(ZERO):.1f}" y2="{y(ZERO):.1f}"/>'
    )
    legend = (
        '<div class="legend"><span><i class="swatch income"></i>Income</span>'
        '<span><i class="swatch expenses"></i>Expenses</span></div>'
    )
    svg = (
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Income and expenses by month, MXN">'
        f"{''.join(grid)}{baseline}{''.join(bars)}</svg>"
    )
    return legend + svg


def _nice_step(span: Decimal) -> Decimal:
    """A 1, 2 or 5 times power-of-ten step that splits `span` into at most five intervals."""
    raw = span / 5
    magnitude = Decimal(10) ** (len(str(int(raw))) - 1) if raw >= 1 else Decimal(1)
    for factor in (1, 2, 5, 10):
        if raw <= factor * magnitude:
            return factor * magnitude
    return 10 * magnitude


def _ceil_to(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _short(value: Decimal) -> str:
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.0f}k"
    return f"{value:.0f}"


def _month_table(summary: Summary) -> str:
    headers = [
        "Month",
        "Income",
        "VAT charged",
        "VAT withheld",
        "Expenses",
        "VAT creditable",
        "Net VAT",
    ]
    rows = [
        [
            escape(m.month),
            _money(m.income.net),
            _money(m.income.iva),
            _money(m.income.iva_withheld),
            _money(m.expenses.net),
            _money(m.expenses.iva),
            _money(m.net_iva),
        ]
        for m in summary.months
    ]
    return _table(headers, rows, numeric_from=1)


def _party_table(parties: Sequence[PartyTotal]) -> str:
    rows = [[escape(p.rfc), escape(p.name), str(p.count), _money(p.net)] for p in parties]
    return _table(["RFC", "Name", "Invoices", "Net (MXN)"], rows, numeric_from=2)


def _balances_table(balances: Sequence[OpenBalance]) -> str:
    rows = [
        [
            escape(b.uuid),
            escape(b.side.value),
            escape(b.counterparty),
            escape(b.issued_at.date().isoformat()),
            escape(b.currency),
            _money(b.total),
            _money(b.paid),
            _money(b.remaining),
        ]
        for b in balances
    ]
    headers = ["UUID", "Side", "Counterparty", "Issued", "Currency", "Total", "Paid", "Remaining"]
    return _table(headers, rows, numeric_from=5)


def _issues_table(issues: Sequence[Issue]) -> str:
    rows = [
        [
            f'<span class="badge {escape(i.severity.value)}">{escape(i.severity.value)}</span>',
            escape(i.code),
            escape(i.message),
            escape(i.source or ""),
        ]
        for i in issues
    ]
    return _table(["Severity", "Check", "Message", "File"], rows, numeric_from=4)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<main>
<header>
<h1>CFDI report · {rfc}</h1>
<p>{count} CFDI(s) · {basis} basis · generated {generated}</p>
</header>
{body}
<footer>Generated locally by cfdi-kit {version}. An estimate to review a period; it does not replace
a tax return or an accountant's advice. Cancellation status with the SAT is not checked.</footer>
</main>
</body>
</html>
"""
