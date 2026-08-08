from __future__ import annotations

from dataclasses import dataclass

from app.core.hashing import stable_hash
from app.market_data.quality.contracts import QualitySeverity, TargetKind

ALL = frozenset(TargetKind)
QUOTES = frozenset(
    {
        TargetKind.UNDERLYING_QUOTE,
        TargetKind.FUTURES_QUOTE,
        TargetKind.OPTION_QUOTE,
    }
)
DERIVATIVE_QUOTES = frozenset({TargetKind.FUTURES_QUOTE, TargetKind.OPTION_QUOTE})
UNDERLYING = frozenset({TargetKind.UNDERLYING_QUOTE})
STATUS = frozenset({TargetKind.MARKET_SEGMENT_STATUS})


@dataclass(frozen=True)
class ReasonDefinition:
    ordinal: int
    code: str
    severity: QualitySeverity
    applicable_target_kinds: frozenset[TargetKind]
    subject_keys: tuple[str, ...]
    evidence_profile: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", QualitySeverity(self.severity))
        kinds = frozenset(TargetKind(value) for value in self.applicable_target_kinds)
        if not kinds:
            raise ValueError("reason applicability cannot be empty")
        object.__setattr__(self, "applicable_target_kinds", kinds)
        keys = tuple(sorted(set(self.subject_keys)))
        if not keys:
            raise ValueError("reason subject_keys cannot be empty")
        object.__setattr__(self, "subject_keys", keys)

    @property
    def rule_id(self) -> str:
        return f"quality.{self.code}"

    @property
    def canonical_payload(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "code": self.code,
            "severity": self.severity.value,
            "applicable_target_kinds": tuple(
                sorted(kind.value for kind in self.applicable_target_kinds)
            ),
            "subject_keys": self.subject_keys,
            "evidence_profile": self.evidence_profile,
        }

    @property
    def canonical_payload_hash(self) -> str:
        return stable_hash(self.canonical_payload)


def _r(
    ordinal: int,
    code: str,
    severity: str,
    applicability: frozenset[TargetKind],
    subject_keys: str | tuple[str, ...],
    profile: str,
) -> ReasonDefinition:
    keys = (subject_keys,) if isinstance(subject_keys, str) else subject_keys
    return ReasonDefinition(
        ordinal,
        code,
        QualitySeverity(severity),
        applicability,
        keys,
        profile,
    )


REASON_REGISTRY = (
    _r(1,"historical_import_availability","warning",ALL,"observation","availability"),
    _r(2,"quote_age_warning","warning",QUOTES,"observation","age"),
    _r(3,"status_age_warning","warning",ALL,"market_segment_status","age"),
    _r(4,"market_locked","warning",QUOTES,"bid_ask_spread","quote_pair"),
    _r(5,"spread_warning","warning",QUOTES,"bid_ask_spread","spread"),
    _r(6,"unadopted_schema_paths_present","warning",QUOTES,"observation","path_set"),
    _r(7,"present_unadopted_message_paths","warning",QUOTES,"observation","path_set"),
    _r(8,"secondary_payload_paths_present","warning",QUOTES,"observation","path_set"),
    _r(9,"depth_truncated","warning",QUOTES,"observation","depth"),
    _r(10,"unsupported_provider","error",ALL,"observation","identity"),
    _r(11,"unsupported_normalization_schema","error",ALL,"observation","schema"),
    _r(12,"unsupported_subject_scope","error",ALL,"observation","scope"),
    _r(13,"provider_timestamp_in_future","error",ALL,"observation","future_offset"),
    _r(14,"quote_stale","error",QUOTES,"observation","age"),
    _r(15,"status_stale","error",ALL,"market_segment_status","age"),
    _r(16,"availability_basis_invalid","error",ALL,"observation","availability"),
    _r(17,"required_last_price_missing","error",UNDERLYING,"last_price","field_presence"),
    _r(18,"bid_missing","error",DERIVATIVE_QUOTES,"bid_price","field_presence"),
    _r(19,"ask_missing","error",DERIVATIVE_QUOTES,"ask_price","field_presence"),
    _r(20,"bid_size_missing","error",DERIVATIVE_QUOTES,"bid_size","field_presence"),
    _r(21,"ask_size_missing","error",DERIVATIVE_QUOTES,"ask_size","field_presence"),
    _r(22,"one_sided_quote","error",UNDERLYING,"bid_ask_spread","field_presence"),
    _r(23,"orphan_quote_component","error",QUOTES,("ask_size","bid_size","last_size","last_trade_at"),"field_presence"),
    _r(24,"invalid_numeric_value","error",QUOTES,("ask_price","ask_size","bid_price","bid_size","last_price","last_size","open_interest","previous_close_price","reported_volume"),"numeric"),
    _r(25,"bid_zero","error",DERIVATIVE_QUOTES,"bid_price","numeric"),
    _r(26,"ask_zero","error",DERIVATIVE_QUOTES,"ask_price","numeric"),
    _r(27,"bid_size_zero","error",DERIVATIVE_QUOTES,"bid_size","numeric"),
    _r(28,"ask_size_zero","error",DERIVATIVE_QUOTES,"ask_size","numeric"),
    _r(29,"last_price_zero","error",QUOTES,"last_price","numeric"),
    _r(30,"market_crossed","error",QUOTES,"bid_ask_spread","quote_pair"),
    _r(31,"spread_limit_exceeded","error",QUOTES,"bid_ask_spread","spread"),
    _r(32,"tick_size_missing_or_invalid","error",QUOTES,"instrument_version","dependency"),
    _r(33,"price_not_tick_aligned","error",QUOTES,("ask_price","bid_price","last_price"),"tick"),
    _r(34,"resolution_cutoff_after_evaluation","error",QUOTES,"observation","cutoff"),
    _r(35,"instrument_version_missing","error",QUOTES,"instrument_version","dependency"),
    _r(36,"instrument_version_ambiguous","error",QUOTES,"instrument_version","dependency_ambiguity"),
    _r(37,"instrument_version_mismatch","error",QUOTES,"instrument_version","dependency_compare"),
    _r(38,"instrument_version_not_effective","error",QUOTES,"instrument_version","dependency"),
    _r(39,"instrument_trading_status_not_active","error",QUOTES,"instrument_version","state"),
    _r(40,"provider_mapping_missing","error",QUOTES,"provider_mapping","dependency"),
    _r(41,"provider_mapping_ambiguous","error",QUOTES,"provider_mapping","dependency_ambiguity"),
    _r(42,"provider_mapping_mismatch","error",QUOTES,"provider_mapping","dependency_compare"),
    _r(43,"provider_mapping_not_effective","error",QUOTES,"provider_mapping","dependency"),
    _r(44,"catalogue_provenance_missing","error",QUOTES,"catalogue_version","dependency"),
    _r(45,"catalogue_provenance_ambiguous","error",QUOTES,"catalogue_version","dependency_ambiguity"),
    _r(46,"catalogue_provenance_mismatch","error",QUOTES,"catalogue_version","dependency_compare"),
    _r(47,"catalogue_provenance_not_effective","error",QUOTES,"catalogue_version","dependency"),
    _r(48,"provider_segment_unresolvable","error",ALL,"provider_segment","segment"),
    _r(49,"provider_segment_mismatch","error",ALL,"provider_segment","segment"),
    _r(50,"trading_session_missing","error",ALL,"trading_session","dependency"),
    _r(51,"trading_session_ambiguous","error",ALL,"trading_session","dependency_ambiguity"),
    _r(52,"trading_session_timezone_mismatch","error",ALL,"trading_session","session"),
    _r(53,"trading_session_not_scheduled","error",ALL,"trading_session","session"),
    _r(54,"outside_regular_session","error",ALL,"trading_session","session"),
    _r(55,"segment_status_missing","error",QUOTES,"market_segment_status","dependency"),
    _r(56,"segment_status_ambiguous","error",QUOTES,"market_segment_status","dependency_ambiguity"),
    _r(57,"segment_status_unknown","error",ALL,"market_segment_status","state"),
    _r(58,"segment_not_normal_open","error",ALL,"market_segment_status","state"),
    _r(59,"connection_state_missing","error",ALL,"connection_session","dependency"),
    _r(60,"connection_state_ambiguous","error",ALL,"connection_session","dependency_ambiguity"),
    _r(61,"connection_not_authorized","error",ALL,"connection_session","lifecycle"),
    _r(62,"connection_state_stale","error",ALL,"connection_session","lifecycle_age"),
    _r(63,"subscription_state_missing","error",QUOTES,"subscription_scope","dependency"),
    _r(64,"subscription_state_ambiguous","error",QUOTES,"subscription_scope","dependency_ambiguity"),
    _r(65,"subscription_not_active","error",QUOTES,"subscription_scope","lifecycle"),
    _r(66,"subscription_mode_mismatch","error",QUOTES,"subscription_scope","subscription"),
    _r(67,"subscription_instrument_missing","error",QUOTES,"subscription_scope","subscription"),
    _r(68,"subscription_state_stale","error",QUOTES,"subscription_scope","lifecycle_age"),
    _r(69,"ambiguous_active_subscription","error",QUOTES,"subscription_scope","dependency_ambiguity"),
)

REASONS_BY_CODE = {item.code: item for item in REASON_REGISTRY}


def validate_reason_registry() -> None:
    if len(REASON_REGISTRY) != 69:
        raise ValueError("DATA-1.5 reason registry must contain exactly 69 definitions")
    if tuple(item.ordinal for item in REASON_REGISTRY) != tuple(range(1, 70)):
        raise ValueError("DATA-1.5 reason registry ordinals must be contiguous 1..69")
    if len(REASONS_BY_CODE) != len(REASON_REGISTRY):
        raise ValueError("DATA-1.5 reason codes must be unique")
    for item in REASON_REGISTRY:
        if item.rule_id != f"quality.{item.code}":
            raise ValueError("reason rule ID mismatch")


validate_reason_registry()
