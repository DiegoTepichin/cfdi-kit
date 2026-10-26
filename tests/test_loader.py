import shutil
import zipfile
from pathlib import Path

from cfdi_kit.loader import load
from tests.conftest import FIXTURES

VALID_COUNT = len(list(FIXTURES.glob("*.xml")))


def test_loads_a_folder_recursively_and_reports_bad_files() -> None:
    result = load([FIXTURES])

    assert len(result.cfdis) == VALID_COUNT
    assert {Path(e.source).name for e in result.errors} == {
        "truncated.xml",
        "not_a_cfdi.xml",
        "cfdi_32.xml",
    }
    assert result.duplicates == ()


def test_error_messages_do_not_repeat_the_source() -> None:
    result = load([FIXTURES / "invalid" / "cfdi_32.xml"])

    assert result.errors[0].message == "unsupported CFDI version '3.2'"


def test_skips_duplicate_uuids(tmp_path: Path) -> None:
    original = FIXTURES / "income_pue_40.xml"
    shutil.copy(original, tmp_path / "a.xml")
    shutil.copy(original, tmp_path / "b.xml")

    result = load([tmp_path])

    assert len(result.cfdis) == 1
    assert result.duplicates == (str(tmp_path / "b.xml"),)


def test_keeps_duplicates_when_asked(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / "income_pue_40.xml", tmp_path / "a.xml")
    shutil.copy(FIXTURES / "income_pue_40.xml", tmp_path / "b.xml")

    assert len(load([tmp_path], deduplicate=False).cfdis) == 2


def test_reads_xml_inside_zip_archives(tmp_path: Path) -> None:
    archive = tmp_path / "descarga.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(FIXTURES / "income_pue_40.xml", "2026/ene/factura.XML")
        zf.writestr("readme.txt", "ignored")

    result = load([archive])

    assert len(result.cfdis) == 1
    assert result.cfdis[0].source == f"{archive}!2026/ene/factura.XML"
    assert result.errors == ()


def test_reports_corrupt_zip(tmp_path: Path) -> None:
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"not a zip")

    assert load([archive]).errors[0].message == "not a valid ZIP archive"


def test_reports_missing_paths_and_wrong_extensions(tmp_path: Path) -> None:
    other = tmp_path / "notes.txt"
    other.write_text("hi")

    messages = [e.message for e in load([tmp_path / "missing", other]).errors]

    assert messages == ["no such file or directory", "not an .xml or .zip file"]


def test_ignores_non_xml_files_inside_folders(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hi")

    assert load([tmp_path]).errors == ()
