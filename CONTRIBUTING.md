# Contributing

Thanks for your interest. Issues and pull requests are welcome, in English or Spanish.

## Before you start

- For anything bigger than a small fix, open an issue first so we can agree on the approach.
- Check the open issues to avoid duplicate work.

## Reporting a CFDI that fails

Real-world invoices are the best way to make the parser robust. If a CFDI fails to parse or gives wrong numbers:

1. **Anonymize it first.** Replace RFCs with the SAT test RFCs (`EKU9003173C9`, `CACX7605101P8`), names with fake ones and the UUID with a made-up one. Never paste a real invoice.
2. Keep the structure and the attributes that trigger the problem.
3. Attach it to a bug report with the error output.

## Development setup

```bash
uv sync
```

## Checks

All of these must pass before a pull request is merged (CI runs them too):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

## Pull requests

- One logical change per pull request.
- Add or update tests for every behavior change. New XML fixtures go in `tests/fixtures/` and must be synthetic.
- Update both READMEs if you change user-facing behavior.
- Use [Conventional Commits](https://www.conventionalcommits.org/) in English, for example `feat: parse Carta Porte complement` or `fix: accept lowercase UUIDs in payments`.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
