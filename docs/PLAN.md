# cfdi-kit: plan to v1.0

## Goal

Turn a folder (or ZIP) of SAT CFDI invoices into data an accountant or developer can use in one command: a typed Python model, a pandas DataFrame, CSV / Excel workbooks, an income / expense / VAT summary per month and a self-contained HTML report. Everything runs locally; the library makes no network calls.

## Architecture

```
xml / zip ──► loader ──► parser ──► Cfdi (frozen dataclasses, Decimal money)
                                      │
             ┌────────────────────────┼─────────────────────────┐
             ▼                        ▼                         ▼
         validate               export (pandas)            summary (by month)
     (totals, RFC, dupes)    DataFrame / CSV / Excel     accrual or cash basis
                                                                │
                                                                ▼
                                                     report (static HTML, inline SVG)
```

| Module | Responsibility |
|---|---|
| `models` | Frozen dataclasses: `Cfdi`, `Party`, `Concept`, `Tax`, `Payment`, `PaymentDocument`, `Stamp`, `Payroll`. |
| `parser` | Namespace-aware parsing of CFDI 3.3 and 4.0 with the TimbreFiscalDigital 1.1, Pagos 1.0 / 2.0 and Nómina 1.2 complements. |
| `loader` | Reads files, directories (recursive) and ZIP archives; collects per-file errors instead of aborting. |
| `catalogs` | Human-readable labels for the SAT catalogs used in reports (`c_TipoDeComprobante`, `c_FormaPago`, `c_MetodoPago`, `c_UsoCFDI`, `c_RegimenFiscal`, `c_Impuesto`). |
| `validate` | Arithmetic checks (subtotal, discount, taxes, total), RFC format, duplicate UUIDs, missing stamp. |
| `export` | Flat tables: one row per invoice, per line item and per payment; CSV and multi-sheet Excel. |
| `summary` | Monthly income, expenses, VAT charged, VAT creditable, withholdings and net VAT for one RFC, on accrual or cash basis. |
| `report` | One HTML file with no external assets. |
| `cli` | `cfdi-kit parse`, `summary`, `validate`, `report`. |

## Decisions

- **Money is `Decimal`** end to end in the model; DataFrames carry floats only at the export boundary.
- **Stdlib XML parser** (`xml.etree.ElementTree`). It does not fetch external entities, and Python's bundled expat guards against entity-expansion attacks.
- **Dependencies:** `pandas` and `openpyxl` only. The CLI uses `argparse`.
- **Direction** (income vs expense) is relative to an RFC the user passes; without it, the summary is not computed.
- **Cash basis** follows the SAT flow-of-cash rule: a `PUE` invoice counts on its issue date, a `PPD` invoice counts through the Pagos complements that settle it, on the payment date.
- **Credit notes** (`E`) subtract from the side they belong to.

## Scope v1.0

1. Parser for CFDI 3.3 / 4.0 with the complements above.
2. Loader for files, folders and ZIP archives, with per-file error reporting.
3. Export to DataFrame, CSV and Excel (invoices, line items, payments).
4. Monthly summary on accrual and cash basis.
5. Validation report.
6. Static HTML report.
7. CLI for all of the above; tests with synthetic invoices; CI on Linux, macOS and Windows.

## Out of scope

Stamping, issuing or cancelling invoices; downloading from the SAT portal; checking cancellation status with the SAT web service; tax return calculations; any cloud service.

## Milestones (one branch and PR each)

| # | Branch | Content |
|---|---|---|
| M0 | `chore/tooling` | pyproject, CI, plan. |
| M1 | `feat/parser` | Models, parser, catalogs, synthetic fixtures. |
| M2 | `feat/export` | Loader, DataFrame / CSV / Excel export. |
| M3 | `feat/summary` | Accrual and cash-basis monthly summary. |
| M4 | `feat/validate` | Validation checks. |
| M5 | `feat/cli` | CLI. |
| M6 | `feat/report` | HTML report. |
| M7 | `docs/v1` | README (EN / ES), CONTRIBUTING, changelog, version 1.0.0. |

## Test strategy

- Synthetic invoices under `tests/fixtures/` (fake RFCs from the SAT generic list, no real data).
- Unit tests per module; CLI tests through `main(argv)`; Excel and HTML outputs are re-read and asserted.
- `mypy --strict`, `ruff check`, `ruff format --check` in CI.

## Launch checklist

- [ ] CI green on main.
- [ ] README with a real screenshot of the HTML report.
- [ ] `uv build` produces a wheel that installs and runs `cfdi-kit --version`.
- [ ] Tag `v1.0.0` (PyPI publish only with the maintainer's OK).
- [ ] Repository made public (maintainer's OK).
