import shutil
from pathlib import Path

import pandas as pd
import pytest

from cfdi_kit import __version__
from cfdi_kit.cli import main
from tests.conftest import FIXTURES, MY_RFC


@pytest.fixture
def clean_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "facturas"
    folder.mkdir()
    for xml in FIXTURES.glob("*.xml"):
        shutil.copy(xml, folder)
    return folder


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["--version"])

    assert __version__ in capsys.readouterr().out


def test_parse_to_excel(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out.xlsx"

    assert main(["parse", str(clean_folder), "-o", str(output), "--rfc", MY_RFC]) == 0

    frame = pd.read_excel(output, sheet_name="invoices")
    assert len(frame) == 8
    assert set(frame["direction"]) == {"issued", "received", "other"}
    assert "loaded 8 CFDI(s)" in capsys.readouterr().err


def test_parse_to_csv(clean_folder: Path, tmp_path: Path) -> None:
    output = tmp_path / "out.csv"

    assert main(["parse", str(clean_folder), "-o", str(output)]) == 0
    assert len(pd.read_csv(output)) == 8


def test_parse_rejects_unknown_output(clean_folder: Path, tmp_path: Path) -> None:
    assert main(["parse", str(clean_folder), "-o", str(tmp_path / "out.json")]) == 1


def test_parse_reports_skipped_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out.csv"

    assert main(["parse", str(FIXTURES), "-o", str(output)]) == 0
    assert "skipped" in capsys.readouterr().err


def test_parse_fails_when_nothing_loads(tmp_path: Path) -> None:
    assert main(["parse", str(tmp_path), "-o", str(tmp_path / "out.csv")]) == 1


def test_summary_prints_a_table(clean_folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["summary", str(clean_folder), "--rfc", MY_RFC]) == 0

    out = capsys.readouterr().out
    assert f"{MY_RFC} · accrual basis · MXN" in out
    assert "2026-01" in out
    assert "30,000.00" in out
    assert "3,573.33" in out


def test_summary_cash_basis_writes_output(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "summary.xlsx"

    assert (
        main(["summary", str(clean_folder), "--rfc", MY_RFC, "--basis", "cash", "-o", str(output)])
        == 0
    )

    assert "cash basis" in capsys.readouterr().out
    assert pd.read_excel(output)["income"].tolist() == pytest.approx([0, 10000, 19500])


def test_summary_notes_unmatched_payments(capsys: pytest.CaptureFixture[str]) -> None:
    path = str(FIXTURES / "payment_10.xml")

    assert main(["summary", path, "--rfc", MY_RFC, "--basis", "cash"]) == 0
    assert "1 payment(s)" in capsys.readouterr().out


def test_summary_without_matching_invoices(clean_folder: Path) -> None:
    assert main(["summary", str(clean_folder), "--rfc", "XAXX010101000"]) == 1


def test_validate_clean_folder(clean_folder: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(clean_folder)]) == 0
    assert "0 error(s), 0 warning(s)" in capsys.readouterr().err


def test_validate_fails_on_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    broken = tmp_path / "broken.xml"
    xml = (FIXTURES / "income_pue_40.xml").read_text(encoding="utf-8")
    broken.write_text(xml.replace('Total="9533.33"', 'Total="9999.99"'), encoding="utf-8")

    assert main(["validate", str(broken)]) == 1
    assert "total-mismatch" in capsys.readouterr().out


def test_validate_fails_on_unreadable_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(FIXTURES / "invalid")]) == 1
