@../briefs/cfdi-kit.md

# cfdi-kit

## What it is

A Python library, CLI and local interface that parses CFDI invoices (SAT XML) into dataframes, Excel or an income / expense / VAT dashboard. Everything runs locally; no data leaves the user's machine.

## Who it is for

Accountants, freelancers and fintech developers in Mexico.

## Scope

v1.0 scope and out-of-scope list live in `docs/PLAN.md`. Ideas beyond it go to GitHub issues.

## Code standards

- Python 3.11+ (CI matrix: 3.11, 3.12, 3.13, 3.14). Dependencies and environments managed with `uv`.
- Strict typing: `mypy --strict` clean, no untyped public functions, no `Any` without a reason.
- Lint and format with `ruff`.
- Tests with `pytest`. No network calls in tests: use recorded or fixture data.
- Small functions, clear names, no dead code, no comments that restate the code.
- Configuration and secrets only through environment variables, documented in `.env.example`.
- Conventional Commits in English, one logical change per commit.
- README and docs describe only what exists and has been run.

## Commands

- `uv sync`: install the project and dev dependencies.
- `uv run ruff check .` / `uv run ruff format --check .` / `uv run mypy .` / `uv run pytest`: the CI checks.
- `uv run cfdi-kit parse|summary|validate|report PATHS ...`: the CLI (see README).
- `uv run python examples/generate_demo.py examples/demo`: regenerate the synthetic demo invoices.
- `uv build`: build the sdist and wheel.

## Structure

- `src/cfdi_kit/`: `models`, `parser`, `loader`, `catalogs`, `export`, `summary`, `validate`, `report` (+ `report.css`), `cli`.
- `tests/`: one test module per source module; synthetic XML in `tests/fixtures/`.
- `examples/`: demo generator and generated demo invoices.
- `docs/`: `PLAN.md` and the README screenshot.
