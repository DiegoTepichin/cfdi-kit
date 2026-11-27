"""Load many CFDIs from files, folders and ZIP archives without stopping at the first bad file."""

from __future__ import annotations

import lzma
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from cfdi_kit.parser import CfdiParseError, parse_bytes

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from cfdi_kit.models import Cfdi

MAX_XML_BYTES = 20 * 1024 * 1024
TOO_LARGE = "larger than 20 MiB, skipped"
ZIP_MEMBER_ERRORS = (
    EOFError,
    NotImplementedError,
    OSError,
    RuntimeError,
    lzma.LZMAError,
    zipfile.BadZipFile,
    zlib.error,
)


@dataclass(frozen=True, slots=True)
class LoadError:
    source: str
    message: str


@dataclass(frozen=True, slots=True)
class LoadResult:
    cfdis: tuple[Cfdi, ...]
    errors: tuple[LoadError, ...]
    duplicates: tuple[str, ...]
    """Sources skipped because a CFDI with the same UUID was already loaded."""


def load(paths: Iterable[str | Path], *, deduplicate: bool = True) -> LoadResult:
    """Parse every `.xml` in the given files, folders (recursively) and `.zip` archives."""
    cfdis: list[Cfdi] = []
    errors: list[LoadError] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for source, data in _documents(paths, errors):
        try:
            cfdi = parse_bytes(data, source=source)
        except CfdiParseError as exc:
            errors.append(LoadError(source, str(exc).removeprefix(f"{source}: ")))
            continue
        if deduplicate and cfdi.uuid is not None:
            if cfdi.uuid in seen:
                duplicates.append(source)
                continue
            seen.add(cfdi.uuid)
        cfdis.append(cfdi)
    return LoadResult(tuple(cfdis), tuple(errors), tuple(duplicates))


def _documents(paths: Iterable[str | Path], errors: list[LoadError]) -> Iterator[tuple[str, bytes]]:
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            for file in sorted(p for p in path.rglob("*") if p.is_file()):
                yield from _file_documents(file, errors, explicit=False)
        elif path.is_file():
            yield from _file_documents(path, errors, explicit=True)
        else:
            errors.append(LoadError(str(path), "no such file or directory"))


def _file_documents(
    path: Path, errors: list[LoadError], *, explicit: bool
) -> Iterator[tuple[str, bytes]]:
    suffix = path.suffix.lower()
    if suffix == ".xml":
        yield from _xml_document(path, errors)
    elif suffix == ".zip":
        yield from _zip_documents(path, errors)
    elif explicit:
        errors.append(LoadError(str(path), "not an .xml or .zip file"))


def _xml_document(path: Path, errors: list[LoadError]) -> Iterator[tuple[str, bytes]]:
    try:
        if path.stat().st_size > MAX_XML_BYTES:
            errors.append(LoadError(str(path), TOO_LARGE))
            return
        data = path.read_bytes()
    except OSError as exc:
        errors.append(LoadError(str(path), f"cannot read file ({exc.strerror})"))
        return
    yield str(path), data


def _zip_documents(path: Path, errors: list[LoadError]) -> Iterator[tuple[str, bytes]]:
    try:
        archive = zipfile.ZipFile(path)
    except (NotImplementedError, UnicodeDecodeError, zipfile.BadZipFile):
        errors.append(LoadError(str(path), "not a valid ZIP archive"))
        return
    except OSError as exc:
        errors.append(LoadError(str(path), f"cannot read file ({exc.strerror})"))
        return
    with archive:
        for member in sorted(archive.infolist(), key=lambda m: m.filename):
            if member.is_dir() or not member.filename.lower().endswith(".xml"):
                continue
            source = f"{path}!{member.filename}"
            if member.file_size > MAX_XML_BYTES:
                errors.append(LoadError(source, TOO_LARGE))
                continue
            try:
                data = archive.read(member)
            except ZIP_MEMBER_ERRORS as exc:
                errors.append(LoadError(source, f"cannot read ZIP member ({exc})"))
                continue
            yield source, data
