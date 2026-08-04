from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.hashing import stable_hash


@dataclass(frozen=True)
class CatalogueVersion:
    provider: str
    source_content_hash: str
    catalogue_schema_version: int
    effective_from: datetime
    effective_until: datetime | None
    published_at: datetime | None
    recorded_at: datetime
    row_count: int

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.source_content_hash.strip():
            raise ValueError("catalogue provider and source content hash are required")
        if (
            not isinstance(self.catalogue_schema_version, int)
            or isinstance(self.catalogue_schema_version, bool)
            or self.catalogue_schema_version <= 0
        ):
            raise ValueError("catalogue_schema_version must be positive")
        if (
            not isinstance(self.row_count, int)
            or isinstance(self.row_count, bool)
            or self.row_count < 0
        ):
            raise ValueError("row_count must be non-negative")
        effective_from = _utc(self.effective_from, "effective_from")
        effective_until = _optional_utc(self.effective_until, "effective_until")
        published_at = _optional_utc(self.published_at, "published_at")
        recorded_at = _utc(self.recorded_at, "recorded_at")
        if effective_until is not None and effective_until <= effective_from:
            raise ValueError("effective_until must be after effective_from")
        object.__setattr__(self, "effective_from", effective_from)
        object.__setattr__(self, "effective_until", effective_until)
        object.__setattr__(self, "published_at", published_at)
        object.__setattr__(self, "recorded_at", recorded_at)

    @property
    def catalogue_version_id(self) -> str:
        return stable_hash(
            {
                "entity": "catalogue_version",
                "provider": self.provider,
                "source_content_hash": self.source_content_hash,
                "catalogue_schema_version": self.catalogue_schema_version,
                "effective_from": self.effective_from,
                "effective_until": self.effective_until,
                "published_at": self.published_at,
                "row_count": self.row_count,
            }
        )

    def visible_at(self, market_as_of: datetime, known_as_of: datetime | None) -> bool:
        market_time = _utc(market_as_of, "market_as_of")
        knowledge_time = _optional_utc(known_as_of, "known_as_of")
        return (
            self.effective_from <= market_time
            and (self.effective_until is None or market_time < self.effective_until)
            and (knowledge_time is None or self.recorded_at <= knowledge_time)
        )


def _optional_utc(value: datetime | None, field_name: str) -> datetime | None:
    return _utc(value, field_name) if value is not None else None


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
