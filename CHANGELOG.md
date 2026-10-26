# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-26

First public release.

### Added

- Parser for CFDI 4.0 and 3.3 with the Timbre Fiscal Digital 1.1, Pagos 1.0 / 2.0 and Nómina 1.2 complements, into frozen dataclasses with `Decimal` money.
- Loader for files, folders and ZIP archives, with per-file error reporting and UUID de-duplication.
- Export to pandas DataFrames, CSV and a three-sheet Excel workbook.
- Monthly income / expense / VAT summary on accrual or cash basis.
- Consistency checks: totals, tax breakdowns, RFCs, stamps, PPD payment form, exchange rate, duplicates.
- Self-contained HTML report.
- `cfdi-kit` CLI with `parse`, `summary`, `validate` and `report`.
- Synthetic demo generator and a year of demo invoices.

[1.0.0]: https://github.com/DiegoTepichin/cfdi-kit/releases/tag/v1.0.0
