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


RISK_LIST = FIXTURES / "risk" / "listado_69b.csv"


def test_risk_flags_suppliers_on_the_list(
    clean_folder: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["risk", str(clean_folder), "--list", str(RISK_LIST), "--rfc", MY_RFC])

    captured = capsys.readouterr()
    assert code == 1
    lines = captured.out.splitlines()
    assert lines
    assert all(line.startswith("Definitivo") and "EKU9003173C9" in line for line in lines)
    assert "list dated 2025-12-31" in captured.err
    assert "not an accusation" in captured.err


def test_risk_passes_when_no_supplier_is_listed(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = tmp_path / "other.csv"
    other.write_text(
        "No,RFC,Nombre del Contribuyente,Situación del contribuyente\n"
        "1,ZZZ010101ZZ1,NOBODY,Definitivo\n",
        encoding="utf-8",
    )

    assert main(["risk", str(clean_folder), "--list", str(other)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "0 match(es)" in captured.err


def test_risk_with_only_cleared_matches_is_not_a_failure(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cleared = tmp_path / "cleared.csv"
    cleared.write_text(
        "No,RFC,Nombre del Contribuyente,Situación del contribuyente\n"
        "1,EKU9003173C9,ESCUELA KEMPER URGATE,Desvirtuado\n",
        encoding="utf-8",
    )

    assert main(["risk", str(clean_folder), "--list", str(cleared)]) == 0

    assert "Desvirtuado" in capsys.readouterr().out


def test_risk_explains_a_missing_list(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.csv"

    assert main(["risk", str(clean_folder), "--list", str(missing)]) == 1

    assert f"cannot read {missing}" in capsys.readouterr().err


def test_risk_explains_a_file_that_is_not_the_list(
    clean_folder: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    wrong = tmp_path / "wrong.csv"
    wrong.write_text("a,b\n1,2\n", encoding="utf-8")

    assert main(["risk", str(clean_folder), "--list", str(wrong)]) == 1

    assert "no header row" in capsys.readouterr().err


def test_report_with_a_risk_list(clean_folder: Path, tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    args = ["report", str(clean_folder), "--rfc", MY_RFC, "-o", str(output)]

    code = main([*args, "--risk-list", str(RISK_LIST)])

    assert code == 0
    assert "Supplier risk, SAT 69-B" in output.read_text(encoding="utf-8")


def test_report_stops_on_an_unreadable_risk_list(clean_folder: Path, tmp_path: Path) -> None:
    output = tmp_path / "report.html"

    args = ["report", str(clean_folder), "--rfc", MY_RFC, "-o", str(output)]

    code = main([*args, "--risk-list", str(tmp_path / "missing.csv")])

    assert code == 1
    assert not output.exists()
