"""Cross-check invoice issuers against a local snapshot of the SAT's article 69-B list.

The SAT publishes the list of taxpayers it presumes issue invoices for non-existent operations
(EFOS). This module reads a copy of that file you downloaded yourself; it never goes online and no
invoice leaves your machine. A match is a coincidence with a public list, not an accusation: the
list changes, and a taxpayer can be cleared.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
AS_OF_PATTERN = re.compile(r"actualizada al (\d{1,2}) de ([a-záéíóú]+) de (\d{4})", re.IGNORECASE)
RFC_COLUMN = "RFC"
NAME_COLUMN = "Nombre del Contribuyente"
STATUS_COLUMN = "Situación del contribuyente"


class SnapshotError(ValueError):
    """The file is not a 69-B list this module understands."""


class ListingStatus(StrEnum):
    """`Situación del contribuyente`, as the SAT writes it."""

    PRESUMED = "Presunto"
    DEFINITIVE = "Definitivo"
    CLEARED = "Desvirtuado"
    FAVORABLE_RULING = "Sentencia Favorable"

    @property
    def is_alert(self) -> bool:
        """Presumed and definitive taxpayers are the ones whose invoices carry risk."""
        return self in (ListingStatus.PRESUMED, ListingStatus.DEFINITIVE)

    @property
    def gravity(self) -> int:
        """Higher is worse: definitive, presumed, cleared, then favorable ruling."""
        return GRAVITY.index(self)


GRAVITY = (
    ListingStatus.FAVORABLE_RULING,
    ListingStatus.CLEARED,
    ListingStatus.PRESUMED,
    ListingStatus.DEFINITIVE,
)


@dataclass(frozen=True, slots=True)
class Listing:
    rfc: str
    name: str
    status: ListingStatus


def worst(listings: tuple[Listing, ...]) -> Listing:
    """The most serious entry; rows are not chronological, so a later row never clears one."""
    return max(listings, key=lambda listing: listing.status.gravity)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """A copy of the list and the date the SAT says it was current.

    An RFC can appear in several rows (separate proceedings), so each maps to all its entries.
    """

    as_of: date | None
    listings: Mapping[str, tuple[Listing, ...]]

    def find(self, rfc: str) -> tuple[Listing, ...]:
        return self.listings.get(rfc.strip().upper(), ())


def load_snapshot(path: Path) -> Snapshot:
    """Read the SAT's `Listado_completo_69-B.csv`, which is not UTF-8."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    return parse_snapshot(text)


def parse_snapshot(text: str) -> Snapshot:
    rows = list(csv.reader(io.StringIO(text, newline="")))
    header_index = next((i for i, row in enumerate(rows) if RFC_COLUMN in _clean(row)), None)
    if header_index is None:
        raise SnapshotError(f"no header row with a {RFC_COLUMN!r} column was found")
    header = _clean(rows[header_index])
    columns = {name: _column(header, name) for name in (RFC_COLUMN, NAME_COLUMN, STATUS_COLUMN)}
    listings: dict[str, list[Listing]] = {}
    for line, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(cell.strip() for cell in row):
            continue
        listing = _listing(row, columns, line)
        listings.setdefault(listing.rfc, []).append(listing)
    return Snapshot(
        as_of=_as_of(rows[:header_index]),
        listings={rfc: tuple(entries) for rfc, entries in listings.items()},
    )


def _clean(row: list[str]) -> list[str]:
    return [cell.strip() for cell in row]


def _column(header: list[str], name: str) -> int:
    try:
        return header.index(name)
    except ValueError:
        raise SnapshotError(f"the header has no {name!r} column") from None


def _listing(row: list[str], columns: Mapping[str, int], line: int) -> Listing:
    cells = _clean(row)
    try:
        status = ListingStatus(cells[columns[STATUS_COLUMN]])
    except (ValueError, IndexError):
        raise SnapshotError(f"line {line}: unknown taxpayer status") from None
    rfc = cells[columns[RFC_COLUMN]].upper()
    return Listing(rfc=rfc, name=cells[columns[NAME_COLUMN]], status=status)


def _as_of(preamble: list[list[str]]) -> date | None:
    for row in preamble:
        for cell in row:
            match = AS_OF_PATTERN.search(cell)
            if match is None:
                continue
            day, month, year = match.groups()
            if month.lower() in MONTHS:
                return date(int(year), MONTHS.index(month.lower()) + 1, int(day))
    return None
