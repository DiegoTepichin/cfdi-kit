from datetime import date
from pathlib import Path

import pytest

from cfdi_kit.risk import (
    Listing,
    ListingStatus,
    SnapshotError,
    load_snapshot,
    parse_snapshot,
    worst,
)
from tests.conftest import FIXTURES

LIST_FILE = FIXTURES / "risk" / "listado_69b.csv"
HEADER = "No,RFC,Nombre del Contribuyente,Situación del contribuyente\n"


def test_reads_the_cp1252_list_with_its_date() -> None:
    snapshot = load_snapshot(LIST_FILE)

    assert snapshot.as_of == date(2025, 12, 31)
    assert len(snapshot.listings) == 5
    assert snapshot.find("EKU9003173C9") == (
        Listing("EKU9003173C9", "ESCUELA KEMPER URGATE", ListingStatus.DEFINITIVE),
    )


def test_keeps_accents_and_enye() -> None:
    (listing,) = load_snapshot(LIST_FILE).find("OÑO120726RX3")

    assert listing.name == "ORGÁNICOS ÑAVEZ OSORIO"


def test_reads_utf8_with_a_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "list.csv"
    path.write_bytes(("﻿" + HEADER + "1,KIJ0906199R1,KERNEL,Presunto\n").encode())

    assert load_snapshot(path).find("KIJ0906199R1")[0].status is ListingStatus.PRESUMED


def test_lookup_ignores_case_and_spaces() -> None:
    assert load_snapshot(LIST_FILE).find(" eku9003173c9 ")


def test_unlisted_rfc_has_no_entries() -> None:
    assert load_snapshot(LIST_FILE).find("CACX7605101P8") == ()


def test_date_is_optional() -> None:
    assert parse_snapshot(HEADER + "1,KIJ0906199R1,KERNEL,Presunto\n").as_of is None


def test_keeps_every_row_of_a_repeated_rfc() -> None:
    text = HEADER + "1,AAA010101AAA,ONE,Definitivo\n2,AAA010101AAA,ONE,Sentencia Favorable\n"

    entries = parse_snapshot(text).find("AAA010101AAA")

    assert [e.status for e in entries] == [ListingStatus.DEFINITIVE, ListingStatus.FAVORABLE_RULING]


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([ListingStatus.FAVORABLE_RULING, ListingStatus.DEFINITIVE], ListingStatus.DEFINITIVE),
        ([ListingStatus.DEFINITIVE, ListingStatus.FAVORABLE_RULING], ListingStatus.DEFINITIVE),
        ([ListingStatus.CLEARED, ListingStatus.PRESUMED], ListingStatus.PRESUMED),
        ([ListingStatus.FAVORABLE_RULING, ListingStatus.CLEARED], ListingStatus.CLEARED),
    ],
)
def test_a_later_row_never_clears_an_earlier_one(
    statuses: list[ListingStatus], expected: ListingStatus
) -> None:
    entries = tuple(Listing("AAA010101AAA", "ONE", status) for status in statuses)

    assert worst(entries).status is expected


def test_only_presumed_and_definitive_are_alerts() -> None:
    alerts = {status for status in ListingStatus if status.is_alert}

    assert alerts == {ListingStatus.PRESUMED, ListingStatus.DEFINITIVE}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("nothing useful here\n", "no header"),
        ("No,RFC,Nombre del Contribuyente\n1,AAA010101AAA,ONE\n", "Situación"),
        (HEADER + "1,AAA010101AAA,ONE,Culpable\n", "line 2: unknown taxpayer status"),
    ],
)
def test_rejects_files_that_are_not_the_list(text: str, message: str) -> None:
    with pytest.raises(SnapshotError, match=message):
        parse_snapshot(text)
