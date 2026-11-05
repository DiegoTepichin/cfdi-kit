from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from cfdi_kit.loader import load as load_folder
from cfdi_kit.models import Cfdi
from cfdi_kit.risk import (
    Listing,
    ListingStatus,
    SnapshotError,
    find_matches,
    load_snapshot,
    parse_snapshot,
    worst,
)
from tests.conftest import FIXTURES, MY_RFC, load

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


def _issued_by(cfdi: Cfdi, rfc: str) -> Cfdi:
    return replace(cfdi, issuer=replace(cfdi.issuer, rfc=rfc, name="SYNTHETIC SUPPLIER"))


@pytest.mark.parametrize(
    ("issuer", "status"),
    [
        ("EKU9003173C9", ListingStatus.DEFINITIVE),
        ("KIJ0906199R1", ListingStatus.PRESUMED),
        ("MAG041126GT8", ListingStatus.CLEARED),
        ("XIA190128J61", ListingStatus.FAVORABLE_RULING),
    ],
)
def test_matches_an_invoice_for_each_status(issuer: str, status: ListingStatus) -> None:
    cfdi = _issued_by(load("expense_pue_40.xml"), issuer)

    (match,) = find_matches([cfdi], load_snapshot(LIST_FILE))

    assert match.status is status
    assert match.issuer_rfc == issuer
    assert match.uuid == cfdi.uuid
    assert match.total == cfdi.total


def test_unlisted_issuers_do_not_match(all_valid: list[Cfdi]) -> None:
    unlisted = [_issued_by(cfdi, "CACX7605101P8") for cfdi in all_valid]

    assert find_matches(unlisted, load_snapshot(LIST_FILE)) == []


def test_lists_the_most_serious_first() -> None:
    base = load("expense_pue_40.xml")
    cfdis = [
        _issued_by(base, "MAG041126GT8"),
        _issued_by(base, "KIJ0906199R1"),
        _issued_by(base, "EKU9003173C9"),
    ]

    statuses = [m.status for m in find_matches(cfdis, load_snapshot(LIST_FILE))]

    assert statuses == [ListingStatus.DEFINITIVE, ListingStatus.PRESUMED, ListingStatus.CLEARED]


def test_with_an_rfc_only_received_invoices_are_checked() -> None:
    received = _issued_by(load("expense_pue_40.xml"), "EKU9003173C9")
    issued_by_me = replace(received, issuer=replace(received.issuer, rfc=MY_RFC))
    issued_by_listed_to_other = replace(
        received, receiver=replace(received.receiver, rfc="CACX7605101P8")
    )
    snapshot = load_snapshot(LIST_FILE)

    assert len(find_matches([received], snapshot, MY_RFC)) == 1
    assert find_matches([issued_by_me], snapshot, MY_RFC) == []
    assert find_matches([issued_by_listed_to_other], snapshot, "XAXX010101000") == []
    assert len(find_matches([issued_by_listed_to_other], snapshot)) == 1


def test_a_repeated_rfc_is_judged_by_its_worst_entry() -> None:
    snapshot = parse_snapshot(
        HEADER + "1,EKU9003173C9,ONE,Definitivo\n2,EKU9003173C9,ONE,Sentencia Favorable\n"
    )

    (match,) = find_matches([load("expense_pue_40.xml")], snapshot)

    assert match.status is ListingStatus.DEFINITIVE
    assert len(match.listings) == 2


def test_the_demo_list_covers_every_status_in_the_demo_invoices() -> None:
    examples = Path(__file__).parents[1] / "examples"
    snapshot = load_snapshot(examples / "demo-69b.csv")

    matches = find_matches(load_folder([examples / "demo"]).cfdis, snapshot, MY_RFC)

    assert {match.status for match in matches} == set(ListingStatus)
