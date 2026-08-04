from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.hashing import stable_hash
from app.persistence.postgres.models import (
    CatalogueVersionRow,
    FuturesContractRow,
    InstrumentVersionRow,
    MarketInstrumentRow,
    OptionContractRow,
    ProviderContractMappingRow,
    TradingSessionRow,
    TradingSessionVersionRow,
    UnderlyingInstrumentRow,
)


DURABLE_MODELS = (
    CatalogueVersionRow,
    MarketInstrumentRow,
    UnderlyingInstrumentRow,
    FuturesContractRow,
    OptionContractRow,
    InstrumentVersionRow,
    ProviderContractMappingRow,
    TradingSessionRow,
    TradingSessionVersionRow,
)


async def database_revision(engine: AsyncEngine) -> str:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        return result.scalar_one()


async def durable_snapshot(engine: AsyncEngine) -> tuple[dict[str, int], str]:
    payload: dict[str, list[dict[str, Any]]] = {}
    async with engine.connect() as connection:
        for model in DURABLE_MODELS:
            table = model.__table__
            primary_keys = tuple(table.primary_key.columns)
            rows = (
                await connection.execute(
                    select(*table.columns).order_by(*primary_keys)
                )
            ).mappings()
            payload[table.name] = [dict(row) for row in rows]
    counts = {table_name: len(rows) for table_name, rows in payload.items()}
    return counts, stable_hash(payload)


def expected_table_names() -> set[str]:
    return {model.__tablename__ for model in DURABLE_MODELS}
