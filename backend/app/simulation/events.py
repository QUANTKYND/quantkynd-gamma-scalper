from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SimulationEvent:
    sequence: int
    timestamp: datetime
    event_type: str
    entity_id: str
    details: dict[str, object]
