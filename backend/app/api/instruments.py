from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request

from app.schemas.instruments import InstrumentDefinition, InstrumentSearchResponse


router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("/search", response_model=InstrumentSearchResponse)
async def search_instruments(
    request: Request,
    query: str = Query(min_length=2, max_length=50),
    exchanges: str = Query(default="NSE,BSE"),
    kinds: str = Query(default="index,equity"),
    limit: int = Query(default=20, ge=1, le=30),
) -> InstrumentSearchResponse:
    exchange_values = _validated_csv(exchanges, {"NSE", "BSE"}, "exchanges")
    kind_values = _validated_csv(kinds, {"index", "equity"}, "kinds")
    items = await request.app.state.live_runtime.instruments.search(query, exchange_values, kind_values, limit)
    return InstrumentSearchResponse(
        query=query,
        items=[InstrumentDefinition.model_validate(asdict(item)) for item in items],
        received_at=datetime.now(UTC),
    )


@router.get("/resolve", response_model=InstrumentDefinition)
async def resolve_instrument(request: Request, instrument_key: str = Query(min_length=1)) -> InstrumentDefinition:
    instrument = await request.app.state.live_runtime.instruments.resolve(instrument_key)
    return InstrumentDefinition.model_validate(asdict(instrument))


def _validated_csv(value: str, allowed: set[str], field: str) -> tuple[str, ...]:
    values = tuple(dict.fromkeys(part.strip() for part in value.split(",") if part.strip()))
    if not values or any(item not in allowed for item in values):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail=f"Unsupported {field}")
    return values
