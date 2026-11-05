"""`cfdi-kit` command line."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cfdi_kit import __version__
from cfdi_kit.export import to_csv, to_excel
from cfdi_kit.loader import LoadResult, load
from cfdi_kit.report import build_report
from cfdi_kit.risk import Match, Snapshot, SnapshotError, find_matches, load_snapshot
from cfdi_kit.summary import Basis, Summary, summarize, summary_frame
from cfdi_kit.validate import Severity, validate

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    import pandas as pd

EXIT_OK = 0
EXIT_FAILURE = 1
RISK_LIST_HELP = "local copy of the SAT's Listado_completo_69-B.csv (see the README to download it)"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    return handler(args)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfdi-kit",
        description="Read SAT CFDI invoices locally: export, summarize and validate them.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(required=True, metavar="COMMAND")

    parse = commands.add_parser("parse", help="export invoices to Excel or CSV")
    _add_inputs(parse)
    parse.add_argument("-o", "--output", type=Path, required=True, help="output .xlsx or .csv")
    parse.add_argument("--rfc", help="your RFC, to label each invoice as issued or received")
    parse.set_defaults(handler=_parse)

    summary = commands.add_parser("summary", help="monthly income, expenses and VAT for an RFC")
    _add_inputs(summary)
    summary.add_argument("--rfc", required=True, help="the RFC to summarize")
    summary.add_argument(
        "--basis",
        choices=[b.value for b in Basis],
        default=Basis.ACCRUAL.value,
        help="accrual: by issue date (default); cash: PPD invoices on their payment date",
    )
    summary.add_argument("-o", "--output", type=Path, help="also write the table to .xlsx or .csv")
    summary.set_defaults(handler=_summary)

    check = commands.add_parser("validate", help="check totals, taxes, RFCs and duplicates")
    _add_inputs(check)
    check.set_defaults(handler=_validate)

    report = commands.add_parser("report", help="write a self-contained HTML report for an RFC")
    _add_inputs(report)
    report.add_argument("--rfc", required=True, help="the RFC to report on")
    report.add_argument("--basis", choices=[b.value for b in Basis], default=Basis.ACCRUAL.value)
    report.add_argument("-o", "--output", type=Path, default=Path("cfdi-report.html"))
    report.add_argument("--risk-list", type=Path, metavar="CSV", help=RISK_LIST_HELP)
    report.set_defaults(handler=_report)

    risk = commands.add_parser("risk", help="flag suppliers that appear on the SAT 69-B list")
    _add_inputs(risk)
    risk.add_argument("--list", type=Path, required=True, metavar="CSV", help=RISK_LIST_HELP)
    risk.add_argument("--rfc", help="your RFC: only invoices you received are checked")
    risk.set_defaults(handler=_risk)
    return parser


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("paths", nargs="+", type=Path, help="XML files, folders or ZIP archives")
    parser.add_argument("--keep-duplicates", action="store_true", help="do not skip repeated UUIDs")


def load_inputs(args: argparse.Namespace) -> LoadResult:
    result = load(args.paths, deduplicate=not args.keep_duplicates)
    for error in result.errors:
        print(f"skipped {error.source}: {error.message}", file=sys.stderr)
    if result.duplicates:
        print(f"skipped {len(result.duplicates)} duplicate UUID(s)", file=sys.stderr)
    print(f"loaded {len(result.cfdis)} CFDI(s)", file=sys.stderr)
    return result


def _parse(args: argparse.Namespace) -> int:
    result = load_inputs(args)
    if not result.cfdis:
        return EXIT_FAILURE
    output: Path = args.output
    if output.suffix.lower() == ".csv":
        to_csv(result.cfdis, output, args.rfc)
    elif output.suffix.lower() == ".xlsx":
        to_excel(result.cfdis, output, args.rfc)
    else:
        print("output must end in .xlsx or .csv", file=sys.stderr)
        return EXIT_FAILURE
    print(f"wrote {output}", file=sys.stderr)
    return EXIT_OK


def _summary(args: argparse.Namespace) -> int:
    result = load_inputs(args)
    summary = summarize(result.cfdis, args.rfc, Basis(args.basis))
    if not summary.months:
        print(f"no invoices issued to or by {summary.rfc}", file=sys.stderr)
        return EXIT_FAILURE
    frame = summary_frame(summary)
    print(render_summary(summary, frame))
    output: Path | None = args.output
    if output is not None:
        if output.suffix.lower() == ".xlsx":
            frame.to_excel(output, index=False, sheet_name="summary")
        else:
            frame.to_csv(output, index=False)
        print(f"wrote {output}", file=sys.stderr)
    return EXIT_OK


TERMINAL_COLUMNS = {
    "month": "Month",
    "income": "Income",
    "iva_charged": "VAT charged",
    "iva_withheld_by_clients": "VAT withheld",
    "expenses": "Expenses",
    "iva_creditable": "VAT creditable",
    "net_iva": "Net VAT",
}


def render_summary(summary: Summary, frame: pd.DataFrame) -> str:
    header = f"{summary.rfc} · {summary.basis.value} basis · MXN"
    rows = [list(TERMINAL_COLUMNS.values())]
    for record in frame.to_dict("records"):
        rows.append(
            [
                str(value) if column == "month" else f"{float(value):,.2f}"
                for column, value in ((c, record[c]) for c in TERMINAL_COLUMNS)
            ]
        )
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = [header, ""]
    for index, row in enumerate(rows):
        lines.append("  ".join(cell.rjust(width) for cell, width in zip(row, widths, strict=True)))
        if index == 0:
            lines.append("  ".join("-" * width for width in widths))
    if summary.unmatched_payments:
        lines.append("")
        lines.append(
            f"note: {len(summary.unmatched_payments)} payment(s) settle invoices that were not "
            "loaded and have no tax breakdown; their full amount was counted as net."
        )
    return "\n".join(lines)


def _validate(args: argparse.Namespace) -> int:
    result = load_inputs(args)
    issues = validate(result.cfdis)
    for issue in issues:
        print(f"{issue.severity.value:7}  {issue.code:28}  {issue.source}  {issue.message}")
    errors = sum(1 for i in issues if i.severity is Severity.ERROR)
    warnings = len(issues) - errors
    print(f"{errors} error(s), {warnings} warning(s)", file=sys.stderr)
    return EXIT_FAILURE if errors or result.errors else EXIT_OK


def _read_snapshot(path: Path) -> Snapshot | None:
    try:
        return load_snapshot(path)
    except (OSError, SnapshotError) as error:
        print(f"cannot read {path}: {error}", file=sys.stderr)
        return None


def _risk(args: argparse.Namespace) -> int:
    snapshot = _read_snapshot(args.list)
    if snapshot is None:
        return EXIT_FAILURE
    result = load_inputs(args)
    matches = find_matches(result.cfdis, snapshot, args.rfc)
    for match in matches:
        print(render_match(match))
    alerts = sum(1 for match in matches if match.status.is_alert)
    dated = f"dated {snapshot.as_of.isoformat()}" if snapshot.as_of else "of unknown date"
    print(
        f"{len(matches)} match(es) against the 69-B list {dated}, {alerts} presumed or definitive",
        file=sys.stderr,
    )
    print(
        "a match is a coincidence with a public list, not an accusation; ask your accountant",
        file=sys.stderr,
    )
    return EXIT_FAILURE if alerts or result.errors else EXIT_OK


def render_match(match: Match) -> str:
    issued = match.issued_at.date().isoformat()
    return (
        f"{match.status.value:19}  {match.issuer_rfc:13}  {issued}  {match.uuid or '-':36}  "
        f"{match.total:>12,.2f} {match.currency}  {match.issuer_name or ''}"
    )


def _report(args: argparse.Namespace) -> int:
    snapshot = None
    if args.risk_list is not None:
        snapshot = _read_snapshot(args.risk_list)
        if snapshot is None:
            return EXIT_FAILURE
    result = load_inputs(args)
    if not result.cfdis:
        return EXIT_FAILURE
    output: Path = args.output
    output.write_text(
        build_report(result.cfdis, args.rfc, Basis(args.basis), risk=snapshot), encoding="utf-8"
    )
    print(f"wrote {output}", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
