from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
from typing import BinaryIO, Iterator
import zlib

import ijson
from ijson.common import JSONError

from app.core.hashing import canonical_json
from app.instruments.provider_catalogue import CatalogueArtifactError, CatalogueParseError


MAX_COMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_ROWS = 1_000_000
MAX_CANONICAL_ROW_BYTES = 64 * 1024
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ParsedCatalogueArtifact:
    decompressed_path: Path
    compressed_sha256: str
    decompressed_sha256: str
    compressed_byte_count: int
    decompressed_byte_count: int


@dataclass(frozen=True)
class ParsedCatalogueRow:
    physical_row_number: int
    raw: dict[str, object]
    raw_row_hash: str


class CatalogueArtifactScratch:
    def __init__(self, artifact: ParsedCatalogueArtifact) -> None:
        self.artifact = artifact

    def __enter__(self) -> ParsedCatalogueArtifact:
        return self.artifact

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.artifact.decompressed_path.unlink(missing_ok=True)


def validate_gzip_json_array(path: Path) -> CatalogueArtifactScratch:
    if path.is_symlink():
        raise CatalogueArtifactError("catalogue artifact path must not be a symlink")
    if not path.is_file():
        raise CatalogueArtifactError("catalogue artifact path must be a regular file")
    compressed_hash = hashlib.sha256()
    decompressed_hash = hashlib.sha256()
    compressed_count = 0
    decompressed_count = 0
    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    temporary = tempfile.NamedTemporaryFile(prefix="quantkynd-catalogue-", suffix=".json", delete=False)
    temporary_path = Path(temporary.name)
    try:
        with path.open("rb") as source, temporary:
            while chunk := source.read(CHUNK_SIZE):
                compressed_count += len(chunk)
                if compressed_count > MAX_COMPRESSED_BYTES:
                    raise CatalogueArtifactError("compressed catalogue artifact exceeds limit")
                compressed_hash.update(chunk)
                data = decompressor.decompress(chunk)
                if data:
                    decompressed_count += len(data)
                    if decompressed_count > MAX_DECOMPRESSED_BYTES:
                        raise CatalogueArtifactError("decompressed catalogue artifact exceeds limit")
                    decompressed_hash.update(data)
                    temporary.write(data)
                if decompressor.unused_data:
                    raise CatalogueArtifactError("catalogue gzip must contain exactly one member")
            tail = decompressor.flush()
            if tail:
                decompressed_count += len(tail)
                if decompressed_count > MAX_DECOMPRESSED_BYTES:
                    raise CatalogueArtifactError("decompressed catalogue artifact exceeds limit")
                decompressed_hash.update(tail)
                temporary.write(tail)
            if not decompressor.eof:
                raise CatalogueArtifactError("catalogue gzip member is incomplete")
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return CatalogueArtifactScratch(
        ParsedCatalogueArtifact(
            decompressed_path=temporary_path,
            compressed_sha256="sha256:" + compressed_hash.hexdigest(),
            decompressed_sha256="sha256:" + decompressed_hash.hexdigest(),
            compressed_byte_count=compressed_count,
            decompressed_byte_count=decompressed_count,
        )
    )


def parse_json_array_rows(path: Path) -> Iterator[ParsedCatalogueRow]:
    with path.open("rb") as stream:
        first = stream.read(3)
        if first == b"\xef\xbb\xbf":
            raise CatalogueParseError("catalogue JSON must be UTF-8 without BOM")
        stream.seek(0)
        try:
            yield from _parse_stream(stream)
        except JSONError as exc:
            raise CatalogueParseError("catalogue JSON is malformed") from exc
        except UnicodeDecodeError as exc:
            raise CatalogueParseError("catalogue JSON must be valid UTF-8") from exc


def _parse_stream(stream: BinaryIO) -> Iterator[ParsedCatalogueRow]:
    parser = ijson.parse(stream, use_float=False)
    try:
        prefix, event, value = next(parser)
    except StopIteration as exc:
        raise CatalogueParseError("catalogue JSON must contain one top-level array") from exc
    if (prefix, event) != ("", "start_array"):
        raise CatalogueParseError("catalogue JSON must contain one top-level array")
    row_number = 0
    for prefix, event, value in parser:
        if prefix == "item" and event == "start_map":
            row_number += 1
            if row_number > MAX_ROWS:
                raise CatalogueParseError("catalogue row count exceeds limit")
            row = _read_map(parser)
            row_hash = _row_hash(row)
            yield ParsedCatalogueRow(row_number, row, row_hash)
            continue
        if prefix == "" and event == "end_array":
            break
        raise CatalogueParseError("catalogue top-level array elements must be objects")
    for _, event, _ in parser:
        if event:
            raise CatalogueParseError("catalogue JSON has trailing content")


def _read_map(parser) -> dict[str, object]:
    item: dict[str, object] = {}
    while True:
        prefix, event, value = next(parser)
        if event == "end_map":
            return item
        if event != "map_key" or not isinstance(value, str):
            raise CatalogueParseError("catalogue rows must be flat JSON objects")
        key = value
        if key in item:
            raise CatalogueParseError("catalogue row contains duplicate object keys")
        _, value_event, parsed = next(parser)
        if value_event in {"start_map", "start_array"}:
            raise CatalogueParseError("catalogue rows must be flat JSON objects")
        if value_event not in {"string", "number", "boolean", "null"}:
            raise CatalogueParseError("catalogue row contains unsupported JSON value")
        item[key] = _json_value(parsed)


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CatalogueParseError("catalogue numeric values must be finite")
        return value
    return value


def _row_hash(row: dict[str, object]) -> str:
    try:
        encoded = canonical_json(row).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CatalogueParseError("catalogue row cannot be canonically serialized") from exc
    if len(encoded) > MAX_CANONICAL_ROW_BYTES:
        raise CatalogueParseError("catalogue canonical row size exceeds limit")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
