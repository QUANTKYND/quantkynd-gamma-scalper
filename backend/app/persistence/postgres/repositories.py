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
from app.market_data.persistence.errors import (
    MarketEventDurableCorruptionError,
)
from app.market_data.persistence.planner import (
    plan_parameter_chunks,
)


EVENT_MEMBERSHIP_IMMUTABLE_FIELDS = (
    "result_id",
    "raw_event_id",
    "event_id",
    "event_ordinal",
)

FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS = (
    "result_id",
    "raw_event_id",
    "failure_id",
    "failure_role",
    "failure_ordinal",
)

OBSERVATION_IMMUTABLE_FIELDS = (
    "event_id",
    "raw_event_id",
    "event_type",
    "subject_id",
    "provider",
    "provider_contract_key",
    "economic_subject_id",
    "provider_mapping_id",
    "contract_version_id",
    "catalogue_version_id",
    "provider_mapping_record_id",
    "contract_version_record_id",
    "catalogue_version_record_id",
    "resolution_market_as_of",
    "resolution_known_as_of",
    "provider_timestamp",
    "exchange_timestamp",
    "received_at",
    "available_at",
    "recorded_at",
    "availability_basis",
    "source_order_scope_id",
    "source_order",
    "normalization_schema_version",
    "normalizer_implementation_version",
    "provider_sequence",
    "supersedes_event_id",
    "payload",
)

FAILURE_IMMUTABLE_FIELDS = (
    "failure_id",
    "result_id",
    "raw_event_id",
    "scope",
    "reason_code",
    "provider_contract_key",
    "segment",
    "safe_detail_code",
    "selected_feed_union",
    "provider_depth_levels_present",
    "field_paths",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "payload",
)

QUOTE_SUBTYPE_TABLE_BY_EVENT_TYPE = {
    "underlying_quote_observation": (
        "underlying_quote_observations"
    ),
    "futures_quote_observation": (
        "futures_quote_observations"
    ),
    "option_quote_observation": (
        "option_quote_observations"
    ),
}

QUOTE_SUBTYPE_IMMUTABLE_FIELDS = (
    "event_id",
    "event_type",
    "subject_id",
    "feed_response_type",
    "request_mode",
    "feed_union",
    "is_snapshot",
    "presence_semantics",
    "numeric_basis",
    "quantity_basis",
    "bid_price",
    "bid_size",
    "ask_price",
    "ask_size",
    "last_price",
    "last_size",
    "last_trade_at",
    "previous_close_price",
    "reported_volume",
    "open_interest",
    "provider_depth_levels_present",
    "normalized_depth_levels",
    "unadopted_depth_level_count",
    "unadopted_schema_paths",
    "present_unadopted_message_paths",
    "secondary_payload_paths_present",
)

STATUS_SUBTYPE_IMMUTABLE_FIELDS = (
    "event_id",
    "event_type",
    "subject_id",
    "segment",
    "provider_status_name",
    "provider_status_numeric",
    "status_is_known",
)


def _rows_match_on_fields(
    existing: dict[str, object],
    proposed: dict[str, object],
    fields: tuple[str, ...],
) -> bool:
    return all(
        existing[field] == proposed[field]
        for field in fields
    )


def _enum_value(value: object | None) -> object | None:
    if value is None:
        return None
    return getattr(value, "value", value)


class PostgresMarketEventRepository:
    def __init__(
        self,
        session,
        require_active,
    ) -> None:
        self._session = session
        self._require_active = require_active

    async def persist_frame_result(
        self,
        command,
        *,
        persistence_recorded_at=None,
    ):
        self._require_active()

        from app.core.hashing import canonical_json
        from app.market_data.persistence.contracts import (
            CANONICAL_IMPLEMENTATION,
            CANONICAL_SCHEMA_VERSION,
            DurableResultIdentity,
            FailureIdentity,
            PersistenceSummary,
        )
        from app.market_data.persistence.errors import (
            NormalizationFailureIdentityConflictError,
            NormalizationResultConflictError,
            NormalizedEventIdentityConflictError,
            RawCaptureIdentityConflictError,
            RawFrameContentMismatchError,
        )
        from app.market_data.persistence.planner import (
            derive_lock_stripes,
        )

        raw = command.raw_frame
        result = command.normalization_result

        if (
            raw.raw_event_id
            != result.raw_frame_identity.raw_event_id
        ):
            raise ValueError(
                "raw frame and result identities differ"
            )

        schema_version = CANONICAL_SCHEMA_VERSION
        implementation_version = CANONICAL_IMPLEMENTATION

        for event in result.accepted_events:
            if (
                event.normalization_schema_version
                != schema_version
                or event.normalizer_implementation_version
                != implementation_version
            ):
                raise ValueError(
                    "normalization result contains mixed "
                    "schema identity"
                )

        result_id = DurableResultIdentity(
            raw.raw_event_id,
            schema_version,
        ).result_id

        failure_items: list[tuple[str, object]] = []
        if result.frame_failure is not None:
            failure_items.append(
                ("frame", result.frame_failure)
            )
        failure_items.extend(
            ("entry", failure)
            for failure in result.entry_failures
        )

        failure_id_items: list[
            tuple[str, object, str]
        ] = []
        for role, failure in failure_items:
            failure_id = FailureIdentity(
                result_id,
                failure.scope.value,
                failure.reason_code,
                failure.provider_contract_key,
                failure.segment,
                payload=failure,
            ).failure_id
            failure_id_items.append(
                (role, failure, failure_id)
            )

        roots = [
            ("raw_frame", raw.raw_event_id),
            ("normalization_result", result_id),
        ]
        roots.extend(
            ("market_observation", event.event_id)
            for event in result.accepted_events
        )
        roots.extend(
            ("market_failure", failure_id)
            for _, _, failure_id in failure_id_items
        )

        for stripe in derive_lock_stripes(roots):
            await self._session.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "CAST(:data14_namespace AS integer), "
                    "CAST(:stripe AS integer)"
                    ")"
                ),
                {
                    "data14_namespace": -1377601296,
                    "stripe": stripe,
                },
            )

        raw_values: dict[str, object] = {
            "raw_event_id": raw.raw_event_id,
            "provider": raw.provider,
            "provider_schema_id": raw.provider_schema_id,
            "provider_schema_sha256": (
                raw.provider_schema_sha256
            ),
            "connection_session_id": (
                raw.connection_session_id
            ),
            "source_order_scope_id": (
                raw.source_order_scope_id
            ),
            "source_order": raw.source_order,
            "frame_bytes": raw.frame_bytes,
            "frame_content_hash": raw.frame_content_hash,
            "received_at": raw.received_at,
            "available_at": raw.available_at,
            "recorded_at": raw.recorded_at,
            "capture_basis": raw.capture_basis.value,
            "source_file_id": raw.source_file_id,
            "source_record_id": raw.source_record_id,
        }

        existing_raw = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        provider,
                        provider_schema_id,
                        provider_schema_sha256,
                        connection_session_id,
                        source_order_scope_id,
                        source_order,
                        frame_bytes,
                        frame_content_hash,
                        received_at,
                        available_at,
                        recorded_at,
                        capture_basis,
                        source_file_id,
                        source_record_id
                    FROM raw_market_frames
                    WHERE raw_event_id = :raw_event_id
                    """
                ),
                {
                    "raw_event_id": raw.raw_event_id,
                },
            )
        ).first()

        if existing_raw is None:
            await self._session.execute(
                text(
                    """
                    INSERT INTO raw_market_frames (
                        raw_event_id,
                        provider,
                        provider_schema_id,
                        provider_schema_sha256,
                        connection_session_id,
                        source_order_scope_id,
                        source_order,
                        frame_bytes,
                        frame_content_hash,
                        received_at,
                        available_at,
                        recorded_at,
                        capture_basis,
                        source_file_id,
                        source_record_id,
                        persistence_recorded_at
                    )
                    VALUES (
                        :raw_event_id,
                        :provider,
                        :provider_schema_id,
                        :provider_schema_sha256,
                        :connection_session_id,
                        :source_order_scope_id,
                        :source_order,
                        :frame_bytes,
                        :frame_content_hash,
                        :received_at,
                        :available_at,
                        :recorded_at,
                        :capture_basis,
                        :source_file_id,
                        :source_record_id,
                        :persistence_recorded_at
                    )
                    """
                ),
                {
                    **raw_values,
                    "persistence_recorded_at": (
                        persistence_recorded_at
                        or raw.recorded_at
                    ),
                },
            )
        else:
            existing_values = dict(
                existing_raw._mapping
            )
            existing_frame_bytes = bytes(
                existing_values["frame_bytes"]
            )

            if (
                existing_frame_bytes != raw.frame_bytes
                or existing_values["frame_content_hash"]
                != raw.frame_content_hash
            ):
                raise RawFrameContentMismatchError(
                    raw.raw_event_id
                )

            immutable_metadata_fields = (
                "provider",
                "provider_schema_id",
                "provider_schema_sha256",
                "connection_session_id",
                "source_order_scope_id",
                "source_order",
                "frame_content_hash",
                "received_at",
                "available_at",
                "recorded_at",
                "capture_basis",
                "source_file_id",
                "source_record_id",
            )

            if not _rows_match_on_fields(
                existing_values,
                raw_values,
                immutable_metadata_fields,
            ):
                raise RawCaptureIdentityConflictError(
                    raw.raw_event_id
                )

        response_type = _enum_value(
            result.response_type
        )
        status = _enum_value(result.status)
        frame_failure_present = (
            result.frame_failure is not None
        )

        result_metadata_projection = {
            "schema": (
                "data-1.4-normalization-result-metadata-v1"
            ),
            "result_id": result_id,
            "raw_event_id": raw.raw_event_id,
            "normalization_schema_version": schema_version,
            "normalizer_implementation_version": (
                implementation_version
            ),
            "response_type": response_type,
            "status": status,
            "decoded_entry_count": (
                result.decoded_entry_count
            ),
            "accepted_entry_count": (
                result.accepted_entry_count
            ),
            "failed_entry_count": (
                result.failed_entry_count
            ),
            "frame_failure_present": frame_failure_present,
            "unadopted_schema_paths": list(
                result.unadopted_schema_paths
            ),
            "present_unadopted_message_paths": list(
                result.present_unadopted_message_paths
            ),
            "secondary_payload_paths_present": list(
                result.secondary_payload_paths_present
            ),
            "full_result_hash": result.full_result_hash,
            "adopted_semantics_hash": (
                result.adopted_semantics_hash
            ),
        }

        result_values: dict[str, object] = {
            key: value
            for key, value
            in result_metadata_projection.items()
            if key != "schema"
        }
        result_values["metadata_payload"] = json.loads(
            canonical_json(result_metadata_projection)
        )

        existing_result = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        result_id,
                        raw_event_id,
                        normalization_schema_version,
                        normalizer_implementation_version,
                        response_type,
                        status,
                        decoded_entry_count,
                        accepted_entry_count,
                        failed_entry_count,
                        frame_failure_present,
                        unadopted_schema_paths,
                        present_unadopted_message_paths,
                        secondary_payload_paths_present,
                        full_result_hash,
                        adopted_semantics_hash,
                        metadata_payload
                    FROM market_normalization_results
                    WHERE result_id = :result_id
                    """
                ),
                {"result_id": result_id},
            )
        ).first()

        if existing_result is None:
            await self._session.execute(
                text(
                    """
                    INSERT INTO market_normalization_results (
                        result_id,
                        raw_event_id,
                        normalization_schema_version,
                        normalizer_implementation_version,
                        response_type,
                        status,
                        decoded_entry_count,
                        accepted_entry_count,
                        failed_entry_count,
                        frame_failure_present,
                        unadopted_schema_paths,
                        present_unadopted_message_paths,
                        secondary_payload_paths_present,
                        full_result_hash,
                        adopted_semantics_hash,
                        metadata_payload,
                        persistence_recorded_at
                    )
                    VALUES (
                        :result_id,
                        :raw_event_id,
                        :normalization_schema_version,
                        :normalizer_implementation_version,
                        :response_type,
                        :status,
                        :decoded_entry_count,
                        :accepted_entry_count,
                        :failed_entry_count,
                        :frame_failure_present,
                        :unadopted_schema_paths,
                        :present_unadopted_message_paths,
                        :secondary_payload_paths_present,
                        :full_result_hash,
                        :adopted_semantics_hash,
                        CAST(:metadata_payload AS jsonb),
                        :persistence_recorded_at
                    )
                    """
                ),
                {
                    **result_values,
                    "metadata_payload": canonical_json(
                        result_values["metadata_payload"]
                    ),
                    "persistence_recorded_at": (
                        persistence_recorded_at
                        or raw.recorded_at
                    ),
                },
            )
            result_inserted = True
        else:
            if dict(existing_result._mapping) != result_values:
                raise NormalizationResultConflictError(
                    result_id
                )
            result_inserted = False

        event_values = [
            self._observation_values(
                event,
                raw,
                canonical_json,
            )
            for event in result.accepted_events
        ]
        event_values_by_id = {
            values["event_id"]: values
            for values in event_values
        }

        subtype_values_by_table: dict[
            str,
            dict[str, dict[str, object]],
        ] = {}
        for event in result.accepted_events:
            subtype_table, subtype_values = (
                self._subtype_values(event)
            )
            subtype_values_by_table.setdefault(
                subtype_table,
                {},
            )[event.event_id] = subtype_values

        existing_observations = (
            await self._fetch_existing_rows(
                "market_observations",
                "event_id",
                tuple(event_values_by_id),
                OBSERVATION_IMMUTABLE_FIELDS,
            )
        )

        missing_event_rows: list[
            dict[str, object]
        ] = []
        for event_id, values in event_values_by_id.items():
            existing = existing_observations.get(event_id)
            if existing is None:
                missing_event_rows.append(values)
                continue
            if not _rows_match_on_fields(
                existing,
                values,
                OBSERVATION_IMMUTABLE_FIELDS,
            ):
                raise NormalizedEventIdentityConflictError(
                    event_id
                )

        if result_inserted and existing_observations:
            raise MarketEventDurableCorruptionError(
                "new result encountered pre-existing "
                "market observation rows"
            )
        if not result_inserted and missing_event_rows:
            raise MarketEventDurableCorruptionError(
                "existing result is missing market "
                "observation rows"
            )

        existing_subtypes_by_table: dict[
            str,
            dict[object, dict[str, object]],
        ] = {}
        for table_name, values_by_id in (
            subtype_values_by_table.items()
        ):
            immutable_fields = (
                STATUS_SUBTYPE_IMMUTABLE_FIELDS
                if table_name
                == "market_segment_status_observations"
                else QUOTE_SUBTYPE_IMMUTABLE_FIELDS
            )
            existing_subtypes_by_table[table_name] = (
                await self._fetch_existing_rows(
                    table_name,
                    "event_id",
                    tuple(values_by_id),
                    immutable_fields,
                )
            )

        missing_subtypes_by_table: dict[
            str,
            list[dict[str, object]],
        ] = {}
        for table_name, values_by_id in (
            subtype_values_by_table.items()
        ):
            immutable_fields = (
                STATUS_SUBTYPE_IMMUTABLE_FIELDS
                if table_name
                == "market_segment_status_observations"
                else QUOTE_SUBTYPE_IMMUTABLE_FIELDS
            )
            existing_subtypes = (
                existing_subtypes_by_table[table_name]
            )
            for event_id, values in values_by_id.items():
                existing_subtype = existing_subtypes.get(
                    event_id
                )
                parent_exists = (
                    event_id in existing_observations
                )

                if existing_subtype is None:
                    if parent_exists:
                        raise MarketEventDurableCorruptionError(
                            "market observation registry row "
                            "is missing its typed subtype: "
                            f"{event_id}"
                        )
                    missing_subtypes_by_table.setdefault(
                        table_name,
                        [],
                    ).append(values)
                    continue

                if not parent_exists:
                    raise MarketEventDurableCorruptionError(
                        "typed market observation subtype "
                        "exists without its registry row: "
                        f"{event_id}"
                    )

                if not _rows_match_on_fields(
                    existing_subtype,
                    values,
                    immutable_fields,
                ):
                    raise NormalizedEventIdentityConflictError(
                        event_id
                    )

        await self._bulk_insert_json_rows(
            "market_observations",
            missing_event_rows,
            payload_cast=True,
        )

        for table_name in sorted(
            missing_subtypes_by_table
        ):
            await self._bulk_insert_rows(
                table_name,
                missing_subtypes_by_table[table_name],
            )

        event_memberships = [
            {
                "result_id": result_id,
                "raw_event_id": raw.raw_event_id,
                "event_id": event.event_id,
                "event_ordinal": ordinal,
            }
            for ordinal, event in enumerate(
                result.accepted_events
            )
        ]

        if result_inserted:
            await self._bulk_insert_rows(
                "market_normalization_result_events",
                event_memberships,
            )
        else:
            await self._require_exact_event_memberships(
                result_id,
                event_memberships,
                NormalizedEventIdentityConflictError,
                NormalizationResultConflictError,
            )

        failure_values: list[dict[str, object]] = []
        failure_memberships: list[
            dict[str, object]
        ] = []
        role_ordinals = {
            "frame": 0,
            "entry": 0,
        }

        for role, failure, failure_id in failure_id_items:
            payload = json.loads(
                canonical_json(failure)
            )
            values = {
                "failure_id": failure_id,
                "result_id": result_id,
                "raw_event_id": raw.raw_event_id,
                "scope": failure.scope.value,
                "reason_code": failure.reason_code,
                "provider_contract_key": (
                    failure.provider_contract_key
                ),
                "segment": failure.segment,
                "safe_detail_code": (
                    failure.safe_detail_code
                ),
                "selected_feed_union": _enum_value(
                    failure.selected_feed_union
                ),
                "provider_depth_levels_present": (
                    failure.provider_depth_levels_present
                ),
                "field_paths": list(failure.field_paths),
                "unadopted_schema_paths": list(
                    failure.unadopted_schema_paths
                ),
                "present_unadopted_message_paths": list(
                    failure.present_unadopted_message_paths
                ),
                "payload": payload,
            }
            failure_values.append(values)
            failure_memberships.append(
                {
                    "result_id": result_id,
                    "raw_event_id": raw.raw_event_id,
                    "failure_id": failure_id,
                    "failure_role": role,
                    "failure_ordinal": (
                        role_ordinals[role]
                    ),
                }
            )
            role_ordinals[role] += 1

        failure_values_by_id = {
            values["failure_id"]: values
            for values in failure_values
        }
        existing_failures = await self._fetch_existing_rows(
            "market_normalization_failures",
            "failure_id",
            tuple(failure_values_by_id),
            FAILURE_IMMUTABLE_FIELDS,
        )

        missing_failure_rows: list[
            dict[str, object]
        ] = []
        for failure_id, values in failure_values_by_id.items():
            existing = existing_failures.get(failure_id)
            if existing is None:
                missing_failure_rows.append(values)
                continue
            if not _rows_match_on_fields(
                existing,
                values,
                FAILURE_IMMUTABLE_FIELDS,
            ):
                raise (
                    NormalizationFailureIdentityConflictError(
                        failure_id
                    )
                )

        if result_inserted and existing_failures:
            raise MarketEventDurableCorruptionError(
                "new result encountered pre-existing "
                "normalization failure rows"
            )

        await self._bulk_insert_json_rows(
            "market_normalization_failures",
            missing_failure_rows,
            payload_cast=True,
        )

        if result_inserted:
            await self._bulk_insert_rows(
                "market_normalization_result_failures",
                failure_memberships,
            )
        else:
            await self._require_exact_failure_memberships(
                result_id,
                failure_memberships,
                NormalizationFailureIdentityConflictError,
                NormalizationResultConflictError,
            )

        return PersistenceSummary(
            result_id=result_id,
            inserted=result_inserted,
            accepted_count=len(result.accepted_events),
            failure_count=(
                len(result.entry_failures)
                + int(result.frame_failure is not None)
            ),
        )

    @staticmethod
    def _observation_values(
        event,
        raw,
        canonical_json,
    ) -> dict[str, object]:
        event_type = event.identity.event_type
        is_quote = hasattr(event, "event_time")

        if is_quote:
            subject = event.subject
            event_time = event.event_time
            catalogue_version_id = (
                subject.contract_version.catalogue_version_id
            )
            provider_contract_key = (
                event.provider_contract_key
            )
            economic_subject_id = (
                event.economic_subject_id
            )
            provider_mapping_id = (
                event.provider_mapping_id
            )
            contract_version_id = (
                event.contract_version_id
            )
            resolution_market_as_of = (
                subject.resolution_market_as_of
            )
            resolution_known_as_of = (
                subject.resolution_known_as_of
            )
            provider_timestamp = (
                event_time.provider_timestamp
            )
            exchange_timestamp = (
                event_time.exchange_timestamp
            )
            received_at = event_time.received_at
            available_at = event_time.available_at
            recorded_at = event_time.recorded_at
            availability_basis = (
                event_time.availability_basis.value
            )
            supersedes_event_id = (
                event.supersedes_event_id
            )
        else:
            catalogue_version_id = None
            provider_contract_key = None
            economic_subject_id = None
            provider_mapping_id = None
            contract_version_id = None
            resolution_market_as_of = None
            resolution_known_as_of = None
            provider_timestamp = event.provider_timestamp
            exchange_timestamp = None
            received_at = event.received_at
            available_at = event.available_at
            recorded_at = event.recorded_at
            availability_basis = (
                "historical_import"
                if raw.capture_basis.value
                == "historical_import"
                else "received"
            )
            supersedes_event_id = None

        return {
            "event_id": event.event_id,
            "raw_event_id": event.raw_event_id,
            "event_type": event_type,
            "subject_id": event.identity.subject_id,
            "provider": event.provider,
            "provider_contract_key": (
                provider_contract_key
            ),
            "economic_subject_id": economic_subject_id,
            "provider_mapping_id": provider_mapping_id,
            "contract_version_id": contract_version_id,
            "catalogue_version_id": catalogue_version_id,
            # Step 5 resolves and binds these exact record IDs.
            "provider_mapping_record_id": None,
            "contract_version_record_id": None,
            "catalogue_version_record_id": None,
            "resolution_market_as_of": (
                resolution_market_as_of
            ),
            "resolution_known_as_of": (
                resolution_known_as_of
            ),
            "provider_timestamp": provider_timestamp,
            "exchange_timestamp": exchange_timestamp,
            "received_at": received_at,
            "available_at": available_at,
            "recorded_at": recorded_at,
            "availability_basis": availability_basis,
            "source_order_scope_id": (
                event.source_order_scope_id
            ),
            "source_order": event.source_order,
            "normalization_schema_version": (
                event.normalization_schema_version
            ),
            "normalizer_implementation_version": (
                event.normalizer_implementation_version
            ),
            "provider_sequence": None,
            "supersedes_event_id": supersedes_event_id,
            "payload": json.loads(canonical_json(event)),
        }

    @staticmethod
    def _subtype_values(
        event,
    ) -> tuple[str, dict[str, object]]:
        event_type = event.identity.event_type
        quote_table = (
            QUOTE_SUBTYPE_TABLE_BY_EVENT_TYPE.get(
                event_type
            )
        )

        if quote_table is not None:
            return quote_table, {
                "event_id": event.event_id,
                "event_type": event_type,
                "subject_id": event.identity.subject_id,
                "feed_response_type": _enum_value(
                    event.feed_response_type
                ),
                "request_mode": _enum_value(
                    event.request_mode
                ),
                "feed_union": _enum_value(
                    event.feed_union
                ),
                "is_snapshot": event.is_snapshot,
                "presence_semantics": (
                    event.presence_semantics
                ),
                "numeric_basis": event.numeric_basis,
                "quantity_basis": event.quantity_basis,
                "bid_price": event.bid_price,
                "bid_size": event.bid_size,
                "ask_price": event.ask_price,
                "ask_size": event.ask_size,
                "last_price": event.last_price,
                "last_size": event.last_size,
                "last_trade_at": event.last_trade_at,
                "previous_close_price": (
                    event.previous_close_price
                ),
                "reported_volume": event.reported_volume,
                "open_interest": event.open_interest,
                "provider_depth_levels_present": (
                    event.provider_depth_levels_present
                ),
                "normalized_depth_levels": (
                    event.normalized_depth_levels
                ),
                "unadopted_depth_level_count": (
                    event.unadopted_depth_level_count
                ),
                "unadopted_schema_paths": list(
                    event.unadopted_schema_paths
                ),
                "present_unadopted_message_paths": list(
                    event.present_unadopted_message_paths
                ),
                "secondary_payload_paths_present": list(
                    event.secondary_payload_paths_present
                ),
            }

        if event_type == "market_segment_status_observation":
            return "market_segment_status_observations", {
                "event_id": event.event_id,
                "event_type": event_type,
                "subject_id": event.identity.subject_id,
                "segment": event.segment,
                "provider_status_name": (
                    event.provider_status_name
                ),
                "provider_status_numeric": (
                    event.provider_status_numeric
                ),
                "status_is_known": event.status_is_known,
            }

        raise ValueError(
            "unsupported market observation subtype: "
            f"{event_type}"
        )

    async def _require_exact_event_memberships(
        self,
        result_id: str,
        proposed: list[dict[str, object]],
        event_conflict,
        result_conflict,
    ) -> None:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        result_id,
                        raw_event_id,
                        event_id,
                        event_ordinal
                    FROM market_normalization_result_events
                    WHERE result_id = :result_id
                    ORDER BY event_ordinal
                    """
                ),
                {"result_id": result_id},
            )
        ).all()

        existing = [
            dict(row._mapping)
            for row in rows
        ]
        if len(existing) != len(proposed):
            raise result_conflict(result_id)

        for actual, expected in zip(
            existing,
            proposed,
            strict=True,
        ):
            if not _rows_match_on_fields(
                actual,
                expected,
                EVENT_MEMBERSHIP_IMMUTABLE_FIELDS,
            ):
                raise event_conflict(
                    expected["event_id"]
                )

    async def _require_exact_failure_memberships(
        self,
        result_id: str,
        proposed: list[dict[str, object]],
        failure_conflict,
        result_conflict,
    ) -> None:
        rows = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        result_id,
                        raw_event_id,
                        failure_id,
                        failure_role,
                        failure_ordinal
                    FROM market_normalization_result_failures
                    WHERE result_id = :result_id
                    ORDER BY
                        CASE failure_role
                            WHEN 'frame' THEN 0
                            ELSE 1
                        END,
                        failure_ordinal
                    """
                ),
                {"result_id": result_id},
            )
        ).all()

        existing = [
            dict(row._mapping)
            for row in rows
        ]
        if len(existing) != len(proposed):
            raise result_conflict(result_id)

        for actual, expected in zip(
            existing,
            proposed,
            strict=True,
        ):
            if not _rows_match_on_fields(
                actual,
                expected,
                FAILURE_MEMBERSHIP_IMMUTABLE_FIELDS,
            ):
                raise failure_conflict(
                    expected["failure_id"]
                )

    async def _bulk_insert_rows(
        self,
        table,
        rows,
    ) -> None:
        if not rows:
            return

        columns = tuple(rows[0].keys())
        chunks = plan_parameter_chunks(
            len(rows),
            len(columns),
        )
        for chunk in chunks:
            batch = rows[
                chunk.offset:
                chunk.offset + chunk.size
            ]
            await self._session.execute(
                text(
                    f"INSERT INTO {table} "
                    f"({', '.join(columns)}) VALUES "
                    f"({', '.join(f':{name}' for name in columns)})"
                ),
                batch,
            )

    async def _bulk_insert_json_rows(
        self,
        table,
        rows,
        *,
        payload_cast: bool = False,
    ) -> None:
        if not rows:
            return

        columns = tuple(rows[0].keys())
        chunks = plan_parameter_chunks(
            len(rows),
            len(columns),
        )
        for chunk in chunks:
            batch = rows[
                chunk.offset:
                chunk.offset + chunk.size
            ]
            parameters: list[dict[str, object]] = []
            for row in batch:
                values = dict(row)
                if payload_cast:
                    values["payload"] = json.dumps(
                        values["payload"],
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                parameters.append(values)

            inserts = ", ".join(
                "CAST(:payload AS jsonb)"
                if column == "payload"
                else f":{column}"
                for column in columns
            )
            await self._session.execute(
                text(
                    f"INSERT INTO {table} "
                    f"({', '.join(columns)}) VALUES "
                    f"({inserts})"
                ),
                parameters,
            )

    async def _fetch_existing_rows(
        self,
        table: str,
        key_name: str,
        identifiers: tuple[object, ...],
        selected_columns: tuple[str, ...],
    ) -> dict[object, dict[str, object]]:
        unique_identifiers = tuple(
            dict.fromkeys(identifiers)
        )
        if not unique_identifiers:
            return {}

        results: dict[
            object,
            dict[str, object],
        ] = {}

        for chunk in plan_parameter_chunks(
            len(unique_identifiers),
            parameters_per_item=1,
        ):
            batch = unique_identifiers[
                chunk.offset:
                chunk.offset + chunk.size
            ]
            parameters = {
                f"id_{index}": value
                for index, value in enumerate(batch)
            }
            placeholders = ", ".join(
                f":id_{index}"
                for index in range(len(batch))
            )

            rows = await self._session.execute(
                text(
                    f"SELECT {', '.join(selected_columns)} "
                    f"FROM {table} "
                    f"WHERE {key_name} IN ({placeholders})"
                ),
                parameters,
            )

            for row in rows:
                values = dict(row._mapping)
                durable_key = values[key_name]

                if durable_key in results:
                    raise MarketEventDurableCorruptionError(
                        "duplicate durable key returned for "
                        f"{table}.{key_name}: {durable_key}"
                    )

                results[durable_key] = values

        return results

    async def get_result(
        self,
        raw_event_id,
        normalization_schema_version,
    ):
        self._require_active()
        row = await self._session.execute(
            text(
                """
                SELECT *
                FROM market_normalization_results
                WHERE raw_event_id = :raw_event_id
                  AND normalization_schema_version = :schema
                """
            ),
            {
                "raw_event_id": raw_event_id,
                "schema": normalization_schema_version,
            },
        )
        return row.first()

    async def get_raw_frame_metadata(
        self,
        raw_event_id: str,
    ):
        self._require_active()
        row = await self._session.execute(
            text(
                """
                SELECT
                    raw_event_id,
                    frame_content_hash,
                    source_order,
                    persistence_recorded_at
                FROM raw_market_frames
                WHERE raw_event_id = :raw_event_id
                """
            ),
            {"raw_event_id": raw_event_id},
        )
        return row.first()

    async def get_raw_frame(
        self,
        raw_event_id,
    ):
        self._require_active()
        row = await self._session.execute(
            text(
                """
                SELECT *
                FROM raw_market_frames
                WHERE raw_event_id = :raw_event_id
                """
            ),
            {"raw_event_id": raw_event_id},
        )
        return row.first()

    async def get_event(
        self,
        event_id,
        normalization_schema_version,
    ):
        self._require_active()
        row = await self._session.execute(
            text(
                """
                SELECT o.*
                FROM market_observations AS o
                JOIN market_normalization_result_events AS m
                  ON m.event_id = o.event_id
                JOIN market_normalization_results AS r
                  ON r.result_id = m.result_id
                WHERE o.event_id = :event_id
                  AND o.normalization_schema_version = :schema
                  AND r.normalization_schema_version = :schema
                """
            ),
            {
                "event_id": event_id,
                "schema": normalization_schema_version,
            },
        )
        return row.first()

    async def load_result_aggregate(
        self,
        raw_event_id,
        normalization_schema_version,
    ):
        self._require_active()
        result = await self.get_result(
            raw_event_id,
            normalization_schema_version,
        )
        if result is None:
            return None

        events = (
            await self._session.execute(
                text(
                    """
                    SELECT o.*
                    FROM market_normalization_result_events AS m
                    JOIN market_observations AS o
                      ON o.event_id = m.event_id
                    WHERE m.result_id = :result_id
                    ORDER BY m.event_ordinal
                    """
                ),
                {"result_id": result.result_id},
            )
        ).all()

        failures = (
            await self._session.execute(
                text(
                    """
                    SELECT
                        f.*,
                        m.failure_role,
                        m.failure_ordinal
                    FROM market_normalization_result_failures AS m
                    JOIN market_normalization_failures AS f
                      ON f.failure_id = m.failure_id
                    WHERE m.result_id = :result_id
                    ORDER BY
                        CASE m.failure_role
                            WHEN 'frame' THEN 0
                            ELSE 1
                        END,
                        m.failure_ordinal
                    """
                ),
                {"result_id": result.result_id},
            )
        ).all()

        return {
            "result": result,
            "events": tuple(events),
            "failures": tuple(failures),
        }

    async def scan_normalization_results(
        self,
        normalization_schema_version,
        cursor=None,
        limit=100,
    ):
        self._require_active()
        rows = await self._session.execute(
            text(
                """
                SELECT *
                FROM market_normalization_results
                WHERE normalization_schema_version = :schema
                  AND (
                    :cursor IS NULL
                    OR result_id > :cursor
                  )
                ORDER BY result_id
                LIMIT :limit
                """
            ),
            {
                "schema": normalization_schema_version,
                "cursor": cursor,
                "limit": limit,
            },
        )
        return tuple(rows.all())

    async def list_subject_observations(
        self,
        normalization_schema_version,
        subject_id,
        limit=100,
    ):
        self._require_active()
        rows = await self._session.execute(
            text(
                """
                SELECT DISTINCT o.*
                FROM market_observations AS o
                JOIN market_normalization_result_events AS m
                  ON m.event_id = o.event_id
                JOIN market_normalization_results AS r
                  ON r.result_id = m.result_id
                WHERE o.normalization_schema_version = :schema
                  AND r.normalization_schema_version = :schema
                  AND o.subject_id = :subject_id
                ORDER BY o.event_id
                LIMIT :limit
                """
            ),
            {
                "schema": normalization_schema_version,
                "subject_id": subject_id,
                "limit": limit,
            },
        )
        return tuple(rows.all())

    async def list_provider_status(
        self,
        normalization_schema_version,
        provider,
        limit=100,
    ):
        self._require_active()
        rows = await self._session.execute(
            text(
                """
                SELECT DISTINCT
                    o.*,
                    s.segment,
                    s.provider_status_name,
                    s.provider_status_numeric,
                    s.status_is_known
                FROM market_observations AS o
                JOIN market_segment_status_observations AS s
                  ON s.event_id = o.event_id
                 AND s.event_type = o.event_type
                 AND s.subject_id = o.subject_id
                JOIN market_normalization_result_events AS m
                  ON m.event_id = o.event_id
                JOIN market_normalization_results AS r
                  ON r.result_id = m.result_id
                WHERE o.normalization_schema_version = :schema
                  AND r.normalization_schema_version = :schema
                  AND o.provider = :provider
                ORDER BY
                    o.provider_timestamp,
                    o.event_id
                LIMIT :limit
                """
            ),
            {
                "schema": normalization_schema_version,
                "provider": provider,
                "limit": limit,
            },
        )
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
