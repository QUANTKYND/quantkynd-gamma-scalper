from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.core.hashing import stable_hash
from app.instruments.catalogue import CatalogueVersion
from app.instruments.catalogue_parser import (
    ParsedCatalogueArtifact,
    ParsedCatalogueRow,
    parse_json_array_rows,
)
from app.instruments.identity import (
    ExerciseStyle,
    FuturesContractIdentity,
    FuturesContractVersion,
    InstrumentType,
    OptionContractIdentity,
    OptionContractVersion,
    OptionSide,
    ProviderContractMapping,
    SettlementType,
    TradingStatus,
    UnderlyingInstrumentIdentity,
    UnderlyingInstrumentVersion,
)
from app.instruments.provider_catalogue import (
    CatalogueConflictError,
    CatalogueIngestionDisposition,
    CatalogueInstrumentKind,
    CatalogueMembership,
    CatalogueNormalizationError,
    CatalogueRowOutcome,
    NormalizedCatalogueItem,
    normalized_catalogue_hash,
    source_row_occurrence_id,
    source_row_semantic_id,
)


PROFILE_VERSION = "upstox-nse-nifty-index-derivatives-v1"
PROVIDER = "upstox"
MEDIA_TYPE = "application/json"
COMPRESSION = "gzip"
SOURCE_SCHEMA_VERSION = "upstox-bod-nse-json-v1"
NORMALIZER_VERSION = "upstox-nse-nifty-index-derivatives-v1"
UNDERLYING_KEY = "NSE_INDEX|Nifty 50"
CANONICAL_SYMBOL = "NIFTY_50"
EXCHANGE = "NSE"
CURRENCY = "INR"
MULTIPLIER = Decimal("1")
KOLKATA = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class UpstoxCataloguePlan:
    catalogue: CatalogueVersion
    underlying: UnderlyingInstrumentIdentity
    items: tuple[NormalizedCatalogueItem, ...]
    outcomes: tuple[CatalogueRowOutcome, ...]
    memberships: tuple[CatalogueMembership, ...]
    normalized_catalogue_hash: str
    physical_row_count: int
    accepted_unique_count: int
    exact_duplicate_count: int
    excluded_count: int
    field_fingerprint: str


@dataclass(frozen=True)
class ProfileScan:
    underlying: UnderlyingInstrumentIdentity
    physical_row_count: int
    field_fingerprint: str


@dataclass(frozen=True)
class AcceptedProjection:
    row: ParsedCatalogueRow
    projection: dict[str, object]


def build_upstox_nifty_catalogue_plan(
    *,
    artifact: ParsedCatalogueArtifact,
    source_artifact_id: str,
    effective_from: datetime,
    effective_until: datetime | None,
    recorded_at: datetime,
    ingestion_run_id: str,
) -> UpstoxCataloguePlan:
    scan = _scan_profile(artifact)
    excluded = 0
    duplicate_count = 0
    seen_semantic_rows: set[str] = set()
    accepted_provider_keys: dict[str, str] = {}
    accepted_projections: list[AcceptedProjection] = []
    outcomes: list[CatalogueRowOutcome] = []
    for row in parse_json_array_rows(artifact.decompressed_path):
        semantic_id = source_row_semantic_id(PROVIDER, PROFILE_VERSION, row.raw_row_hash)
        occurrence_id = source_row_occurrence_id(
            source_artifact_id,
            row.physical_row_number,
            row.raw_row_hash,
        )
        if not _is_profile_candidate(row.raw):
            excluded += 1
            outcomes.append(
                CatalogueRowOutcome(
                    ingestion_run_id=ingestion_run_id,
                    source_row_occurrence_id=occurrence_id,
                    source_row_semantic_id=semantic_id,
                    physical_row_number=row.physical_row_number,
                    raw_row_hash=row.raw_row_hash,
                    normalized_row_hash=None,
                    provider_contract_key=_optional_text(row.raw, "instrument_key"),
                    disposition=CatalogueIngestionDisposition.EXCLUDED_BY_PROFILE,
                    reason_codes=("excluded_by_profile",),
                )
            )
            continue
        if semantic_id in seen_semantic_rows:
            duplicate_count += 1
            outcomes.append(
                CatalogueRowOutcome(
                    ingestion_run_id=ingestion_run_id,
                    source_row_occurrence_id=occurrence_id,
                    source_row_semantic_id=semantic_id,
                    physical_row_number=row.physical_row_number,
                    raw_row_hash=row.raw_row_hash,
                    normalized_row_hash=None,
                    provider_contract_key=_required_text(row.raw, "instrument_key"),
                    disposition=CatalogueIngestionDisposition.EXACT_DUPLICATE,
                    reason_codes=("exact_duplicate",),
                )
            )
            continue
        seen_semantic_rows.add(semantic_id)
        projection = _projection(row.raw, scan.underlying.instrument_id)
        provider_key = str(projection["provider_contract_key"])
        prior_raw_hash = accepted_provider_keys.get(provider_key)
        if prior_raw_hash is not None and prior_raw_hash != row.raw_row_hash:
            raise CatalogueConflictError("duplicate provider key with non-identical raw content")
        accepted_provider_keys[provider_key] = row.raw_row_hash
        accepted_projections.append(AcceptedProjection(row, projection))
    catalogue_hash = normalized_catalogue_hash(tuple(item.projection for item in accepted_projections))
    catalogue = CatalogueVersion(
        provider=_catalogue_scope(),
        source_content_hash=catalogue_hash,
        catalogue_schema_version=1,
        effective_from=effective_from,
        effective_until=effective_until,
        published_at=None,
        recorded_at=recorded_at,
        row_count=len(accepted_projections),
    )
    items: list[NormalizedCatalogueItem] = []
    memberships: list[CatalogueMembership] = []
    for accepted_projection in accepted_projections:
        row = accepted_projection.row
        projection = accepted_projection.projection
        item = _item_from_projection(
            row=row,
            projection=projection,
            source_artifact_id=source_artifact_id,
            catalogue=catalogue,
            underlying=scan.underlying,
            effective_from=effective_from,
            effective_until=effective_until,
            recorded_at=recorded_at,
        )
        items.append(item)
        accepted = CatalogueRowOutcome(
            ingestion_run_id=ingestion_run_id,
            source_row_occurrence_id=item.source_row_occurrence_id,
            source_row_semantic_id=item.source_row_semantic_id,
            physical_row_number=item.physical_row_number,
            raw_row_hash=item.raw_row_hash,
            normalized_row_hash=item.normalized_row_hash,
            provider_contract_key=item.provider_contract_key,
            disposition=CatalogueIngestionDisposition.ACCEPTED,
            reason_codes=(),
            instrument_id=item.instrument_id,
            version_id=item.version_id,
            mapping_id=item.mapping_id,
        )
        outcomes.append(accepted)
        memberships.append(
            CatalogueMembership(
                catalogue_version_id=catalogue.catalogue_version_id,
                row_outcome_id=accepted.row_outcome_id,
                source_row_occurrence_id=item.source_row_occurrence_id,
                source_row_semantic_id=item.source_row_semantic_id,
                instrument_id=item.instrument_id,
                version_id=item.version_id,
                mapping_id=item.mapping_id,
                provider_contract_key=item.provider_contract_key,
                raw_row_hash=item.raw_row_hash,
                normalized_row_hash=item.normalized_row_hash,
            )
        )
    return UpstoxCataloguePlan(
        catalogue=catalogue,
        underlying=scan.underlying,
        items=tuple(sorted(items, key=lambda item: (item.instrument_id, item.provider_contract_key))),
        outcomes=tuple(sorted(outcomes, key=lambda item: item.physical_row_number)),
        memberships=tuple(sorted(memberships, key=lambda item: item.membership_id)),
        normalized_catalogue_hash=catalogue_hash,
        physical_row_count=scan.physical_row_count,
        accepted_unique_count=len(memberships),
        exact_duplicate_count=duplicate_count,
        excluded_count=excluded,
        field_fingerprint=scan.field_fingerprint,
    )


def bind_upstox_catalogue_plan_recorded_at(
    plan: UpstoxCataloguePlan,
    recorded_at: datetime,
) -> UpstoxCataloguePlan:
    catalogue = replace(plan.catalogue, recorded_at=recorded_at)
    items = tuple(
        replace(
            item,
            version=replace(item.version, recorded_at=recorded_at),
            mapping=replace(item.mapping, recorded_at=recorded_at),
        )
        for item in plan.items
    )
    rebound = replace(plan, catalogue=catalogue, items=items)
    if rebound.catalogue.catalogue_version_id != plan.catalogue.catalogue_version_id:
        raise CatalogueConflictError("catalogue semantic identity changed during time binding")
    for prior, current in zip(plan.items, rebound.items, strict=True):
        if prior.version_id != current.version.version_id or prior.mapping_id != current.mapping.mapping_id:
            raise CatalogueConflictError("catalogue item semantic identity changed during time binding")
    return rebound


def _scan_profile(artifact: ParsedCatalogueArtifact) -> ProfileScan:
    underlying: UnderlyingInstrumentIdentity | None = None
    underlying_raw_hash: str | None = None
    physical_count = 0
    fields: set[str] = set()
    for row in parse_json_array_rows(artifact.decompressed_path):
        physical_count += 1
        fields.update(row.raw)
        if row.raw.get("instrument_key") == UNDERLYING_KEY:
            if underlying is not None:
                if row.raw_row_hash == underlying_raw_hash:
                    continue
                raise CatalogueConflictError("duplicate approved underlying row")
            underlying = _normalize_underlying(row.raw)
            underlying_raw_hash = row.raw_row_hash
    if underlying is None:
        raise CatalogueNormalizationError("missing approved Upstox Nifty 50 underlying row")
    return ProfileScan(
        underlying=underlying,
        physical_row_count=physical_count,
        field_fingerprint=stable_hash(
            {
                "entity": "upstox_catalogue_field_fingerprint",
                "fields": frozenset(fields),
            }
        ),
    )


def _normalize_underlying(row: dict[str, object]) -> UnderlyingInstrumentIdentity:
    if _required_text(row, "instrument_key") != UNDERLYING_KEY:
        raise CatalogueNormalizationError("unexpected underlying instrument key")
    segment = _required_text(row, "segment")
    exchange = _required_text(row, "exchange")
    if segment != "NSE_INDEX" or exchange != EXCHANGE:
        raise CatalogueNormalizationError("underlying row is outside the approved profile")
    if _required_text(row, "instrument_type") != "INDEX":
        raise CatalogueNormalizationError("underlying instrument_type must be INDEX")
    return UnderlyingInstrumentIdentity(EXCHANGE, CANONICAL_SYMBOL, InstrumentType.INDEX, CURRENCY)


def _is_profile_candidate(row: dict[str, object]) -> bool:
    key = _optional_text(row, "instrument_key")
    return key == UNDERLYING_KEY or _optional_text(row, "underlying_key") == UNDERLYING_KEY


def _projection(row: dict[str, object], underlying_instrument_id: str) -> dict[str, object]:
    key = _required_text(row, "instrument_key")
    if key == UNDERLYING_KEY:
        return {
            "kind": "underlying",
            "provider_contract_key": key,
            "exchange": EXCHANGE,
            "canonical_symbol": CANONICAL_SYMBOL,
            "instrument_type": "index",
            "currency": CURRENCY,
            "lot_size": _positive_int(row, "lot_size"),
            "tick_size": _tick_size(row),
            "display_symbol": _required_text(row, "trading_symbol"),
            "trading_status": "active",
        }
    _validate_derivative(row)
    instrument_type = _required_text(row, "instrument_type")
    if instrument_type not in {"FUT", "CE", "PE"}:
        raise CatalogueNormalizationError("derivative instrument_type must be FUT, CE, or PE")
    base = {
        "provider_contract_key": key,
        "exchange": EXCHANGE,
        "underlying_instrument_id": underlying_instrument_id,
        "expiry": _expiry(row),
        "settlement_type": "cash",
        "multiplier": MULTIPLIER,
        "currency": CURRENCY,
        "lot_size": _positive_int(row, "lot_size"),
        "tick_size": _tick_size(row),
        "display_symbol": _required_text(row, "trading_symbol"),
        "trading_status": "active",
    }
    if instrument_type == "FUT":
        return {"kind": "future", **base}
    option_side = "call" if instrument_type == "CE" else "put"
    return {
        "kind": "option",
        **base,
        "strike": _positive_decimal(row, "strike_price"),
        "option_side": option_side,
        "exercise_style": "european",
    }


def _item_from_projection(
    *,
    row,
    projection: dict[str, object],
    source_artifact_id: str,
    catalogue: CatalogueVersion,
    underlying: UnderlyingInstrumentIdentity,
    effective_from: datetime,
    effective_until: datetime | None,
    recorded_at: datetime,
) -> NormalizedCatalogueItem:
    semantic_id = source_row_semantic_id(PROVIDER, PROFILE_VERSION, row.raw_row_hash)
    occurrence_id = source_row_occurrence_id(source_artifact_id, row.physical_row_number, row.raw_row_hash)
    provider_key = str(projection["provider_contract_key"])
    tick_size = projection["tick_size"]
    lot_size = projection["lot_size"]
    common = {
        "valid_from": effective_from,
        "valid_until": effective_until,
        "lot_size": lot_size,
        "tick_size": tick_size,
        "display_symbol": str(projection["display_symbol"]),
        "trading_status": TradingStatus.ACTIVE,
        "catalogue_version_id": catalogue.catalogue_version_id,
        "recorded_at": recorded_at,
    }
    if projection["kind"] == "underlying":
        instrument = underlying
        version = UnderlyingInstrumentVersion(instrument_id=underlying.instrument_id, **common)
        kind = CatalogueInstrumentKind.UNDERLYING
    elif projection["kind"] == "future":
        instrument = FuturesContractIdentity(
            exchange=EXCHANGE,
            underlying_instrument_id=underlying.instrument_id,
            expiry=projection["expiry"],
            settlement_type=SettlementType.CASH,
            multiplier=MULTIPLIER,
            currency=CURRENCY,
        )
        version = FuturesContractVersion(contract_id=instrument.contract_id, **common)
        kind = CatalogueInstrumentKind.FUTURE
    else:
        instrument = OptionContractIdentity(
            exchange=EXCHANGE,
            underlying_instrument_id=underlying.instrument_id,
            expiry=projection["expiry"],
            strike=projection["strike"],
            option_side=OptionSide(projection["option_side"]),
            exercise_style=ExerciseStyle.EUROPEAN,
            settlement_type=SettlementType.CASH,
            multiplier=MULTIPLIER,
            currency=CURRENCY,
        )
        version = OptionContractVersion(contract_id=instrument.contract_id, **common)
        kind = CatalogueInstrumentKind.OPTION
    normalized_hash = stable_hash(projection)
    mapping = ProviderContractMapping(
        provider=PROVIDER,
        provider_contract_key=provider_key,
        contract_version_id=version.version_id,
        provider_payload_hash=row.raw_row_hash,
        source_row_identity=semantic_id,
        effective_from=effective_from,
        effective_until=effective_until,
        recorded_at=recorded_at,
    )
    instrument_id = getattr(instrument, "instrument_id", None) or instrument.contract_id
    return NormalizedCatalogueItem(
        kind=kind,
        provider_contract_key=provider_key,
        instrument_id=instrument_id,
        version_id=version.version_id,
        mapping_id=mapping.mapping_id,
        normalized_row_hash=normalized_hash,
        raw_row_hash=row.raw_row_hash,
        source_row_semantic_id=semantic_id,
        source_row_occurrence_id=occurrence_id,
        physical_row_number=row.physical_row_number,
        projection=projection,
        instrument=instrument,
        version=version,
        mapping=mapping,
    )


def _validate_derivative(row: dict[str, object]) -> None:
    if _required_text(row, "segment") != "NSE_FO":
        raise CatalogueNormalizationError("derivative segment must be NSE_FO")
    if _required_text(row, "exchange") != EXCHANGE:
        raise CatalogueNormalizationError("derivative exchange must be NSE")
    if _required_text(row, "underlying_key") != UNDERLYING_KEY:
        raise CatalogueNormalizationError("derivative underlying_key is outside the approved profile")
    if _required_text(row, "underlying_type") != "INDEX":
        raise CatalogueNormalizationError("derivative underlying_type must be INDEX")
    symbol = _required_text(row, "underlying_symbol").strip().upper().replace("_", " ")
    if symbol not in {"NIFTY", "NIFTY 50"}:
        raise CatalogueNormalizationError("derivative underlying_symbol does not match profile")


def _expiry(row: dict[str, object]):
    value = row.get("expiry")
    if isinstance(value, bool) or value is None:
        raise CatalogueNormalizationError("expiry must be integral epoch milliseconds")
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise CatalogueNormalizationError("expiry must be integral epoch milliseconds")
        milliseconds = int(value)
    elif isinstance(value, int):
        milliseconds = value
    else:
        raise CatalogueNormalizationError("expiry must be integral epoch milliseconds")
    if milliseconds < 0:
        raise CatalogueNormalizationError("expiry must not be negative")
    try:
        seconds, remainder_milliseconds = divmod(milliseconds, 1000)
        instant = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            seconds=seconds,
            milliseconds=remainder_milliseconds,
        )
        return instant.astimezone(KOLKATA).date()
    except (OverflowError, ValueError) as exc:
        raise CatalogueNormalizationError("expiry is outside the supported timestamp range") from exc


def _tick_size(row: dict[str, object]) -> Decimal:
    return _positive_decimal(row, "tick_size") / Decimal("100")


def _positive_decimal(row: dict[str, object], field_name: str) -> Decimal:
    value = row.get(field_name)
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise CatalogueNormalizationError(f"{field_name} must be a JSON number")
    decimal = Decimal(value)
    if not decimal.is_finite() or decimal <= 0:
        raise CatalogueNormalizationError(f"{field_name} must be positive and finite")
    return decimal


def _positive_int(row: dict[str, object], field_name: str) -> int:
    value = row.get(field_name)
    if isinstance(value, bool):
        raise CatalogueNormalizationError(f"{field_name} must be a positive integer")
    if isinstance(value, Decimal):
        if value != value.to_integral_value():
            raise CatalogueNormalizationError(f"{field_name} must be a positive integer")
        integer = int(value)
    elif isinstance(value, int):
        integer = value
    else:
        raise CatalogueNormalizationError(f"{field_name} must be a positive integer")
    if integer <= 0:
        raise CatalogueNormalizationError(f"{field_name} must be a positive integer")
    return integer


def _required_text(row: dict[str, object], field_name: str) -> str:
    value = row.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise CatalogueNormalizationError(f"{field_name} is required")
    return value.strip()


def _optional_text(row: dict[str, object], field_name: str) -> str | None:
    value = row.get(field_name)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _catalogue_scope() -> str:
    return f"{PROVIDER}:{PROFILE_VERSION}"
