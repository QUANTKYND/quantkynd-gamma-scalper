from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

import yaml
from yaml.events import AliasEvent, DocumentStartEvent, NodeEvent

from app.market_data.quality.contracts import (
    OBSERVATION_DOMAIN,
    POLICY_NAME,
    POLICY_PROVIDER,
    QUALITY_EVALUATOR_IMPLEMENTATION_VERSION,
    QUALITY_POLICY_SCHEMA_VERSION,
    QualityPolicyIdentity,
    QualityPolicyVersionIdentity,
    SourceArtifactIdentity,
    TargetKind,
)
from app.market_data.quality.errors import (
    InvalidQualityPolicyDocumentError,
    UnsupportedQualityPolicyError,
)
from app.market_data.quality.policy_schema import ParsedQualityPolicy
from app.market_data.quality.reason_registry import REASON_REGISTRY, ReasonDefinition

MAX_POLICY_SOURCE_BYTES = 262_144
PARSER_LABEL = "data15-strict-yaml-1"
MEDIA_TYPE = "application/yaml"
NORMALIZATION_SCHEMA_VERSION = 1
NORMALIZER_IMPLEMENTATION_VERSION = "upstox-v3-normalizer-1"
CATALOGUE_PROFILE = "upstox-nse-nifty-index-derivatives-v1"

_UNSIGNED_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_CONTROLLED = re.compile(r"[A-Za-z0-9_.:/-]+\Z")
_FORBIDDEN_INTERPOLATION = re.compile(r"\$\{|\$\(")
_ALLOWED_TAGS = {
    None,
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:seq",
    "tag:yaml.org,2002:str",
}


class Data15StrictLoader(yaml.BaseLoader):
    """BaseLoader with duplicate and non-string key rejection."""

    def construct_mapping(self, node: yaml.nodes.MappingNode, deep: bool = False):
        mapping: dict[str, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise InvalidQualityPolicyDocumentError(
                    "policy mappings require string keys"
                )
            if key in mapping:
                raise InvalidQualityPolicyDocumentError(
                    f"duplicate policy key: {key}"
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


Data15StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    Data15StrictLoader.construct_mapping,
)


def parse_quality_policy(source_bytes: bytes) -> ParsedQualityPolicy:
    text = _decode_source(source_bytes)
    _validate_yaml_events(text)
    try:
        documents = list(yaml.load_all(text, Loader=Data15StrictLoader))
    except InvalidQualityPolicyDocumentError:
        raise
    except yaml.YAMLError as exc:
        raise InvalidQualityPolicyDocumentError("invalid policy YAML") from exc
    if len(documents) != 1:
        raise InvalidQualityPolicyDocumentError(
            "policy source must contain exactly one YAML document"
        )
    root = _mapping(documents[0], "policy", _TOP_LEVEL_KEYS)
    _reject_interpolation(root)

    schema_version = _positive_int(root["schema_version"], "schema_version")
    if schema_version != QUALITY_POLICY_SCHEMA_VERSION:
        raise UnsupportedQualityPolicyError("unsupported quality policy schema")

    policy_node = _mapping(
        root["policy"],
        "policy.policy",
        {"name", "provider", "observation_domain"},
    )
    policy_identity = QualityPolicyIdentity(
        policy_name=_controlled(policy_node["name"], "policy.name"),
        provider=_controlled(policy_node["provider"], "policy.provider"),
        observation_domain=_controlled(
            policy_node["observation_domain"],
            "policy.observation_domain",
        ),
    )
    if (
        policy_identity.policy_name != POLICY_NAME
        or policy_identity.provider != POLICY_PROVIDER
        or policy_identity.observation_domain != OBSERVATION_DOMAIN
    ):
        raise UnsupportedQualityPolicyError("unsupported quality policy family")

    version = _positive_int(root["version"], "version")
    if version != 1:
        raise UnsupportedQualityPolicyError("DATA-1.5 supports policy version 1 only")
    version_identity = QualityPolicyVersionIdentity(policy_identity.policy_id, version)

    compatibility = _parse_compatibility(root["compatibility"])
    scope = _parse_scope(root["scope"])
    time_policy = _parse_time(root["time"])
    availability = _parse_availability(root["availability"])
    freshness = _parse_threshold_family(root["freshness"], "freshness", _FRESHNESS_KEYS)
    quote_components = _parse_quote_components(root["quote_components"])
    tick_alignment = _parse_tick_alignment(root["tick_alignment"])
    spread = _parse_spread(root["spread"])
    session = _parse_session(root["session"])
    segment_status = _parse_segment_status(root["segment_status"])
    lifecycle = _parse_lifecycle(root["lifecycle"])
    completeness = _parse_completeness(root["normalization_completeness"])
    reasons = _parse_reason_registry(root["reason_registry"])

    projection: dict[str, object] = {
        "schema_version": schema_version,
        "policy": {
            "name": policy_identity.policy_name,
            "provider": policy_identity.provider,
            "observation_domain": policy_identity.observation_domain,
        },
        "version": version,
        "compatibility": compatibility,
        "scope": scope,
        "time": time_policy,
        "availability": availability,
        "freshness": freshness,
        "quote_components": quote_components,
        "tick_alignment": tick_alignment,
        "spread": spread,
        "session": session,
        "segment_status": segment_status,
        "lifecycle": lifecycle,
        "normalization_completeness": completeness,
        "reason_registry": [item.canonical_payload for item in reasons],
    }

    source_sha256 = f"sha256:{hashlib.sha256(source_bytes).hexdigest()}"
    source_identity = SourceArtifactIdentity(
        policy_version_id=version_identity.policy_version_id,
        source_sha256=source_sha256,
        source_byte_count=len(source_bytes),
        media_type=MEDIA_TYPE,
        parser_label=PARSER_LABEL,
    )
    return ParsedQualityPolicy(
        policy_identity=policy_identity,
        policy_version_identity=version_identity,
        semantic_projection=projection,
        reason_definitions=reasons,
        source_bytes=source_bytes,
        source_sha256=source_sha256,
        source_artifact_identity=source_identity,
    )


def _decode_source(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes):
        raise InvalidQualityPolicyDocumentError("policy source must be bytes")
    if not 1 <= len(source_bytes) <= MAX_POLICY_SOURCE_BYTES:
        raise InvalidQualityPolicyDocumentError(
            "policy source byte count must be in 1..262144"
        )
    if source_bytes.startswith(b"\xef\xbb\xbf"):
        raise InvalidQualityPolicyDocumentError("UTF-8 BOM is prohibited")
    for byte in source_bytes:
        if (byte < 32 and byte not in {9, 10, 13}) or byte == 127:
            raise InvalidQualityPolicyDocumentError(
                "policy source contains a prohibited control byte"
            )
    try:
        return source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InvalidQualityPolicyDocumentError(
            "policy source must be valid UTF-8"
        ) from exc


def _validate_yaml_events(text: str) -> None:
    document_count = 0
    try:
        for event in yaml.parse(text, Loader=Data15StrictLoader):
            if isinstance(event, DocumentStartEvent):
                document_count += 1
            if isinstance(event, AliasEvent):
                raise InvalidQualityPolicyDocumentError(
                    "YAML aliases are prohibited"
                )
            if isinstance(event, NodeEvent):
                if event.anchor is not None:
                    raise InvalidQualityPolicyDocumentError(
                        "YAML anchors are prohibited"
                    )
                if event.tag not in _ALLOWED_TAGS:
                    raise InvalidQualityPolicyDocumentError(
                        "nonstandard YAML tags are prohibited"
                    )
    except InvalidQualityPolicyDocumentError:
        raise
    except yaml.YAMLError as exc:
        raise InvalidQualityPolicyDocumentError("invalid policy YAML") from exc
    if document_count > 1:
        raise InvalidQualityPolicyDocumentError(
            "multi-document policy sources are prohibited"
        )


def _parse_compatibility(value: object) -> dict[str, object]:
    node = _mapping(
        value,
        "compatibility",
        {
            "normalization_schema_version",
            "normalizer_implementation_version",
            "quality_policy_schema_version",
            "quality_evaluator_implementation_version",
        },
    )
    result = {
        "normalization_schema_version": _positive_int(
            node["normalization_schema_version"],
            "compatibility.normalization_schema_version",
        ),
        "normalizer_implementation_version": _controlled(
            node["normalizer_implementation_version"],
            "compatibility.normalizer_implementation_version",
        ),
        "quality_policy_schema_version": _positive_int(
            node["quality_policy_schema_version"],
            "compatibility.quality_policy_schema_version",
        ),
        "quality_evaluator_implementation_version": _controlled(
            node["quality_evaluator_implementation_version"],
            "compatibility.quality_evaluator_implementation_version",
        ),
    }
    if result != {
        "normalization_schema_version": NORMALIZATION_SCHEMA_VERSION,
        "normalizer_implementation_version": NORMALIZER_IMPLEMENTATION_VERSION,
        "quality_policy_schema_version": QUALITY_POLICY_SCHEMA_VERSION,
        "quality_evaluator_implementation_version": (
            QUALITY_EVALUATOR_IMPLEMENTATION_VERSION
        ),
    }:
        raise UnsupportedQualityPolicyError(
            "unsupported policy/evaluator/normalizer compatibility tuple"
        )
    return result


def _parse_scope(value: object) -> dict[str, object]:
    node = _mapping(
        value,
        "scope",
        {"catalogue_profile", "quote_event_types", "status_segments"},
    )
    quote_types = _sorted_unique_controlled_list(
        node["quote_event_types"],
        "scope.quote_event_types",
        max_items=128,
    )
    expected_quote_types = (
        "futures_quote_observation",
        "option_quote_observation",
        "underlying_quote_observation",
    )
    if quote_types != expected_quote_types:
        raise InvalidQualityPolicyDocumentError(
            "quote_event_types must contain the exact DATA-1.5 v1 set"
        )
    status_segments = _sorted_unique_controlled_list(
        node["status_segments"],
        "scope.status_segments",
        max_items=128,
    )
    if status_segments != ("NSE_FO", "NSE_INDEX"):
        raise InvalidQualityPolicyDocumentError(
            "status_segments must contain NSE_INDEX and NSE_FO"
        )
    profile = _controlled(node["catalogue_profile"], "scope.catalogue_profile")
    if profile != CATALOGUE_PROFILE:
        raise UnsupportedQualityPolicyError("unsupported catalogue profile")
    return {
        "catalogue_profile": profile,
        "quote_event_types": quote_types,
        "status_segments": status_segments,
    }


def _parse_time(value: object) -> dict[str, str]:
    node = _mapping(
        value,
        "time",
        {
            "exchange_timezone",
            "session_kind",
            "market_time_basis",
            "future_target_behavior",
        },
    )
    result = {
        key: _controlled(node[key], f"time.{key}")
        for key in sorted(node)
    }
    expected = {
        "exchange_timezone": "Asia/Kolkata",
        "future_target_behavior": "ineligible",
        "market_time_basis": "provider_timestamp_v1",
        "session_kind": "regular",
    }
    if result != expected:
        raise UnsupportedQualityPolicyError("unsupported DATA-1.5 time semantics")
    return result


def _parse_availability(value: object) -> dict[str, str]:
    node = _mapping(
        value,
        "availability",
        {"accepted_basis", "warning_basis"},
    )
    result = {
        "accepted_basis": _controlled(
            node["accepted_basis"], "availability.accepted_basis"
        ),
        "warning_basis": _controlled(
            node["warning_basis"], "availability.warning_basis"
        ),
    }
    if result != {
        "accepted_basis": "received",
        "warning_basis": "historical_import",
    }:
        raise UnsupportedQualityPolicyError("unsupported availability semantics")
    return result


def _parse_threshold_family(
    value: object,
    path: str,
    required_keys: set[str],
) -> dict[str, object]:
    node = _mapping(value, path, required_keys)
    return {
        key: _parse_warning_error_ms(node[key], f"{path}.{key}")
        for key in sorted(required_keys)
    }


def _parse_warning_error_ms(value: object, path: str) -> dict[str, int]:
    node = _mapping(value, path, {"warning_ms", "error_ms"})
    warning = _bounded_int(node["warning_ms"], f"{path}.warning_ms", 0, 86_400_000)
    error = _bounded_int(node["error_ms"], f"{path}.error_ms", 0, 86_400_000)
    if warning >= error:
        raise InvalidQualityPolicyDocumentError(
            f"{path} warning threshold must be strictly below error threshold"
        )
    return {"warning_ms": warning, "error_ms": error}


def _parse_quote_components(value: object) -> dict[str, object]:
    node = _mapping(value, "quote_components", {"underlying", "future", "option"})
    expected: dict[str, dict[str, str]] = {
        "underlying": {
            "last_price": "required_positive",
            "bid_ask_prices": "optional_pair",
            "side_sizes": "optional_with_price",
            "last_size": "optional_with_last_price",
            "last_trade_at": "optional_with_last_price",
        },
        "future": {
            "bid_price": "required_positive",
            "bid_size": "required_positive_integer",
            "ask_price": "required_positive",
            "ask_size": "required_positive_integer",
            "last_price": "optional_positive",
            "last_size": "optional_with_last_price",
            "last_trade_at": "optional_with_last_price",
        },
        "option": {
            "bid_price": "required_positive",
            "bid_size": "required_positive_integer",
            "ask_price": "required_positive",
            "ask_size": "required_positive_integer",
            "last_price": "optional_positive",
            "last_size": "optional_with_last_price",
            "last_trade_at": "optional_with_last_price",
        },
    }
    result: dict[str, object] = {}
    for kind, expected_fields in expected.items():
        kind_node = _mapping(node[kind], f"quote_components.{kind}", set(expected_fields))
        parsed = {
            key: _controlled(kind_node[key], f"quote_components.{kind}.{key}")
            for key in sorted(expected_fields)
        }
        if parsed != {key: expected_fields[key] for key in sorted(expected_fields)}:
            raise InvalidQualityPolicyDocumentError(
                f"quote_components.{kind} does not match v1 tuple semantics"
            )
        result[kind] = parsed
    return result


def _parse_tick_alignment(value: object) -> dict[str, object]:
    node = _mapping(value, "tick_alignment", {"fields", "arithmetic"})
    fields = _sorted_unique_controlled_list(
        node["fields"], "tick_alignment.fields", max_items=128
    )
    if fields != ("ask_price", "bid_price", "last_price"):
        raise InvalidQualityPolicyDocumentError(
            "tick_alignment.fields must contain bid_price, ask_price, and last_price"
        )
    arithmetic = _controlled(node["arithmetic"], "tick_alignment.arithmetic")
    if arithmetic != "exact_decimal_remainder_zero":
        raise UnsupportedQualityPolicyError("unsupported tick arithmetic")
    return {"fields": fields, "arithmetic": arithmetic}


def _parse_spread(value: object) -> dict[str, object]:
    node = _mapping(value, "spread", {"underlying", "future", "option"})
    return {
        key: _parse_spread_thresholds(node[key], f"spread.{key}")
        for key in ("future", "option", "underlying")
    }


def _parse_spread_thresholds(value: object, path: str) -> dict[str, Decimal]:
    node = _mapping(
        value,
        path,
        {"warning_ticks", "error_ticks", "warning_bps", "error_bps"},
    )
    warning_ticks = _positive_decimal(node["warning_ticks"], f"{path}.warning_ticks")
    error_ticks = _positive_decimal(node["error_ticks"], f"{path}.error_ticks")
    warning_bps = _positive_decimal(node["warning_bps"], f"{path}.warning_bps")
    error_bps = _positive_decimal(node["error_bps"], f"{path}.error_bps")
    if warning_ticks >= error_ticks or warning_bps >= error_bps:
        raise InvalidQualityPolicyDocumentError(
            f"{path} warning thresholds must be below error thresholds"
        )
    return {
        "warning_ticks": warning_ticks,
        "error_ticks": error_ticks,
        "warning_bps": warning_bps,
        "error_bps": error_bps,
    }


def _parse_session(value: object) -> dict[str, str]:
    node = _mapping(
        value,
        "session",
        {"exchange", "required_status", "open_interval"},
    )
    result = {
        key: _controlled(node[key], f"session.{key}")
        for key in sorted(node)
    }
    if result != {
        "exchange": "NSE",
        "open_interval": "half_open",
        "required_status": "scheduled",
    }:
        raise UnsupportedQualityPolicyError("unsupported session semantics")
    return result


def _parse_segment_status(value: object) -> dict[str, str]:
    node = _mapping(value, "segment_status", {"accepted_status"})
    accepted = _controlled(
        node["accepted_status"], "segment_status.accepted_status"
    )
    if accepted != "NORMAL_OPEN":
        raise UnsupportedQualityPolicyError("unsupported segment status semantics")
    return {"accepted_status": accepted}


def _parse_lifecycle(value: object) -> dict[str, object]:
    node = _mapping(
        value,
        "lifecycle",
        {
            "required_connection_state",
            "active_subscription_states",
            "lease_ms",
        },
    )
    required_state = _controlled(
        node["required_connection_state"],
        "lifecycle.required_connection_state",
    )
    active_states = _sorted_unique_controlled_list(
        node["active_subscription_states"],
        "lifecycle.active_subscription_states",
        max_items=128,
    )
    lease_ms = _bounded_int(node["lease_ms"], "lifecycle.lease_ms", 0, 86_400_000)
    if required_state != "authorized" or active_states != ("mode_changed", "subscribed"):
        raise UnsupportedQualityPolicyError("unsupported lifecycle state semantics")
    return {
        "required_connection_state": required_state,
        "active_subscription_states": active_states,
        "lease_ms": lease_ms,
    }


def _parse_completeness(value: object) -> dict[str, str]:
    required = {
        "unadopted_schema_paths",
        "present_unadopted_message_paths",
        "secondary_payload_paths",
        "depth_truncation",
    }
    node = _mapping(value, "normalization_completeness", required)
    result = {
        key: _controlled(node[key], f"normalization_completeness.{key}")
        for key in sorted(required)
    }
    if any(item != "warning" for item in result.values()):
        raise UnsupportedQualityPolicyError(
            "normalization completeness semantics must be warning"
        )
    return result


def _parse_reason_registry(value: object) -> tuple[ReasonDefinition, ...]:
    rows = _sequence(value, "reason_registry")
    if len(rows) != len(REASON_REGISTRY):
        raise InvalidQualityPolicyDocumentError(
            "reason_registry must contain exactly 69 definitions"
        )
    parsed: list[ReasonDefinition] = []
    for index, (raw_row, expected) in enumerate(zip(rows, REASON_REGISTRY, strict=True)):
        path = f"reason_registry[{index}]"
        node = _mapping(
            raw_row,
            path,
            {
                "code",
                "ordinal",
                "severity",
                "applicable_target_kinds",
                "subject_keys",
                "evidence_profile",
            },
        )
        try:
            item = ReasonDefinition(
                ordinal=_positive_int(node["ordinal"], f"{path}.ordinal"),
                code=_controlled(node["code"], f"{path}.code"),
                severity=_controlled(node["severity"], f"{path}.severity"),
                applicable_target_kinds=frozenset(
                    TargetKind(kind)
                    for kind in _sorted_unique_controlled_list(
                        node["applicable_target_kinds"],
                        f"{path}.applicable_target_kinds",
                        max_items=128,
                    )
                ),
                subject_keys=_sorted_unique_controlled_list(
                    node["subject_keys"],
                    f"{path}.subject_keys",
                    max_items=128,
                ),
                evidence_profile=_controlled(
                    node["evidence_profile"], f"{path}.evidence_profile"
                ),
            )
        except (TypeError, ValueError) as exc:
            raise InvalidQualityPolicyDocumentError(
                f"invalid reason definition at ordinal {index + 1}"
            ) from exc
        if item.canonical_payload != expected.canonical_payload:
            raise InvalidQualityPolicyDocumentError(
                f"reason definition differs from frozen registry: {expected.code}"
            )
        parsed.append(item)
    return tuple(parsed)


def _mapping(value: object, path: str, required_keys: set[str]) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidQualityPolicyDocumentError(f"{path} must be a mapping")
    if any(not isinstance(key, str) for key in value):
        raise InvalidQualityPolicyDocumentError(f"{path} requires string keys")
    actual = set(value)
    missing = sorted(required_keys - actual)
    unknown = sorted(actual - required_keys)
    if missing or unknown:
        raise InvalidQualityPolicyDocumentError(
            f"{path} key mismatch; missing={missing}, unknown={unknown}"
        )
    return dict(value)


def _sequence(value: object, path: str) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise InvalidQualityPolicyDocumentError(f"{path} must be a sequence")
    return list(value)


def _controlled(value: object, path: str) -> str:
    if not isinstance(value, str):
        raise InvalidQualityPolicyDocumentError(f"{path} must be text")
    if not 1 <= len(value.encode("utf-8")) <= 128:
        raise InvalidQualityPolicyDocumentError(f"{path} must be 1..128 UTF-8 bytes")
    if value != value.strip() or _CONTROLLED.fullmatch(value) is None:
        raise InvalidQualityPolicyDocumentError(f"{path} is not controlled text")
    if _FORBIDDEN_INTERPOLATION.search(value):
        raise InvalidQualityPolicyDocumentError(
            f"{path} contains prohibited environment interpolation"
        )
    return value


def _positive_int(value: object, path: str) -> int:
    parsed = _bounded_int(value, path, 1, 2**31 - 1)
    return parsed


def _bounded_int(value: object, path: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, str) or _UNSIGNED_INTEGER.fullmatch(value) is None:
        raise InvalidQualityPolicyDocumentError(
            f"{path} must be an unsigned base-10 integer string"
        )
    parsed = int(value)
    if not minimum <= parsed <= maximum:
        raise InvalidQualityPolicyDocumentError(
            f"{path} must be in {minimum}..{maximum}"
        )
    return parsed


def _positive_decimal(value: object, path: str) -> Decimal:
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None:
        raise InvalidQualityPolicyDocumentError(
            f"{path} must be non-exponent finite decimal text"
        )
    whole, _, fractional = value.partition(".")
    if len(whole) + len(fractional) > 38 or len(fractional) > 18:
        raise InvalidQualityPolicyDocumentError(
            f"{path} exceeds Numeric(38,18) bounds"
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise InvalidQualityPolicyDocumentError(f"{path} is not a decimal") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise InvalidQualityPolicyDocumentError(f"{path} must be positive and finite")
    return parsed


def _sorted_unique_controlled_list(
    value: object,
    path: str,
    *,
    max_items: int,
) -> tuple[str, ...]:
    rows = _sequence(value, path)
    if not 1 <= len(rows) <= max_items:
        raise InvalidQualityPolicyDocumentError(
            f"{path} must contain 1..{max_items} values"
        )
    parsed = tuple(_controlled(item, f"{path}[]") for item in rows)
    if len(set(parsed)) != len(parsed):
        raise InvalidQualityPolicyDocumentError(f"{path} must be unique")
    return tuple(sorted(parsed))


def _reject_interpolation(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_interpolation(key)
            _reject_interpolation(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            _reject_interpolation(item)
    elif isinstance(value, str) and _FORBIDDEN_INTERPOLATION.search(value):
        raise InvalidQualityPolicyDocumentError(
            "environment interpolation is prohibited"
        )


_TOP_LEVEL_KEYS = {
    "schema_version",
    "policy",
    "version",
    "compatibility",
    "scope",
    "time",
    "availability",
    "freshness",
    "quote_components",
    "tick_alignment",
    "spread",
    "session",
    "segment_status",
    "lifecycle",
    "normalization_completeness",
    "reason_registry",
}

_FRESHNESS_KEYS = {
    "underlying_live",
    "future_live",
    "option_live",
    "any_initial",
    "segment_status",
}
