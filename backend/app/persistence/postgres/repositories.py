from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, TypeVar

from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.instruments.catalogue import CatalogueVersion
from app.instruments.identity import (
    ContractVersion,
    FuturesContractIdentity,
    OptionContractIdentity,
    ProviderContractMapping,
    UnderlyingInstrumentIdentity,
)
from app.instruments.ports import (
    CatalogueVersionState,
    InstrumentVersionState,
    PersistenceIntegrityError,
    ProviderMappingState,
    SemanticCollisionError,
)
from app.market_data.persistence.planner import plan_parameter_chunks

class PostgresMarketEventRepository:
    def __init__(self, session, require_active):
        self._session = session
        self._require_active = require_active

    async def persist_frame_result(self, command, *, persistence_recorded_at=None):
        self._require_active()
        from app.core.hashing import canonical_json
        from app.market_data.persistence.contracts import DurableResultIdentity, FailureIdentity, PersistenceSummary
        from app.market_data.persistence.errors import (
            NormalizationFailureIdentityConflictError, NormalizationResultConflictError,
            NormalizedEventIdentityConflictError, RawFrameContentMismatchError,
        )
        raw = command.raw_frame
        result = command.normalization_result
        if raw.raw_event_id != result.raw_frame_identity.raw_event_id:
            raise ValueError("raw frame and result identities differ")
        schema_version = result.accepted_events[0].normalization_schema_version if result.accepted_events else 1
        result_id = DurableResultIdentity(raw.raw_event_id, schema_version).result_id
        from app.market_data.persistence.planner import derive_lock_stripes
        roots = [("raw_frame", raw.raw_event_id), ("normalization_result", result_id)]
        roots.extend(("market_observation", event.event_id) for event in result.accepted_events)
        for failure in getattr(result, "entry_failures", ()):
            failure_id = FailureIdentity(
                result_id,
                failure.scope.value,
                failure.reason_code,
                failure.provider_contract_key,
                failure.segment,
                payload=failure,
            ).failure_id
            roots.append(("market_failure", failure_id))
        if getattr(result, "frame_failure", None) is not None:
            frame_failure = result.frame_failure
            failure_id = FailureIdentity(
                result_id,
                frame_failure.scope.value,
                frame_failure.reason_code,
                frame_failure.provider_contract_key,
                frame_failure.segment,
                payload=frame_failure,
            ).failure_id
            roots.append(("market_failure", failure_id))
        for stripe in derive_lock_stripes(roots):
            await self._session.execute(text("SELECT pg_advisory_xact_lock(CAST(:data14_namespace AS integer), CAST(:stripe AS integer))"), {"data14_namespace":-1377601296,"stripe":stripe})

        existing_raw = (await self._session.execute(text("SELECT frame_bytes, frame_content_hash FROM raw_market_frames WHERE raw_event_id=:id"), {"id": raw.raw_event_id})).first()
        if existing_raw is None:
            await self._session.execute(text("INSERT INTO raw_market_frames (id, created_at, raw_event_id, frame_bytes, frame_content_hash, source_order) VALUES (:id, :at, :raw, :bytes, :hash, :order)"), {"id":raw.raw_event_id,"at":raw.recorded_at,"raw":raw.raw_event_id,"bytes":raw.frame_bytes,"hash":raw.frame_content_hash,"order":raw.source_order})
            inserted = True
        elif bytes(existing_raw.frame_bytes) != raw.frame_bytes or existing_raw.frame_content_hash != raw.frame_content_hash:
            raise RawFrameContentMismatchError(raw.raw_event_id)
        else:
            inserted = False

        existing_result = (await self._session.execute(text("SELECT full_result_hash, adopted_semantics_hash FROM market_normalization_results WHERE id=:id"), {"id":result_id})).first()
        if existing_result is None:
            await self._session.execute(text("INSERT INTO market_normalization_results (id, created_at, raw_event_id, full_result_hash, adopted_semantics_hash, normalization_schema_version, normalizer_implementation_version) VALUES (:id,:at,:raw,:full,:adopted,:schema,:implementation)"), {"id":result_id,"at":persistence_recorded_at or raw.recorded_at,"raw":raw.raw_event_id,"full":result.full_result_hash,"adopted":result.adopted_semantics_hash,"schema":schema_version,"implementation":"upstox-v3-normalizer-1"})
            inserted = True
        elif existing_result.full_result_hash != result.full_result_hash or existing_result.adopted_semantics_hash != result.adopted_semantics_hash:
            raise NormalizationResultConflictError(result_id)

        event_rows: list[dict[str, object]] = []
        event_memberships: list[dict[str, object]] = []
        event_payloads = {
            event.event_id: canonical_json(event)
            for event in result.accepted_events
        }
        existing_observations = await self._fetch_existing_rows(
            "market_observations",
            "id",
            tuple(event_payloads),
            ("id", "raw_event_id", "payload"),
        )
        for ordinal, event in enumerate(result.accepted_events):
            payload = event_payloads[event.event_id]
            existing = existing_observations.get(event.event_id)
            if existing is None:
                event_rows.append({
                    "id": event.event_id,
                    "created_at": raw.recorded_at,
                    "raw_event_id": raw.raw_event_id,
                    "event_type": type(event).__name__,
                    "normalization_schema_version": event.normalization_schema_version,
                    "payload": payload,
                })
            elif existing["raw_event_id"] != raw.raw_event_id or existing["payload"] != json.loads(payload):
                raise NormalizedEventIdentityConflictError(event.event_id)
            event_memberships.append({
                "id": f"{result_id}:{ordinal}",
                "created_at": raw.recorded_at,
                "result_id": result_id,
                "raw_event_id": raw.raw_event_id,
                "event_id": event.event_id,
                "event_ordinal": ordinal,
            })
        await self._bulk_insert_json_rows("market_observations", event_rows, payload_cast=True)

        existing_memberships = await self._fetch_existing_rows(
            "market_normalization_result_events",
            "id",
            tuple(membership["id"] for membership in event_memberships),
            ("id", "result_id", "raw_event_id", "event_id", "event_ordinal"),
        )
        missing_event_memberships = []
        for membership in event_memberships:
            existing = existing_memberships.get(membership["id"])
            if existing is None:
                missing_event_memberships.append(membership)
            elif tuple(existing.items()) != tuple(membership.items()):
                raise NormalizedEventIdentityConflictError(membership["event_id"])
        await self._bulk_insert_rows("market_normalization_result_events", missing_event_memberships)

        failure_rows: list[dict[str, object]] = []
        failure_memberships: list[dict[str, object]] = []
        role_ordinals = {"frame": 0, "entry": 0}
        failure_payloads = []
        failures = []
        if getattr(result, "frame_failure", None) is not None:
            failures.append(("frame", result.frame_failure))
        failures.extend(("entry", failure) for failure in result.entry_failures)
        for role, failure in failures:
            failure_id = FailureIdentity(
                result_id,
                failure.scope.value,
                failure.reason_code,
                failure.provider_contract_key,
                failure.segment,
                payload=failure,
            ).failure_id
            payload = canonical_json(failure)
            failure_payloads.append((failure_id, payload, failure))
            failure_memberships.append({
                "id": f"{result_id}:{role}:{role_ordinals[role]}",
                "created_at": raw.recorded_at,
                "result_id": result_id,
                "raw_event_id": raw.raw_event_id,
                "failure_id": failure_id,
                "failure_role": role,
                "failure_ordinal": role_ordinals[role],
            })
            role_ordinals[role] += 1
        existing_failures = await self._fetch_existing_rows(
            "market_normalization_failures",
            "failure_id",
            tuple(failure_id for failure_id, _, _ in failure_payloads),
            ("failure_id", "payload"),
        )
        for failure_id, payload, failure in failure_payloads:
            existing = existing_failures.get(failure_id)
            if existing is None:
                failure_rows.append({
                    "id": failure_id,
                    "created_at": raw.recorded_at,
                    "result_id": result_id,
                    "raw_event_id": raw.raw_event_id,
                    "failure_id": failure_id,
                    "payload": payload,
                })
            elif existing["payload"] != json.loads(payload):
                raise NormalizationFailureIdentityConflictError(failure_id)
        existing_failure_memberships = await self._fetch_existing_rows(
            "market_normalization_result_failures",
            "id",
            tuple(membership["id"] for membership in failure_memberships),
            ("id", "result_id", "raw_event_id", "failure_id", "failure_role", "failure_ordinal"),
        )
        missing_failure_memberships = []
        for membership in failure_memberships:
            existing = existing_failure_memberships.get(membership["id"])
            if existing is None:
                missing_failure_memberships.append(membership)
            elif tuple(existing.items()) != tuple(membership.items()):
                raise NormalizationFailureIdentityConflictError(membership["failure_id"])
        await self._bulk_insert_json_rows("market_normalization_failures", failure_rows, payload_cast=True)
        await self._bulk_insert_rows("market_normalization_result_failures", missing_failure_memberships)

        accepted = len(getattr(result, "accepted_events", ()))
        failures = len(getattr(result, "entry_failures", ())) + (1 if getattr(result, "frame_failure", None) else 0)
        return PersistenceSummary(result_id=result_id, inserted=inserted, accepted_count=accepted, failure_count=failures)

    async def _bulk_insert_rows(self, table, rows):
        if not rows:
            return
        columns = tuple(rows[0].keys())
        chunks = plan_parameter_chunks(len(rows), len(columns))
        for chunk in chunks:
            batch = rows[chunk.offset : chunk.offset + chunk.size]
            await self._session.execute(
                text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(f':{name}' for name in columns)})"),
                batch,
            )

    async def _bulk_insert_json_rows(self, table, rows, *, payload_cast: bool = False):
        if not rows:
            return
        columns = tuple(rows[0].keys())
        chunks = plan_parameter_chunks(len(rows), len(columns))
        for chunk in chunks:
            batch = rows[chunk.offset : chunk.offset + chunk.size]
            inserts = ", ".join(
                "CAST(:payload AS json)" if column == "payload" else f":{column}"
                for column in columns
            )
            await self._session.execute(
                text(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({inserts})"),
                batch,
            )

    async def _fetch_existing_rows(self, table, key_name, identifiers, selected_columns):
        if not identifiers:
            return {}
        if len(identifiers) == 1:
            id_list = [identifiers[0]]
        else:
            id_list = list(identifiers)
        placeholders = ", ".join(f":id_{index}" for index in range(len(id_list)))
        rows = await self._session.execute(
            text(f"SELECT {', '.join(selected_columns)} FROM {table} WHERE {key_name} IN ({placeholders})"),
            {f"id_{index}": value for index, value in enumerate(id_list)},
        )
        results = {}
        for row in rows:
            values = dict(row._mapping)
            results[values[key_name]] = values
        return results

    async def _insert_membership(self, table, values, predicate):
        existing = (await self._session.execute(text(f"SELECT id FROM {table} WHERE {predicate}"), values)).first()
        if existing is None:
            columns = ", ".join(values)
            parameters = ", ".join(f":{name}" for name in values)
            await self._session.execute(text(f"INSERT INTO {table} ({columns}) VALUES ({parameters})"), values)

    async def get_result(self, raw_event_id, normalization_schema_version):
        self._require_active()
        row = await self._session.execute(text("SELECT * FROM market_normalization_results WHERE raw_event_id=:raw AND normalization_schema_version=:schema"), {"raw":raw_event_id,"schema":normalization_schema_version})
        return row.first()

    async def insert_or_compare_raw_frame(self, frame):
        if not hasattr(frame, "raw_frame"):
            raise TypeError("frame must supply a raw_frame and normalization_result pair")
        return await self.persist_frame_result(frame)

    async def insert_or_compare_normalization_result(self, result):
        if not hasattr(result, "raw_frame_identity"):
            raise TypeError("result must be a frame normalization result")
        return result

    async def insert_or_compare_market_observations(self, observations):
        return tuple(observations)

    async def insert_or_compare_quote_observations(self, observations):
        return tuple(observations)

    async def insert_or_compare_failures(self, failures):
        return tuple(failures)

    async def insert_result_event_memberships(self, memberships):
        return tuple(memberships)

    async def insert_result_failure_memberships(self, memberships):
        return tuple(memberships)
    async def get_raw_frame_metadata(self, raw_event_id):
        row = await self._session.execute(text("SELECT raw_event_id,frame_content_hash,source_order,created_at FROM raw_market_frames WHERE raw_event_id=:id"), {"id":raw_event_id})
        return row.first()
    async def get_raw_frame(self, raw_event_id):
        row = await self._session.execute(text("SELECT * FROM raw_market_frames WHERE raw_event_id=:id"), {"id":raw_event_id})
        return row.first()
    async def get_event(self, event_id, normalization_schema_version):
        row = await self._session.execute(text("SELECT o.* FROM market_observations o JOIN market_normalization_result_events m ON m.event_id=o.id JOIN market_normalization_results r ON r.id=m.result_id WHERE o.id=:id AND o.normalization_schema_version=:schema AND r.normalization_schema_version=:schema"), {"id":event_id,"schema":normalization_schema_version})
        return row.first()
    async def load_result_aggregate(self, raw_event_id, normalization_schema_version):
        result = await self.get_result(raw_event_id, normalization_schema_version)
        if result is None: return None
        events = (await self._session.execute(text("SELECT o.* FROM market_normalization_result_events m JOIN market_observations o ON o.id=m.event_id WHERE m.result_id=:id ORDER BY m.event_ordinal"), {"id":result.id})).all()
        failures = (await self._session.execute(text("SELECT f.*,m.failure_role,m.failure_ordinal FROM market_normalization_result_failures m JOIN market_normalization_failures f ON f.failure_id=m.failure_id WHERE m.result_id=:id ORDER BY m.failure_role,m.failure_ordinal"), {"id":result.id})).all()
        return {"result":result,"events":tuple(events),"failures":tuple(failures)}
    async def scan_normalization_results(self, normalization_schema_version, cursor=None, limit=100):
        rows = await self._session.execute(text("SELECT * FROM market_normalization_results WHERE normalization_schema_version=:schema AND (:cursor IS NULL OR id>:cursor) ORDER BY id LIMIT :limit"), {"schema":normalization_schema_version,"cursor":cursor,"limit":limit})
        return tuple(rows.all())
    async def list_subject_observations(self, normalization_schema_version, subject_id, limit=100):
        rows = await self._session.execute(text("SELECT DISTINCT o.* FROM market_observations o JOIN market_normalization_result_events m ON m.event_id=o.id JOIN market_normalization_results r ON r.id=m.result_id WHERE o.normalization_schema_version=:schema AND CAST(o.payload AS text) LIKE :subject ORDER BY o.id LIMIT :limit"), {"schema":normalization_schema_version,"subject":f'%{subject_id}%',"limit":limit})
        return tuple(rows.all())
    async def list_provider_status(self, normalization_schema_version, provider, limit=100):
        rows = await self._session.execute(text("SELECT DISTINCT o.* FROM market_observations o JOIN market_normalization_result_events m ON m.event_id=o.id JOIN market_normalization_results r ON r.id=m.result_id WHERE o.normalization_schema_version=:schema AND CAST(o.payload AS text) LIKE :provider ORDER BY o.id LIMIT :limit"), {"schema":normalization_schema_version,"provider":f'%{provider}%',"limit":limit})
        return tuple(rows.all())
from app.instruments.provider_catalogue import (
    CatalogueIngestionRun,
    CatalogueMembership,
    CatalogueRowOutcome,
    CatalogueSourceArtifact,
)
from app.instruments.sessions import TradingSessionIdentity, TradingSessionVersion
from app.instruments.temporal_records import (
    TemporalRecord,
    TemporalRecordKind,
    TemporalState,
    TemporalSupersessionConflictError,
    catalogue_temporal_record,
    instrument_version_temporal_record,
    provider_mapping_temporal_record,
    resolve_temporal_knowledge_leaf,
    resolve_temporal_state,
    trading_session_version_temporal_record,
)
from app.persistence.postgres.mappings import (
    catalogue_from_row,
    catalogue_values,
    future_from_rows,
    future_values,
    market_instrument_values,
    option_from_rows,
    option_values,
    provider_mapping_from_row,
    provider_mapping_values,
    ingestion_run_from_row,
    ingestion_run_values,
    membership_values,
    row_outcome_values,
    source_artifact_values,
    temporal_record_from_row,
    temporal_record_values,
    trading_session_values,
    trading_session_version_from_row,
    trading_session_version_values,
    underlying_from_rows,
    underlying_values,
    version_from_row,
    version_values,
)
from app.persistence.postgres.models import (
    CatalogueIngestionRunRow,
    CatalogueMembershipRow,
    CatalogueRowOutcomeRow,
    CatalogueSourceArtifactRow,
    CatalogueVersionRecordRow,
    CatalogueVersionRow,
    FuturesContractRow,
    InstrumentVersionRecordRow,
    InstrumentVersionRow,
    MarketInstrumentRow,
    OptionContractRow,
    ProviderContractMappingRow,
    ProviderMappingRecordRow,
    TradingSessionRow,
    TradingSessionVersionRecordRow,
    TradingSessionVersionRow,
    UnderlyingInstrumentRow,
)
from app.core.hashing import stable_hash


class PostgresCatalogueRepository:
    def __init__(self, session: AsyncSession, require_active: Callable[[], None]) -> None:
        self._session = session
        self._require_active = require_active

    async def add(
        self,
        catalogue: CatalogueVersion,
        supersedes_record_id: str | None = None,
    ) -> str:
        self._require_active()
        await _insert_immutable(
            self._session,
            CatalogueVersionRow,
            "catalogue_version_id",
            catalogue_values(catalogue),
            "catalogue version",
        )
        record = catalogue_temporal_record(catalogue, supersedes_record_id)
        await _insert_temporal_record(
            self._session,
            CatalogueVersionRecordRow,
            "catalogue_version_id",
            record,
            "catalogue version record",
        )
        return record.record_id

    async def get(self, catalogue_version_id: str) -> CatalogueVersion | None:
        self._require_active()
        item = (
            await self._session.execute(
                select(CatalogueVersionRow, CatalogueVersionRecordRow)
                .join(
                    CatalogueVersionRecordRow,
                    CatalogueVersionRecordRow.catalogue_version_id
                    == CatalogueVersionRow.catalogue_version_id,
                )
                .where(CatalogueVersionRow.catalogue_version_id == catalogue_version_id)
                .order_by(
                    CatalogueVersionRecordRow.recorded_at.desc(),
                    CatalogueVersionRecordRow.record_id,
                )
                .limit(1)
            )
        ).one_or_none()
        return catalogue_from_row(*item) if item is not None else None

    async def list_for_provider(self, provider: str) -> tuple[CatalogueVersion, ...]:
        self._require_active()
        rows = (
            await self._session.execute(
                select(CatalogueVersionRow, CatalogueVersionRecordRow)
                .join(
                    CatalogueVersionRecordRow,
                    CatalogueVersionRecordRow.catalogue_version_id
                    == CatalogueVersionRow.catalogue_version_id,
                )
                .where(CatalogueVersionRow.provider == provider)
                .order_by(
                    CatalogueVersionRow.effective_from,
                    CatalogueVersionRow.catalogue_version_id,
                    CatalogueVersionRecordRow.recorded_at.desc(),
                    CatalogueVersionRecordRow.record_id,
                )
            )
        ).all()
        values: dict[str, CatalogueVersion] = {}
        for row, record_row in rows:
            values.setdefault(row.catalogue_version_id, catalogue_from_row(row, record_row))
        return tuple(values.values())

    async def resolve(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersion | None:
        resolved = await self.resolve_state(provider, market_as_of, known_as_of)
        return resolved.value if resolved is not None else None

    async def resolve_state(
        self,
        provider: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> CatalogueVersionState | None:
        self._require_active()
        states = await self._states_for_provider(provider, known_as_of)
        resolved = resolve_temporal_state(
            states,
            known_as_of,
            lambda value: value.effective_from <= market_as_of
            and (value.effective_until is None or market_as_of < value.effective_until),
        )
        if resolved is None:
            return None
        return CatalogueVersionState(resolved.value, resolved.record.record_id)

    async def resolve_knowledge_leaf(
        self,
        provider: str,
        known_as_of: datetime | None = None,
    ) -> CatalogueVersionState | None:
        self._require_active()
        resolved = resolve_temporal_knowledge_leaf(
            await self._states_for_provider(provider, known_as_of),
            known_as_of,
        )
        if resolved is None:
            return None
        return CatalogueVersionState(resolved.value, resolved.record.record_id)

    async def _states_for_provider(
        self,
        provider: str,
        known_as_of: datetime | None,
    ) -> tuple[TemporalState[CatalogueVersion], ...]:
        conditions = [CatalogueVersionRow.provider == provider]
        if known_as_of is not None:
            conditions.append(CatalogueVersionRecordRow.recorded_at <= known_as_of)
        rows = (
            await self._session.execute(
                select(CatalogueVersionRow, CatalogueVersionRecordRow)
                .join(
                    CatalogueVersionRecordRow,
                    CatalogueVersionRecordRow.catalogue_version_id
                    == CatalogueVersionRow.catalogue_version_id,
                )
                .where(*conditions)
                .order_by(CatalogueVersionRecordRow.recorded_at, CatalogueVersionRecordRow.record_id)
            )
        ).all()
        return tuple(
            TemporalState(
                temporal_record_from_row(
                    record_row,
                    TemporalRecordKind.CATALOGUE_VERSION,
                    "catalogue_version_id",
                ),
                catalogue_from_row(row, record_row),
            )
            for row, record_row in rows
        )


class PostgresInstrumentRepository:
    def __init__(self, session: AsyncSession, require_active: Callable[[], None]) -> None:
        self._session = session
        self._require_active = require_active

    async def add_underlying(self, instrument: UnderlyingInstrumentIdentity) -> None:
        self._require_active()
        await self._add_registry(instrument)
        await _insert_immutable(
            self._session,
            UnderlyingInstrumentRow,
            "instrument_id",
            underlying_values(instrument),
            "underlying instrument",
        )

    async def add_future(self, contract: FuturesContractIdentity) -> None:
        self._require_active()
        await self._add_registry(contract)
        await _insert_immutable(
            self._session,
            FuturesContractRow,
            "contract_id",
            future_values(contract),
            "futures contract",
        )

    async def add_option(self, contract: OptionContractIdentity) -> None:
        self._require_active()
        await self._add_registry(contract)
        await _insert_immutable(
            self._session,
            OptionContractRow,
            "contract_id",
            option_values(contract),
            "option contract",
        )

    async def add_version(
        self,
        version: ContractVersion,
        supersedes_record_id: str | None = None,
    ) -> str:
        self._require_active()
        await _insert_immutable(
            self._session,
            InstrumentVersionRow,
            "version_id",
            version_values(version),
            "instrument version",
        )
        record = instrument_version_temporal_record(version, supersedes_record_id)
        await _insert_temporal_record(
            self._session,
            InstrumentVersionRecordRow,
            "version_id",
            record,
            "instrument version record",
        )
        return record.record_id

    async def add_provider_mapping(
        self,
        mapping: ProviderContractMapping,
        supersedes_record_id: str | None = None,
    ) -> str:
        self._require_active()
        await _insert_immutable(
            self._session,
            ProviderContractMappingRow,
            "mapping_id",
            provider_mapping_values(mapping),
            "provider mapping",
        )
        record = provider_mapping_temporal_record(mapping, supersedes_record_id)
        await _insert_temporal_record(
            self._session,
            ProviderMappingRecordRow,
            "mapping_id",
            record,
            "provider mapping record",
        )
        return record.record_id

    async def get_identity(
        self,
        instrument_id: str,
    ) -> UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity | None:
        self._require_active()
        registry = await self._session.get(MarketInstrumentRow, instrument_id)
        if registry is None:
            return None
        if registry.instrument_kind == "underlying":
            return underlying_from_rows(
                registry,
                _required_subtype(await self._session.get(UnderlyingInstrumentRow, instrument_id)),
            )
        if registry.instrument_kind == "future":
            return future_from_rows(
                registry,
                _required_subtype(await self._session.get(FuturesContractRow, instrument_id)),
            )
        if registry.instrument_kind == "option":
            return option_from_rows(
                registry,
                _required_subtype(await self._session.get(OptionContractRow, instrument_id)),
            )
        raise PersistenceIntegrityError("durable instrument registry has an unsupported kind")

    async def get_version(self, version_id: str) -> ContractVersion | None:
        self._require_active()
        item = (
            await self._session.execute(
                select(
                    InstrumentVersionRow,
                    InstrumentVersionRecordRow,
                    MarketInstrumentRow.instrument_kind,
                )
                .join(
                    InstrumentVersionRecordRow,
                    InstrumentVersionRecordRow.version_id == InstrumentVersionRow.version_id,
                )
                .join(
                    MarketInstrumentRow,
                    MarketInstrumentRow.instrument_id == InstrumentVersionRow.instrument_id,
                )
                .where(InstrumentVersionRow.version_id == version_id)
                .order_by(
                    InstrumentVersionRecordRow.recorded_at.desc(),
                    InstrumentVersionRecordRow.record_id,
                )
                .limit(1)
            )
        ).one_or_none()
        return version_from_row(item[0], item[1], item[2]) if item is not None else None

    async def resolve_provider_key(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderContractMapping | None:
        resolved = await self.resolve_provider_key_state(
            provider,
            provider_contract_key,
            market_as_of,
            known_as_of,
        )
        return resolved.value if resolved is not None else None

    async def resolve_version_state(
        self,
        instrument_id: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> InstrumentVersionState | None:
        self._require_active()
        resolved = resolve_temporal_state(
            await self._version_states(instrument_id, known_as_of),
            known_as_of,
            lambda value: value.valid_from <= market_as_of
            and (value.valid_until is None or market_as_of < value.valid_until),
        )
        if resolved is None:
            return None
        return InstrumentVersionState(resolved.value, resolved.record.record_id)

    async def resolve_version_knowledge_leaf(
        self,
        instrument_id: str,
        known_as_of: datetime | None = None,
    ) -> InstrumentVersionState | None:
        self._require_active()
        resolved = resolve_temporal_knowledge_leaf(
            await self._version_states(instrument_id, known_as_of),
            known_as_of,
        )
        if resolved is None:
            return None
        return InstrumentVersionState(resolved.value, resolved.record.record_id)

    async def resolve_provider_key_state(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderMappingState | None:
        self._require_active()
        mapping_rows = await self._mapping_rows(
            provider,
            provider_contract_key,
            known_as_of,
        )
        scopes = {row.instrument_id for _, _, row in mapping_rows}
        current_versions = {
            resolved.record.semantic_id
            for scope in sorted(scopes)
            if (
                resolved := resolve_temporal_state(
                    await self._version_states(scope, known_as_of),
                    known_as_of,
                    lambda value: value.valid_from <= market_as_of
                    and (value.valid_until is None or market_as_of < value.valid_until),
                )
            )
            is not None
        }
        states = tuple(
            TemporalState(
                temporal_record_from_row(
                    record_row,
                    TemporalRecordKind.PROVIDER_MAPPING,
                    "mapping_id",
                ),
                provider_mapping_from_row(mapping_row, record_row),
            )
            for mapping_row, record_row, _ in mapping_rows
        )
        resolved = resolve_temporal_state(
            states,
            known_as_of,
            lambda value: value.contract_version_id in current_versions
            and value.effective_from <= market_as_of
            and (value.effective_until is None or market_as_of < value.effective_until),
        )
        if resolved is None:
            return None
        instrument_ids = {
            mapping_row.mapping_id: version_row.instrument_id
            for mapping_row, _, version_row in mapping_rows
        }
        return ProviderMappingState(
            resolved.value,
            resolved.record.record_id,
            instrument_ids[resolved.value.mapping_id],
        )

    async def resolve_provider_key_mapping_state(
        self,
        provider: str,
        provider_contract_key: str,
        market_as_of: datetime,
        known_as_of: datetime | None,
    ) -> ProviderMappingState | None:
        self._require_active()
        mapping_rows = await self._mapping_rows(provider, provider_contract_key, known_as_of)
        states = tuple(
            TemporalState(
                temporal_record_from_row(record_row, TemporalRecordKind.PROVIDER_MAPPING, "mapping_id"),
                provider_mapping_from_row(mapping_row, record_row),
            )
            for mapping_row, record_row, _ in mapping_rows
        )
        resolved = resolve_temporal_state(
            states,
            known_as_of,
            lambda value: value.effective_from <= market_as_of
            and (value.effective_until is None or market_as_of < value.effective_until),
        )
        if resolved is None:
            return None
        instrument_ids = {
            mapping_row.mapping_id: version_row.instrument_id
            for mapping_row, _, version_row in mapping_rows
        }
        return ProviderMappingState(
            resolved.value,
            resolved.record.record_id,
            instrument_ids[resolved.value.mapping_id],
        )

    async def resolve_provider_key_knowledge_leaf(
        self,
        provider: str,
        provider_contract_key: str,
        known_as_of: datetime | None = None,
    ) -> ProviderMappingState | None:
        self._require_active()
        mapping_rows = await self._mapping_rows(
            provider,
            provider_contract_key,
            known_as_of,
        )
        states = tuple(
            TemporalState(
                temporal_record_from_row(
                    record_row,
                    TemporalRecordKind.PROVIDER_MAPPING,
                    "mapping_id",
                ),
                provider_mapping_from_row(mapping_row, record_row),
            )
            for mapping_row, record_row, _ in mapping_rows
        )
        resolved = resolve_temporal_knowledge_leaf(states, known_as_of)
        if resolved is None:
            return None
        instrument_ids = {
            mapping_row.mapping_id: version_row.instrument_id
            for mapping_row, _, version_row in mapping_rows
        }
        return ProviderMappingState(
            resolved.value,
            resolved.record.record_id,
            instrument_ids[resolved.value.mapping_id],
        )

    async def resolve_provider_key_instrument_id(
        self,
        provider: str,
        provider_contract_key: str,
    ) -> str | None:
        self._require_active()
        instrument_ids = tuple(
            sorted(
                set(
                    await self._session.scalars(
                        select(InstrumentVersionRow.instrument_id)
                        .join(
                            ProviderContractMappingRow,
                            ProviderContractMappingRow.contract_version_id
                            == InstrumentVersionRow.version_id,
                        )
                        .where(
                            ProviderContractMappingRow.provider == provider,
                            ProviderContractMappingRow.provider_contract_key
                            == provider_contract_key,
                        )
                    )
                )
            )
        )
        if len(instrument_ids) > 1:
            raise PersistenceIntegrityError(
                "provider key has conflicting durable economic instrument bindings"
            )
        return instrument_ids[0] if instrument_ids else None

    async def list_contract_versions(
        self,
        underlying_instrument_id: str,
        expiry: date,
    ) -> tuple[ContractVersion, ...]:
        self._require_active()
        result = await self._session.execute(
            select(
                InstrumentVersionRow,
                InstrumentVersionRecordRow,
                MarketInstrumentRow.instrument_kind,
            )
            .join(
                InstrumentVersionRecordRow,
                InstrumentVersionRecordRow.version_id == InstrumentVersionRow.version_id,
            )
            .join(
                MarketInstrumentRow,
                MarketInstrumentRow.instrument_id == InstrumentVersionRow.instrument_id,
            )
            .outerjoin(
                FuturesContractRow,
                FuturesContractRow.contract_id == MarketInstrumentRow.instrument_id,
            )
            .outerjoin(
                OptionContractRow,
                OptionContractRow.contract_id == MarketInstrumentRow.instrument_id,
            )
            .where(
                or_(
                    and_(
                        FuturesContractRow.underlying_instrument_id == underlying_instrument_id,
                        FuturesContractRow.expiry == expiry,
                    ),
                    and_(
                        OptionContractRow.underlying_instrument_id == underlying_instrument_id,
                        OptionContractRow.expiry == expiry,
                    ),
                )
            )
            .order_by(
                InstrumentVersionRow.version_id,
                InstrumentVersionRecordRow.recorded_at.desc(),
                InstrumentVersionRecordRow.record_id,
            )
        )
        values: dict[str, ContractVersion] = {}
        for row, record_row, kind in result.all():
            values.setdefault(row.version_id, version_from_row(row, record_row, kind))
        return tuple(values.values())

    async def _mapping_rows(
        self,
        provider: str,
        provider_contract_key: str,
        known_as_of: datetime | None,
    ) -> list[tuple[Any, Any, Any]]:
        conditions = [
            ProviderContractMappingRow.provider == provider,
            ProviderContractMappingRow.provider_contract_key == provider_contract_key,
        ]
        if known_as_of is not None:
            conditions.append(ProviderMappingRecordRow.recorded_at <= known_as_of)
        return list(
            (
                await self._session.execute(
                    select(
                        ProviderContractMappingRow,
                        ProviderMappingRecordRow,
                        InstrumentVersionRow,
                    )
                    .join(
                        ProviderMappingRecordRow,
                        ProviderMappingRecordRow.mapping_id
                        == ProviderContractMappingRow.mapping_id,
                    )
                    .join(
                        InstrumentVersionRow,
                        InstrumentVersionRow.version_id
                        == ProviderContractMappingRow.contract_version_id,
                    )
                    .where(*conditions)
                    .order_by(ProviderMappingRecordRow.recorded_at, ProviderMappingRecordRow.record_id)
                )
            ).all()
        )

    async def _version_states(
        self,
        scope_id: str,
        known_as_of: datetime | None,
    ) -> tuple[TemporalState[ContractVersion], ...]:
        conditions = [InstrumentVersionRecordRow.scope_id == scope_id]
        if known_as_of is not None:
            conditions.append(InstrumentVersionRecordRow.recorded_at <= known_as_of)
        rows = (
            await self._session.execute(
                select(
                    InstrumentVersionRow,
                    InstrumentVersionRecordRow,
                    MarketInstrumentRow.instrument_kind,
                )
                .join(
                    InstrumentVersionRecordRow,
                    InstrumentVersionRecordRow.version_id == InstrumentVersionRow.version_id,
                )
                .join(
                    MarketInstrumentRow,
                    MarketInstrumentRow.instrument_id == InstrumentVersionRow.instrument_id,
                )
                .where(*conditions)
                .order_by(InstrumentVersionRecordRow.recorded_at, InstrumentVersionRecordRow.record_id)
            )
        ).all()
        return tuple(
            TemporalState(
                temporal_record_from_row(
                    record_row,
                    TemporalRecordKind.INSTRUMENT_VERSION,
                    "version_id",
                ),
                version_from_row(row, record_row, kind),
            )
            for row, record_row, kind in rows
        )

    async def _add_registry(
        self,
        instrument: UnderlyingInstrumentIdentity | FuturesContractIdentity | OptionContractIdentity,
    ) -> None:
        await _insert_immutable(
            self._session,
            MarketInstrumentRow,
            "instrument_id",
            market_instrument_values(instrument),
            "market instrument",
        )


class PostgresTradingSessionRepository:
    def __init__(self, session: AsyncSession, require_active: Callable[[], None]) -> None:
        self._session = session
        self._require_active = require_active

    async def add_identity(self, session: TradingSessionIdentity) -> None:
        self._require_active()
        await _insert_immutable(
            self._session,
            TradingSessionRow,
            "session_id",
            trading_session_values(session),
            "trading session",
        )

    async def add_version(
        self,
        version: TradingSessionVersion,
        supersedes_record_id: str | None = None,
    ) -> str:
        self._require_active()
        await _insert_immutable(
            self._session,
            TradingSessionVersionRow,
            "session_version_id",
            trading_session_version_values(version),
            "trading session version",
        )
        record = trading_session_version_temporal_record(version, supersedes_record_id)
        await _insert_temporal_record(
            self._session,
            TradingSessionVersionRecordRow,
            "session_version_id",
            record,
            "trading session version record",
        )
        return record.record_id

    async def resolve(
        self,
        exchange: str,
        session_date: date,
        session_kind: str,
        known_as_of: datetime | None,
    ) -> TradingSessionVersion | None:
        self._require_active()
        conditions = [
            TradingSessionRow.exchange == exchange,
            TradingSessionRow.session_date == session_date,
            TradingSessionRow.session_kind == session_kind,
        ]
        if known_as_of is not None:
            conditions.append(TradingSessionVersionRecordRow.recorded_at <= known_as_of)
        rows = (
            await self._session.execute(
                select(TradingSessionVersionRow, TradingSessionVersionRecordRow)
                .join(
                    TradingSessionRow,
                    TradingSessionRow.session_id == TradingSessionVersionRow.session_id,
                )
                .join(
                    TradingSessionVersionRecordRow,
                    TradingSessionVersionRecordRow.session_version_id
                    == TradingSessionVersionRow.session_version_id,
                )
                .where(*conditions)
                .order_by(
                    TradingSessionVersionRecordRow.recorded_at,
                    TradingSessionVersionRecordRow.record_id,
                )
            )
        ).all()
        states = tuple(
            TemporalState(
                temporal_record_from_row(
                    record_row,
                    TemporalRecordKind.TRADING_SESSION_VERSION,
                    "session_version_id",
                ),
                trading_session_version_from_row(row, record_row),
            )
            for row, record_row in rows
        )
        resolved = resolve_temporal_state(states, known_as_of, lambda value: True)
        return resolved.value if resolved is not None else None


class PostgresCatalogueIngestionRepository:
    def __init__(self, session: AsyncSession, require_active: Callable[[], None]) -> None:
        self._session = session
        self._require_active = require_active

    async def lock_provider_profile(self, provider: str, profile_version: str) -> None:
        self._require_active()
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _advisory_lock_key(provider, profile_version)},
        )

    async def add_source_artifact(self, artifact: CatalogueSourceArtifact) -> None:
        self._require_active()
        await _insert_immutable(
            self._session,
            CatalogueSourceArtifactRow,
            "source_artifact_id",
            source_artifact_values(artifact),
            "catalogue source artifact",
        )

    async def add_ingestion_run(self, run: CatalogueIngestionRun) -> None:
        self._require_active()
        await _insert_immutable(
            self._session,
            CatalogueIngestionRunRow,
            "ingestion_run_id",
            ingestion_run_values(run),
            "catalogue ingestion run",
        )

    async def add_row_outcomes(self, outcomes: tuple[CatalogueRowOutcome, ...]) -> None:
        self._require_active()
        for outcome in outcomes:
            await _insert_immutable(
                self._session,
                CatalogueRowOutcomeRow,
                "row_outcome_id",
                row_outcome_values(outcome),
                "catalogue row outcome",
            )

    async def add_memberships(self, memberships: tuple[CatalogueMembership, ...]) -> None:
        self._require_active()
        provider_key_memberships: dict[tuple[str, str], str] = {}
        for membership in memberships:
            key = (membership.catalogue_version_id, membership.provider_contract_key)
            existing_membership_id = provider_key_memberships.get(key)
            if existing_membership_id is not None and existing_membership_id != membership.membership_id:
                raise PersistenceIntegrityError(
                    "catalogue membership contains a duplicate provider key"
                )
            provider_key_memberships[key] = membership.membership_id
        for catalogue_version_id, provider_contract_key in sorted(provider_key_memberships):
            existing_membership_ids = tuple(
                await self._session.scalars(
                    select(CatalogueMembershipRow.membership_id).where(
                        CatalogueMembershipRow.catalogue_version_id == catalogue_version_id,
                        CatalogueMembershipRow.provider_contract_key == provider_contract_key,
                    )
                )
            )
            expected_membership_id = provider_key_memberships[
                (catalogue_version_id, provider_contract_key)
            ]
            if any(
                membership_id != expected_membership_id
                for membership_id in existing_membership_ids
            ):
                raise PersistenceIntegrityError(
                    "catalogue membership conflicts with an existing provider key"
                )
        for membership in memberships:
            await _insert_immutable(
                self._session,
                CatalogueMembershipRow,
                "membership_id",
                membership_values(membership),
                "catalogue membership",
            )

    async def list_memberships_for_catalogue(
        self,
        catalogue_version_id: str,
    ) -> tuple[CatalogueMembership, ...]:
        self._require_active()
        rows = (
            await self._session.scalars(
                select(CatalogueMembershipRow)
                .where(CatalogueMembershipRow.catalogue_version_id == catalogue_version_id)
                .order_by(CatalogueMembershipRow.membership_id)
            )
        ).all()
        return tuple(
            CatalogueMembership(
                catalogue_version_id=row.catalogue_version_id,
                row_outcome_id=row.row_outcome_id,
                source_row_occurrence_id=row.source_row_occurrence_id,
                source_row_semantic_id=row.source_row_semantic_id,
                instrument_id=row.instrument_id,
                version_id=row.version_id,
                mapping_id=row.mapping_id,
                provider_contract_key=row.provider_contract_key,
                raw_row_hash=row.raw_row_hash,
                normalized_row_hash=row.normalized_row_hash,
            )
            for row in rows
        )

    async def get_ingestion_run_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> CatalogueIngestionRun | None:
        self._require_active()
        row = (
            await self._session.scalars(
                select(CatalogueIngestionRunRow).where(
                    CatalogueIngestionRunRow.idempotency_key == idempotency_key
                )
            )
        ).one_or_none()
        return ingestion_run_from_row(row) if row is not None else None


RowType = TypeVar("RowType")


async def _insert_temporal_record(
    session: AsyncSession,
    model: type[RowType],
    semantic_column: str,
    record: TemporalRecord,
    label: str,
) -> None:
    values = temporal_record_values(record, semantic_column)
    existing = await session.get(model, record.record_id)
    if existing is not None:
        _require_equal_record(existing, values, label)
        return
    if record.supersedes_record_id is not None:
        predecessor = (
            await session.scalars(
                select(model)
                .where(getattr(model, "record_id") == record.supersedes_record_id)
                .with_for_update()
            )
        ).one_or_none()
        if predecessor is None:
            raise TemporalSupersessionConflictError(
                f"{label} supersession target does not exist"
            )
        if predecessor.scope_id != record.scope_id:
            raise TemporalSupersessionConflictError(
                f"{label} supersession target belongs to another scope"
            )
        if record.recorded_at <= predecessor.recorded_at:
            raise TemporalSupersessionConflictError(
                f"{label} must be recorded after its supersession target"
            )
        successor = (
            await session.scalars(
                select(model).where(
                    getattr(model, "supersedes_record_id") == record.supersedes_record_id
                )
            )
        ).one_or_none()
        if successor is not None:
            if successor.record_id == record.record_id:
                _require_equal_record(successor, values, label)
                return
            raise TemporalSupersessionConflictError(
                f"{label} supersession target already has a successor"
            )
    try:
        await _insert_immutable(
            session,
            model,
            "record_id",
            values,
            label,
        )
    except PersistenceIntegrityError:
        if record.supersedes_record_id is not None:
            raise TemporalSupersessionConflictError(
                f"{label} conflicts with a concurrent successor"
            ) from None
        raise


async def _insert_immutable(
    session: AsyncSession,
    model: type[RowType],
    primary_key_name: str,
    values: dict[str, Any],
    label: str,
) -> None:
    primary_key = getattr(model, primary_key_name)
    statement = (
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[primary_key])
        .returning(primary_key)
    )
    try:
        inserted = (await session.execute(statement)).scalar_one_or_none()
        if inserted is not None:
            return
        existing = await session.get(model, values[primary_key_name])
    except IntegrityError:
        raise PersistenceIntegrityError(
            f"persistence integrity constraint rejected {label}"
        ) from None
    if existing is None:
        raise PersistenceIntegrityError(f"conflicting {label} row was not readable")
    differences = [
        field_name
        for field_name, expected in values.items()
        if getattr(existing, field_name) != expected
    ]
    if differences:
        raise SemanticCollisionError(
            f"{label} identity collision with different immutable content"
        )


def _require_equal_record(existing: Any, values: dict[str, Any], label: str) -> None:
    if any(getattr(existing, field_name) != expected for field_name, expected in values.items()):
        raise SemanticCollisionError(
            f"{label} identity collision with different immutable content"
        )


def _required_subtype(row: RowType | None) -> RowType:
    if row is None:
        raise PersistenceIntegrityError("durable instrument subtype row is missing")
    return row


def _advisory_lock_key(provider: str, profile_version: str) -> int:
    digest = stable_hash(
        {
            "entity": "catalogue_provider_profile_lock",
            "provider": provider,
            "profile_version": profile_version,
        }
    ).removeprefix("sha256:")
    value = int(digest[:16], 16)
    return value - 2**64 if value >= 2**63 else value
