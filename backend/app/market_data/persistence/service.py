from __future__ import annotations
from datetime import UTC, datetime
from typing import Callable

from app.market_data.persistence.contracts import FramePersistenceCommand, PersistenceSummary

class MarketEventPersistenceService:
    def __init__(self, uow_factory, *, clock: Callable[[], datetime] | None = None):
        self._uow_factory = uow_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def persist_frame_result(self, command: FramePersistenceCommand) -> PersistenceSummary:
        if not isinstance(command, FramePersistenceCommand):
            raise TypeError("command must be FramePersistenceCommand")
        raw = command.raw_frame
        result = command.normalization_result
        raw_id = raw.raw_event_id
        result_id = getattr(result, "result_id", None) or result.raw_frame_identity.raw_event_id
        async with self._uow_factory() as uow:
            repo = uow.market_events
            if hasattr(repo, "persist_frame_result"):
                summary = await repo.persist_frame_result(command, persistence_recorded_at=self._clock())
            else:
                summary = await repo.insert_frame_aggregate(command, persistence_recorded_at=self._clock())
            await uow.commit()
            return summary if isinstance(summary, PersistenceSummary) else PersistenceSummary(
                result_id=result_id,
                inserted=bool(getattr(summary, "inserted", True)),
                accepted_count=len(getattr(result, "accepted_events", ())),
                failure_count=len(getattr(result, "entry_failures", ())) + (1 if getattr(result, "frame_failure", None) else 0),
            )

