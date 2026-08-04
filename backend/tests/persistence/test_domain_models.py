from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from app.instruments.catalogue import CatalogueVersion
from app.instruments.sessions import (
    SessionKind,
    SessionStatus,
    TradingSessionIdentity,
    TradingSessionVersion,
)


NOW = datetime(2026, 8, 4, 3, 30, tzinfo=UTC)


def catalogue(**changes) -> CatalogueVersion:
    values = {
        "provider": "fixture",
        "source_content_hash": "sha256:" + "a" * 64,
        "catalogue_schema_version": 1,
        "effective_from": NOW,
        "effective_until": None,
        "published_at": NOW,
        "recorded_at": NOW,
        "row_count": 3,
    }
    values.update(changes)
    return CatalogueVersion(**values)


def test_catalogue_identity_excludes_runtime_record_time() -> None:
    first = catalogue()
    later = replace(first, recorded_at=NOW + timedelta(hours=1))
    assert first.catalogue_version_id == later.catalogue_version_id


def test_catalogue_normalizes_utc_and_validates_interval() -> None:
    india = timezone(timedelta(hours=5, minutes=30))
    value = catalogue(effective_from=NOW.astimezone(india))
    assert value.effective_from == NOW
    assert value.effective_from.tzinfo is UTC
    with pytest.raises(ValueError, match="effective_until"):
        catalogue(effective_until=NOW)
    with pytest.raises(ValueError, match="row_count"):
        catalogue(row_count=-1)


def test_session_identity_and_version_are_deterministic() -> None:
    identity = TradingSessionIdentity("NSE", date(2026, 8, 4), SessionKind.REGULAR)
    version = TradingSessionVersion(
        session_id=identity.session_id,
        pre_open_at=NOW,
        open_at=NOW + timedelta(minutes=15),
        close_at=NOW + timedelta(hours=6, minutes=30),
        post_close_at=NOW + timedelta(hours=6, minutes=45),
        timezone="Asia/Kolkata",
        status=SessionStatus.CLOSED,
        recorded_at=NOW,
    )
    assert identity.session_id == TradingSessionIdentity("NSE", date(2026, 8, 4)).session_id
    assert version.session_version_id == replace(
        version,
        recorded_at=NOW + timedelta(hours=1),
    ).session_version_id


def test_session_boundaries_and_timezone_fail_explicitly() -> None:
    identity = TradingSessionIdentity("NSE", date(2026, 8, 4))
    values = {
        "session_id": identity.session_id,
        "pre_open_at": NOW,
        "open_at": NOW + timedelta(minutes=15),
        "close_at": NOW + timedelta(hours=6),
        "post_close_at": None,
        "timezone": "Asia/Kolkata",
        "status": SessionStatus.SCHEDULED,
        "recorded_at": NOW,
    }
    with pytest.raises(ValueError, match="open_at must precede"):
        TradingSessionVersion(**{**values, "close_at": values["open_at"]})
    with pytest.raises(ValueError, match="Asia/Kolkata"):
        TradingSessionVersion(**{**values, "timezone": "UTC"})
