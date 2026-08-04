from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.hashing import stable_hash


class SessionKind(StrEnum):
    REGULAR = "regular"
    SPECIAL = "special"


class SessionStatus(StrEnum):
    SCHEDULED = "scheduled"
    CLOSED = "closed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TradingSessionIdentity:
    exchange: str
    session_date: date
    session_kind: SessionKind = SessionKind.REGULAR

    def __post_init__(self) -> None:
        if not self.exchange.strip():
            raise ValueError("exchange is required")
        if not isinstance(self.session_date, date) or isinstance(self.session_date, datetime):
            raise TypeError("session_date must be an exchange date")
        object.__setattr__(self, "session_kind", SessionKind(self.session_kind))

    @property
    def session_id(self) -> str:
        return stable_hash(
            {
                "entity": "trading_session",
                "exchange": self.exchange,
                "session_date": self.session_date,
                "session_kind": self.session_kind.value,
            }
        )


@dataclass(frozen=True)
class TradingSessionVersion:
    session_id: str
    pre_open_at: datetime | None
    open_at: datetime
    close_at: datetime
    post_close_at: datetime | None
    timezone: str
    status: SessionStatus
    recorded_at: datetime
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id is required")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone") from exc
        if self.timezone != "Asia/Kolkata":
            raise ValueError("DATA-1.1 session timezone must be Asia/Kolkata")
        pre_open_at = _optional_utc(self.pre_open_at, "pre_open_at")
        open_at = _utc(self.open_at, "open_at")
        close_at = _utc(self.close_at, "close_at")
        post_close_at = _optional_utc(self.post_close_at, "post_close_at")
        recorded_at = _utc(self.recorded_at, "recorded_at")
        superseded_at = _optional_utc(self.superseded_at, "superseded_at")
        if open_at >= close_at:
            raise ValueError("open_at must precede close_at")
        if pre_open_at is not None and pre_open_at > open_at:
            raise ValueError("pre_open_at must not follow open_at")
        if post_close_at is not None and post_close_at < close_at:
            raise ValueError("post_close_at must not precede close_at")
        if superseded_at is not None and superseded_at <= recorded_at:
            raise ValueError("superseded_at must be after recorded_at")
        object.__setattr__(self, "pre_open_at", pre_open_at)
        object.__setattr__(self, "open_at", open_at)
        object.__setattr__(self, "close_at", close_at)
        object.__setattr__(self, "post_close_at", post_close_at)
        object.__setattr__(self, "status", SessionStatus(self.status))
        object.__setattr__(self, "recorded_at", recorded_at)
        object.__setattr__(self, "superseded_at", superseded_at)

    @property
    def session_version_id(self) -> str:
        return stable_hash(
            {
                "entity": "trading_session_version",
                "session_id": self.session_id,
                "pre_open_at": self.pre_open_at,
                "open_at": self.open_at,
                "close_at": self.close_at,
                "post_close_at": self.post_close_at,
                "timezone": self.timezone,
                "status": self.status.value,
            }
        )

    def visible_at(self, known_as_of: datetime | None) -> bool:
        knowledge_time = _optional_utc(known_as_of, "known_as_of")
        return knowledge_time is None or (
            self.recorded_at <= knowledge_time
            and (self.superseded_at is None or knowledge_time < self.superseded_at)
        )


def _optional_utc(value: datetime | None, field_name: str) -> datetime | None:
    return _utc(value, field_name) if value is not None else None


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)
