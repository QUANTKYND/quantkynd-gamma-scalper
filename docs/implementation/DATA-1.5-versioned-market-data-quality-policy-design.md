# DATA-1.5 — Versioned Market-Data Quality Policy Design

**Status:** Proposed for independent design review; implementation is not authorized.

**Repository:** `QUANTKYND/quantkynd-gamma-scalper`  
**Accepted baseline branch/SHA:** `master` / `b461d507d08546d72d952f80016b2617e216d711`  
**Design branch:** `feature/data15-versioned-market-data-quality-policy`  
**Requirements source branch SHA:** `478a7a917730b5acf12e27e8c3e17d97036e3154`  
**Reviewed canonical requirements SHA-256:** `a4c7d551d59d7685278faecb6153d84786d9dceff983669699ad78d9f0ff1266`  
**Current Alembic head:** `20260804_04`  
**Proposed migration:** `20260804_05`  
**Acceptance database:** PostgreSQL server major 17 and PostgreSQL client major 17. Exact 17.x versions are captured during implementation evidence; no patch version is claimed by this documentation-only phase.  
**Design-phase changed files:** this design, its independent review, its approval record, and the corrected design gate only.  
**Implementation/configuration/test/migration changes in this phase:** none.

The remote branch was created from the accepted DATA-1.4 baseline and, through SHA `478a7a...`, contains documentation changes only. During design review, one stale clause in requirements §§14.1–14.2 still named the target `provider_timestamp`; the explicit supersession clauses in §§8.2–8.3, 28, and 29 already require `dependency_market_as_of`. The canonical requirements file bundled with this design replaces those two stale references and is bound by the SHA-256 above. A local worktree state is not observable through the repository connector; this design binds itself to the exact remote source SHA and reviewed requirements bytes rather than claiming an unverified local status.

---

## 1. Decision summary

DATA-1.5 adds one deterministic, versioned quality-policy subsystem over DATA-1.4 durable observations. It does not reconstruct chains, choose a latest quote, compute IV, run a strategy, connect Redis, or touch broker/execution paths.

The design freezes these decisions:

1. The policy is a strict YAML artifact parsed into a fully typed semantic projection. Source bytes and policy semantics are separate append-only objects.
2. One exact policy version is named by every evaluation command. There is no active/current/latest policy pointer.
3. Every assessment requires explicit `evaluation_market_as_of` and `evaluation_known_as_of`; `known_as_of` cannot precede `market_as_of`.
4. A target hidden at the knowledge cutoff yields non-persisting `target_not_visible`. In a multi-target command, one hidden target aborts the whole command before any run row is written.
5. Any target timestamp after the market cutoff is visible for quality assessment but ineligible. All dependency selectors use `dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)`.
6. Temporal dependency visibility requires both the existing asserted knowledge interval and an immutable repository-owned receipt boundary.
7. Expected missing/ambiguous market dependencies become controlled reasons. Broken hashes, identities, FKs, graph shape, counts, or immutable content abort the run as durable corruption.
8. Assessment identity is independent of its result and of run packaging. One assessment may belong to multiple runs.
9. Every present dependency has a real FK. A generic manifest is retained for canonical ordering, but present candidate rows use typed FK columns guarded by exact database shape constraints.
10. One repeatable-read transaction persists a complete run, assessments, reasons, dependencies, candidates, and memberships atomically.

---

## 2. Repository findings and required adaptations

| Source anchor | Verified current behavior | DATA-1.5 design response |
|---|---|---|
| `backend/app/market_data/point_in_time.py` — `QuoteQualityDisposition`, `PointInTimeQuery`, `DataQualityAssessment`, `_selected_assessment` | Provisional vocabulary is `accepted/accepted_with_flags/quarantined/rejected`; assessment identity includes run, result, and reasons; `_selected_assessment` chooses the latest persisted assessment. | Replace the provisional quality types with imports/adapters to the accepted DATA-1.5 contracts. Exact assessment selection requires event, policy-version ID, market cutoff, and knowledge cutoff. No max/latest fallback remains. `reconstruct_option_chain` is not wired to any runtime path. |
| `backend/app/market_data/normalization/models.py` — `QuoteObservationV1`, three quote subtypes, `ProviderMarketSegmentStatusObservationV1`, `NormalizedMarketEventTimeV1` | Carries provider timestamp, availability, request mode/feed union, prices/sizes, completeness metadata, and resolved mapping/version provenance. Exchange timestamp is explicitly unavailable. | Use these persisted fields as immutable inputs. `provider_timestamp_v1` is the sole market-time basis. No provider SDK or Protobuf object enters the quality domain. |
| `backend/app/market_data/persistence/contracts.py` and `planner.py` | DATA-1.4 already defines canonical hashing, repeatable identities, parameter chunks, and a 64-stripe advisory-lock namespace. | Reuse `canonical_json`, `stable_hash`, and `plan_parameter_chunks`; define a DATA-1.5-specific lock namespace and stripe function. Do not reuse DATA-1.4 namespace or entity labels. |
| `backend/app/persistence/postgres/models.py` | DATA-1.4 persists raw frames, normalization results, exact result/event membership, observations and subtypes, lifecycle batches/events/observations, and typed instrument/session temporal records. Result and lifecycle batch roots own `persistence_recorded_at`. | Add DATA-1.5 tables and five typed receipt tables (four temporal-record receipts and one catalogue-membership receipt). Reuse owning result persistence for market observations and owning lifecycle-batch persistence for lifecycle observations and subscription sets. |
| `backend/app/persistence/postgres/repositories.py` — `PostgresMarketEventRepository`, temporal repositories, `_insert_temporal_record`, `_insert_immutable` | Immutable insert-or-compare and temporal graph resolution exist. Existing temporal selectors only filter semantic `recorded_at`; trading-session `resolve` returns a value without record ID. | Add a dedicated quality repository with cutoff-limited plural candidate queries. Extend temporal writers to create typed receipt facts atomically. Add `resolve_state` for trading sessions returning `session_version_id` and `record_id`. Existing generic singular resolvers are not used for eligibility when ambiguity evidence is required. |
| `backend/app/persistence/postgres/unit_of_work.py` — `PostgresUnitOfWork` | Starts `REPEATABLE READ`, exposes final/non-reusable repositories, commits or rolls back once. | Add `market_data_quality` repository property. Evaluation uses writable repeatable-read; audit/verification may use read-only repeatable-read. No nested transaction or network call. |
| `backend/app/persistence/postgres/verification.py` — `DURABLE_MODELS`, `durable_snapshot` | Snapshot orders every table by primary key and hashes the complete payload. | Register all DATA-1.5 ORM tables in FK-safe deterministic order and include policy/reason/assessment/dependency hashes in reconstruction checks. |
| `backend/app/instruments/identity.py`, `catalogue.py`, `sessions.py`, `temporal_records.py` | Semantic identities exclude `recorded_at`; temporal record IDs include scope, asserted recorded time, predecessor, and provenance. Graph branches/cycles are rejected. | Preserve semantic IDs. Add receipt visibility without changing existing IDs or validity intervals. A branch/cycle/missing predecessor is corruption; multiple effective leaves are a quality ambiguity only when the stored graph itself is valid. |
| `backend/app/instruments/ports.py` — `TradingSessionRepository.resolve` | Returns only `TradingSessionVersion`. | Add `TradingSessionVersionState(value, record_id)` and `resolve_state(...)`; retain `resolve` as a wrapper. |
| `backend/alembic/versions/20260804_04_append_only_market_events.py` | Owns DATA-1.4 append-only functions/triggers, aggregate checks, temporal provenance unique constraints, and deterministic non-empty downgrade refusal. | Migration `20260804_05` owns only DATA-1.5 objects, one new session-record composite unique constraint, four receipt-completeness triggers, and DATA-1.5 append-only/aggregate functions. It does not edit DATA-1.4 functions or permissive clauses. |

### Source/requirements mismatches that must be implemented

- The old disposition vocabulary and latest-assessment selector are not acceptable DATA-1.5 semantics.
- Trading-session resolution lacks the temporal record ID required for exact provenance.
- Mapping, version, catalogue, and session temporal rows lack accepted non-backdatable receipt facts.
- Existing market/lifecycle repositories do not expose the plural candidate sets and owning persistence rows required to prove ambiguity and absence.
- No accepted policy, reason, assessment, dependency, or run persistence API exists yet.

---

## 3. Exact proposed file layout and import direction

```text
config/data_quality/
└── upstox-nse-market-observation-quality-v1.yaml

backend/app/market_data/quality/
├── __init__.py
├── contracts.py
├── errors.py
├── policy_schema.py
├── policy_parser.py
├── reason_registry.py
├── dependency_resolution.py
├── evaluator.py
├── ports.py
└── service.py

backend/app/market_data/point_in_time.py                       # compatibility adaptation only
backend/app/instruments/ports.py                              # TradingSessionVersionState API
backend/app/persistence/postgres/models.py                    # DATA-1.5 tables
backend/app/persistence/postgres/mappings.py                  # row/domain mappings
backend/app/persistence/postgres/repositories.py              # quality repo + receipt-aware temporal writes
backend/app/persistence/postgres/unit_of_work.py              # quality repository property
backend/app/persistence/postgres/verification.py              # durable registry/snapshot
backend/alembic/versions/20260804_05_versioned_market_data_quality_policy.py

backend/tests/unit/market_data/quality/
├── test_contracts.py
├── test_policy_parser.py
├── test_policy_vectors.py
├── test_reason_registry.py
├── test_dependency_resolution.py
├── test_evaluator_quote_rules.py
├── test_evaluator_status_rules.py
└── test_point_in_time_compatibility.py

backend/tests/integration/postgres/
├── test_data15_policy_repository.py
├── test_data15_assessment_repository.py
├── test_data15_dependency_receipts.py
├── test_data15_concurrency.py
├── test_data15_no_future_leakage.py
├── test_data15_migration.py
└── test_data15_restore.py

docs/implementation/
├── DATA-1.5-versioned-market-data-quality-policy-design.md
├── DATA-1.5-design-adversarial-review.md
├── DATA-1.5-design-approval.md
└── DATA-1.5-acceptance-evidence.md                         # implementation phase
```

Import rules:

- `contracts.py`, `reason_registry.py`, `dependency_resolution.py`, and `evaluator.py` may import only Python stdlib, `app.core.hashing`, instrument/normalization domain types, and sibling quality modules.
- `policy_parser.py` may additionally import PyYAML, already present in `backend/pyproject.toml`; it may not import SQLAlchemy.
- `ports.py` contains protocols and immutable query/result DTOs; it may not import SQLAlchemy.
- `service.py` orchestrates ports and pure evaluator; it does not import concrete PostgreSQL models.
- PostgreSQL modules depend inward on quality contracts/ports. Quality domain modules never depend outward on SQLAlchemy, FastAPI, Redis, Upstox SDK, Protobuf, or broker types.
- No FastAPI route, Redis key, live worker, broker adapter, or frontend file is added.

---

## 4. Domain contracts and deterministic identities

### 4.1 Controlled enums

```text
QualityDisposition = eligible | warning | ineligible
QualitySeverity    = warning | error
DependencyOutcome = selected | absent | ambiguous
TargetKind         = underlying_quote | futures_quote | option_quote | market_segment_status
ReceiptBasis       = legacy_bootstrap | repository_insert
```

`QualityDisposition.is_eligible` is true for `eligible` and `warning` only.

### 4.2 Identity table

| Durable object | Deterministic key | Included identity material | Excluded evidence | Collision/retry | FK targets |
|---|---|---|---|---|---|
| Policy | `policy_id` | entity, policy name, provider, observation domain | descriptions, source path, time | same ID/different tuple collides; exact retry idempotent | none |
| Policy version | `policy_version_id` | entity, `policy_id`, positive version | policy content/hash, source bytes, registration time | same ID/different semantic projection or compatibility collides | policy |
| Source artifact | `source_artifact_id` | entity, version ID, exact source SHA-256, byte count, media type, parser label | registration time | same bytes idempotent; equivalent different bytes create another artifact | policy version |
| Reason definition | `reason_definition_id` | entity, version ID, reason code | ordinal, severity, applicability/evidence schema | same ID/different definition collides | policy version |
| Assessment | `assessment_id` | entity, event ID, policy-version ID, market cutoff, knowledge cutoff | run, disposition, reasons, dependencies, persistence time | same ID/different complete evidence is durable collision | event/result/raw/policy version |
| Assessment run | `assessment_run_id` | entity, run schema `1`, policy-version ID, both cutoffs, sorted unique target IDs, evaluator label | persistence time, result | exact retry idempotent; changed target set/content collides | policy version |
| Reason occurrence | `reason_occurrence_id` | entity, assessment ID, reason code, subject key | evidence and ordinal | same ID/different evidence collides | assessment, reason definition |
| Dependency manifest | `assessment_dependency_id` | entity, assessment ID, dependency kind, subject key | outcome, candidates, evidence | same ID/different closure evidence collides | assessment |
| Run membership | composite `(assessment_run_id, target_ordinal)` | run plus canonical target ordinal | persistence time | exact row idempotent; changed event/assessment collides | run, assessment, event |
| Temporal receipt | existing temporal `record_id` as PK/FK | exact record identity | receipt time/basis from semantic identity | one receipt per record; retry leaves first receipt unchanged | exact temporal record |

Frozen formulas:

```text
source_artifact_id = stable_hash({
  "entity": "market_data_quality_policy_source_artifact",
  "policy_version_id": policy_version_id,
  "source_sha256": source_sha256,
  "source_byte_count": source_byte_count,
  "media_type": "application/yaml",
  "parser_label": "data15-strict-yaml-1"
})

reason_definition_id = stable_hash({
  "entity": "market_data_quality_reason_definition",
  "policy_version_id": policy_version_id,
  "reason_code": reason_code
})

assessment_run_id = stable_hash({
  "entity": "market_data_quality_assessment_run",
  "assessment_run_schema_version": 1,
  "policy_version_id": policy_version_id,
  "evaluation_market_as_of": evaluation_market_as_of,
  "evaluation_known_as_of": evaluation_known_as_of,
  "ordered_target_event_ids": sorted_unique_event_ids,
  "quality_evaluator_implementation_version": "market-data-quality-evaluator-1"
})

reason_occurrence_id = stable_hash({
  "entity": "market_data_quality_assessment_reason",
  "assessment_id": assessment_id,
  "reason_code": reason_code,
  "subject_key": subject_key
})

dependency_id = stable_hash({
  "entity": "market_data_quality_assessment_dependency",
  "assessment_id": assessment_id,
  "dependency_kind": dependency_kind,
  "subject_key": subject_key
})
```

The requirements-defined policy, policy-version, and assessment formulas are used verbatim.

---

## 5. Canonical policy document and strict parsing

### 5.1 Complete v1 schema tree

All YAML scalar nodes are initially strings. Conversion occurs only through the field schema below.

```yaml
schema_version: "1"
policy:
  name: upstox_nse_nifty_index_derivatives_quality
  provider: upstox
  observation_domain: normalized_market_observation
version: "1"
compatibility:
  normalization_schema_version: "1"
  normalizer_implementation_version: upstox-v3-normalizer-1
  quality_policy_schema_version: "1"
  quality_evaluator_implementation_version: market-data-quality-evaluator-1
scope:
  catalogue_profile: upstox-nse-nifty-index-derivatives-v1
  quote_event_types:
    - underlying_quote_observation
    - futures_quote_observation
    - option_quote_observation
  status_segments: [NSE_INDEX, NSE_FO]
time:
  exchange_timezone: Asia/Kolkata
  session_kind: regular
  market_time_basis: provider_timestamp_v1
  future_target_behavior: ineligible
availability:
  accepted_basis: received
  warning_basis: historical_import
freshness:
  underlying_live: {warning_ms: "3000", error_ms: "10000"}
  future_live: {warning_ms: "2000", error_ms: "5000"}
  option_live: {warning_ms: "2000", error_ms: "5000"}
  any_initial: {warning_ms: "15000", error_ms: "60000"}
  segment_status: {warning_ms: "60000", error_ms: "300000"}
quote_components:
  underlying:
    last_price: required_positive
    bid_ask_prices: optional_pair
    side_sizes: optional_with_price
    last_size: optional_with_last_price
    last_trade_at: optional_with_last_price
  future:
    bid_price: required_positive
    bid_size: required_positive_integer
    ask_price: required_positive
    ask_size: required_positive_integer
    last_price: optional_positive
    last_size: optional_with_last_price
    last_trade_at: optional_with_last_price
  option:
    bid_price: required_positive
    bid_size: required_positive_integer
    ask_price: required_positive
    ask_size: required_positive_integer
    last_price: optional_positive
    last_size: optional_with_last_price
    last_trade_at: optional_with_last_price
tick_alignment:
  fields: [bid_price, ask_price, last_price]
  arithmetic: exact_decimal_remainder_zero
spread:
  underlying: {warning_ticks: "5", error_ticks: "20", warning_bps: "15", error_bps: "75"}
  future: {warning_ticks: "4", error_ticks: "12", warning_bps: "20", error_bps: "75"}
  option: {warning_ticks: "5", error_ticks: "20", warning_bps: "1000", error_bps: "5000"}
session:
  exchange: NSE
  required_status: scheduled
  open_interval: half_open
segment_status:
  accepted_status: NORMAL_OPEN
lifecycle:
  required_connection_state: authorized
  active_subscription_states: [subscribed, mode_changed]
  lease_ms: "43200000"
normalization_completeness:
  unadopted_schema_paths: warning
  present_unadopted_message_paths: warning
  secondary_payload_paths: warning
  depth_truncation: warning
reason_registry:
  - code: <one of the 69 frozen codes>
    ordinal: "<1..69>"
    severity: warning|error
    applicable_target_kinds: [<controlled values>]
    subject_keys: [<controlled values>]
    evidence_profile: <controlled profile>
```

The `option` mapping is physically repeated in the reviewed YAML. Anchors and aliases are prohibited.

Required types and bounds:

- versions/ordinals are base-10 positive integers; reason ordinals are exactly contiguous `1..69`;
- millisecond thresholds are integers `0..86400000`; warning is strictly less than error;
- tick and basis-point thresholds are finite positive `Decimal`, no exponent in source, at most 18 fractional digits and 38 total digits;
- controlled identifiers are ASCII lowercase snake case or explicitly enumerated uppercase exchange/status values, 1–128 UTF-8 bytes;
- lists are nonempty where shown, sorted/unique in the semantic projection, and bounded to 128 entries except the fixed reason registry of 69;
- no field is optional in v1; presentation comments are outside the semantic tree.

### 5.2 Parser algorithm

`policy_parser.py` uses a `yaml.BaseLoader` subclass named `Data15StrictLoader`:

1. reject UTF-8 BOM, invalid UTF-8, NUL/control bytes other than LF/TAB, and source larger than 262,144 bytes;
2. reject every `AliasEvent`, every node anchor, nonstandard tag, merge key, non-string mapping key, duplicate key, and multi-document stream;
3. preserve every scalar as text; schema converters alone recognize exact lowercase `true`/`false`, unsigned base-10 integers, finite non-exponent decimal text, and controlled strings;
4. reject unknown keys, missing keys, implicit/coerced nulls, floats, timestamps, environment interpolation, custom constructors, and extra list entries;
5. build immutable policy contracts, canonicalize controlled lists, and verify the full 69-code registry against `reason_registry.py`;
6. compute exact source evidence from the original bytes and semantic evidence from the typed projection.

`source_sha256 = "sha256:" + sha256(source_bytes).hexdigest()`.

`policy_definition_hash = stable_hash(semantic_projection)` using existing repository `canonical_json`/`stable_hash`.

Comments, indentation, LF/CRLF choice, and key order may change source bytes but not the semantic projection. Any threshold, applicability, reason, ordinal, severity, subject key, evidence profile, scope, or compatibility change changes the semantic projection and collides under version `1`.

### 5.3 Compatibility matrix

| Policy schema | Evaluator label | Normalization schema | Normalizer label | Supported |
|---:|---|---:|---|---|
| 1 | `market-data-quality-evaluator-1` | 1 | `upstox-v3-normalizer-1` | yes |
| any other | any | any | any | no; policy registration or visible-target evaluation fails according to the relevant contract |

### 5.4 Frozen canonical vectors

| Canonical JSON | Expected hash |
|---|---|
| `{"entity":"market_data_quality_policy","observation_domain":"normalized_market_observation","policy_name":"upstox_nse_nifty_index_derivatives_quality","provider":"upstox"}` | `sha256:eb8daac12517a8e65f25e2a0aee14cda8eeb4a3b2308a80719f747bdcb333d01` |
| `{"entity":"market_data_quality_policy_version","policy_id":"sha256:0000000000000000000000000000000000000000000000000000000000000000","version":"1"}` | `sha256:85eafa1a1b1517e373c0784d2842d11b065cd8c0ae3502d1aeb1398e4bea929d` |
| `{"at":"2026-08-07T12:34:56.123456+00:00","entity":"canonical_hash_test","price":"100.05","text":"ASCII","values":[null,true,"0","-3"]}` | `sha256:dcadb9cc36527b1507f5edb90916e72ea9cf774d65fa29b07d76829b52e2b0f8` |

---

## 6. Frozen reason registry

Registry ordinals are contiguous and immutable. `rule_id` is `quality.<reason_code>`; a rule may emit multiple occurrences only through distinct permitted subject keys.

| Ordinal | Reason code | Severity | Applicability | Permitted subject key(s) | Evidence profile |
|---:|---|---|---|---|---|
| 1 | `historical_import_availability` | warning | all targets | `observation` | `availability` |
| 2 | `quote_age_warning` | warning | quote targets | `observation` | `age` |
| 3 | `status_age_warning` | warning | status target or status dependency | `market_segment_status` | `age` |
| 4 | `market_locked` | warning | quote targets with two-sided book | `bid_ask_spread` | `quote_pair` |
| 5 | `spread_warning` | warning | uncrossed quote targets | `bid_ask_spread` | `spread` |
| 6 | `unadopted_schema_paths_present` | warning | quote targets | `observation` | `path_set` |
| 7 | `present_unadopted_message_paths` | warning | quote targets | `observation` | `path_set` |
| 8 | `secondary_payload_paths_present` | warning | quote targets | `observation` | `path_set` |
| 9 | `depth_truncated` | warning | quote targets | `observation` | `depth` |
| 10 | `unsupported_provider` | error | all targets | `observation` | `identity` |
| 11 | `unsupported_normalization_schema` | error | all targets | `observation` | `schema` |
| 12 | `unsupported_subject_scope` | error | all targets | `observation` | `scope` |
| 13 | `provider_timestamp_in_future` | error | all targets | `observation` | `future_offset` |
| 14 | `quote_stale` | error | quote targets | `observation` | `age` |
| 15 | `status_stale` | error | status target or status dependency | `market_segment_status` | `age` |
| 16 | `availability_basis_invalid` | error | all targets | `observation` | `availability` |
| 17 | `required_last_price_missing` | error | underlying quote | `last_price` | `field_presence` |
| 18 | `bid_missing` | error | future/option quote | `bid_price` | `field_presence` |
| 19 | `ask_missing` | error | future/option quote | `ask_price` | `field_presence` |
| 20 | `bid_size_missing` | error | future/option quote | `bid_size` | `field_presence` |
| 21 | `ask_size_missing` | error | future/option quote | `ask_size` | `field_presence` |
| 22 | `one_sided_quote` | error | underlying quote | `bid_ask_spread` | `field_presence` |
| 23 | `orphan_quote_component` | error | quote targets | `bid_size|ask_size|last_size|last_trade_at` | `field_presence` |
| 24 | `invalid_numeric_value` | error | quote targets | `controlled numeric field` | `numeric` |
| 25 | `bid_zero` | error | future/option quote | `bid_price` | `numeric` |
| 26 | `ask_zero` | error | future/option quote | `ask_price` | `numeric` |
| 27 | `bid_size_zero` | error | future/option quote | `bid_size` | `numeric` |
| 28 | `ask_size_zero` | error | future/option quote | `ask_size` | `numeric` |
| 29 | `last_price_zero` | error | quote targets | `last_price` | `numeric` |
| 30 | `market_crossed` | error | quote targets with two-sided book | `bid_ask_spread` | `quote_pair` |
| 31 | `spread_limit_exceeded` | error | uncrossed quote targets | `bid_ask_spread` | `spread` |
| 32 | `tick_size_missing_or_invalid` | error | quote targets | `instrument_version` | `dependency` |
| 33 | `price_not_tick_aligned` | error | quote targets | `bid_price|ask_price|last_price` | `tick` |
| 34 | `resolution_cutoff_after_evaluation` | error | quote targets | `observation` | `cutoff` |
| 35 | `instrument_version_missing` | error | quote targets | `instrument_version` | `dependency` |
| 36 | `instrument_version_ambiguous` | error | quote targets | `instrument_version` | `dependency_ambiguity` |
| 37 | `instrument_version_mismatch` | error | quote targets | `instrument_version` | `dependency_compare` |
| 38 | `instrument_version_not_effective` | error | quote targets | `instrument_version` | `dependency` |
| 39 | `instrument_trading_status_not_active` | error | quote targets | `instrument_version` | `state` |
| 40 | `provider_mapping_missing` | error | quote targets | `provider_mapping` | `dependency` |
| 41 | `provider_mapping_ambiguous` | error | quote targets | `provider_mapping` | `dependency_ambiguity` |
| 42 | `provider_mapping_mismatch` | error | quote targets | `provider_mapping` | `dependency_compare` |
| 43 | `provider_mapping_not_effective` | error | quote targets | `provider_mapping` | `dependency` |
| 44 | `catalogue_provenance_missing` | error | quote targets | `catalogue_version` | `dependency` |
| 45 | `catalogue_provenance_ambiguous` | error | quote targets | `catalogue_version` | `dependency_ambiguity` |
| 46 | `catalogue_provenance_mismatch` | error | quote targets | `catalogue_version` | `dependency_compare` |
| 47 | `catalogue_provenance_not_effective` | error | quote targets | `catalogue_version` | `dependency` |
| 48 | `provider_segment_unresolvable` | error | all targets | `provider_segment` | `segment` |
| 49 | `provider_segment_mismatch` | error | all targets | `provider_segment` | `segment` |
| 50 | `trading_session_missing` | error | all targets | `trading_session` | `dependency` |
| 51 | `trading_session_ambiguous` | error | all targets | `trading_session` | `dependency_ambiguity` |
| 52 | `trading_session_timezone_mismatch` | error | all targets | `trading_session` | `session` |
| 53 | `trading_session_not_scheduled` | error | all targets | `trading_session` | `session` |
| 54 | `outside_regular_session` | error | all targets | `trading_session` | `session` |
| 55 | `segment_status_missing` | error | quote targets | `market_segment_status` | `dependency` |
| 56 | `segment_status_ambiguous` | error | quote targets | `market_segment_status` | `dependency_ambiguity` |
| 57 | `segment_status_unknown` | error | all targets | `market_segment_status` | `state` |
| 58 | `segment_not_normal_open` | error | all targets | `market_segment_status` | `state` |
| 59 | `connection_state_missing` | error | all targets | `connection_session` | `dependency` |
| 60 | `connection_state_ambiguous` | error | all targets | `connection_session` | `dependency_ambiguity` |
| 61 | `connection_not_authorized` | error | all targets | `connection_session` | `lifecycle` |
| 62 | `connection_state_stale` | error | all targets | `connection_session` | `lifecycle_age` |
| 63 | `subscription_state_missing` | error | quote targets | `subscription_scope` | `dependency` |
| 64 | `subscription_state_ambiguous` | error | quote targets | `subscription_scope` | `dependency_ambiguity` |
| 65 | `subscription_not_active` | error | quote targets | `subscription_scope` | `lifecycle` |
| 66 | `subscription_mode_mismatch` | error | quote targets | `subscription_scope` | `subscription` |
| 67 | `subscription_instrument_missing` | error | quote targets | `subscription_scope` | `subscription` |
| 68 | `subscription_state_stale` | error | quote targets | `subscription_scope` | `lifecycle_age` |
| 69 | `ambiguous_active_subscription` | error | quote targets | `subscription_scope` | `dependency_ambiguity` |

### 6.1 Evidence profiles

Every reason stores schema version `1`, its subject key, sorted unique named values, sorted unique dependency IDs, and no provider free text. Profiles define exact names/types/units:

| Profile | Required evidence |
|---|---|
| `identity` | `expected_provider`, `observed_provider` as controlled text; target event ID in dependency IDs |
| `schema` | observed/expected normalization schema integer and implementation controlled text |
| `scope` | catalogue profile, target kind/segment, membership or target dependency ID |
| `future_offset` | provider timestamp, market cutoff, `future_offset_ms` decimal milliseconds |
| `age` | observed timestamp, cutoff, `age_ms`, warning/error threshold milliseconds |
| `availability` | availability basis and available timestamp |
| `field_presence` | field name and controlled `present/absent` state |
| `numeric` | field name and canonical numeric value; no non-finite text is persisted |
| `quote_pair` | bid and ask prices, comparison state |
| `tick` | field price, tick size, exact remainder, instrument-version dependency ID |
| `spread` | spread ticks/bps plus all four warning/error thresholds |
| `cutoff` | persisted resolution market/knowledge cutoffs and assessment cutoffs |
| `dependency` | dependency ID, candidate count, T, K, search-scope hash |
| `dependency_ambiguity` | dependency ID, candidate count, candidate-set hash; full candidates remain in typed candidate rows |
| `dependency_compare` | persisted and selected semantic/record IDs |
| `state` | selected state/status and dependency ID |
| `segment` | provider key/segment derivation result as controlled text |
| `session` | exchange date, session IDs, timezone/status/open/close and T |
| `lifecycle` | selected lifecycle event ID, state, occurred timestamp |
| `lifecycle_age` | selected event ID, occurred timestamp, T, exact age and 43,200,000 ms lease |
| `subscription` | scope ID, target key hash, request modes, instrument-set digest |
| `path_set` | exact count and `stable_hash(sorted_paths)`; target event ID reconstructs the exact path set |
| `depth` | provider depth, normalized depth, truncated count |

Named evidence arrays contain at most 16 entries and candidate IDs in reason evidence contain at most 16. Candidate sets larger than 16 are never truncated in durable truth: all candidates are persisted in `market_data_quality_dependency_candidates`, while reason evidence carries count and hash.

---

## 7. Evaluation and reason precedence

### 7.1 Quote formulas

```text
quote_age_ms = (evaluation_market_as_of - provider_timestamp) / 1 millisecond
spread       = ask_price - bid_price
mid          = (ask_price + bid_price) / 2
spread_ticks = spread / tick_size
spread_bps   = (spread / mid) * 10000
aligned      = price % tick_size == 0
```

All operations use `Decimal`; datetime differences are converted from exact integer microseconds to Decimal milliseconds. No binary float or epsilon is permitted.

Examples:

- `100.05 % 0.05 = 0`: aligned; `100.03 % 0.05 = 0.03`: off tick.
- underlying live age `2999.999 ms`: clean; `3000.000`: warning; `9999.999`: warning; `10000.000`: error only.
- lifecycle age `43200000.000 ms`: accepted; `43200000.001`: stale.
- equal bid/ask emits `market_locked` and suppresses spread reasons; bid one tick above ask emits `market_crossed` and suppresses locked/spread reasons.
- spread dimension states are classified independently; any error emits only `spread_limit_exceeded`, otherwise any warning emits only `spread_warning`.

### 7.2 Dependency-family precedence

For mapping, instrument version, catalogue, and session:

1. validate the temporal graph; malformed graph is durable corruption;
2. filter asserted `recorded_at <= K` and typed receipt `receipt_at <= K`;
3. filter market/effective eligibility at T;
4. zero effective leaves: if no visible knowledge leaf, emit `*_missing`; otherwise emit `*_not_effective` where that code exists;
5. multiple effective leaves: emit `*_ambiguous` and persist every candidate; do not choose by ID;
6. one leaf: compare its semantic and record IDs with persisted provenance, emitting `*_mismatch` if different;
7. dependent rules run only when their prerequisite dependency is singular and usable.

This makes missing/not-effective/ambiguous/mismatch mutually exclusive inside each provenance family while allowing independent families to report simultaneously.

### 7.3 Subscription precedence

- Any equal-rank conflicting state inside any visible scope containing the target key produces one aggregated `subscription_state_ambiguous`; no scope is selected.
- Otherwise, more than one active containing scope produces `ambiguous_active_subscription`.
- Exactly one active containing scope may independently produce mode mismatch and stale reasons.
- With no active containing scope, emit exactly one of state missing, not active, or instrument missing according to the requirements staging rules.

---

## 8. Numbered orchestration algorithm

1. **Validate command.** Require policy-version ID, aware UTC M/K, `K >= M`, 1–5,000 target IDs, canonical SHA-256 IDs, and no duplicate target IDs after canonical sorting.
2. **Precompute target order.** Sort unique event IDs lexicographically. No input order enters identity.
3. **Start transaction.** Enter one new writable `PostgresUnitOfWork` at `REPEATABLE READ`; the instance is final/non-reusable.
4. **Read policy bundle.** Load the exact policy version, policy row, all 69 reason definitions, and at least one source artifact. Recompute identities/hashes and compatibility. No latest selection.
5. **Load visible targets in bulk.** For each supplied event ID, join observation, typed subtype, exact result/event membership, result, and raw frame; filter `event.available_at <= K` and `result.persistence_recorded_at <= K`. Do not filter provider/schema compatibility here.
6. **Apply all-or-nothing visibility.** If any supplied ID has no knowledge-visible target, return the same `target_not_visible` outcome for the entire command, listing only the caller-supplied IDs in canonical order, and roll back without writing a run or any child row.
7. **Bind roots.** Recompute event/result/raw identities, membership counts, subtype shape, and canonical payload hashes. Any mismatch is durable corruption.
8. **Compute T.** For each target set `T = min(provider_timestamp, M)` and derive exchange date in `Asia/Kolkata`.
9. **Resolve dependencies in plural.** Execute the exact queries in §9, persisting selected, absent, or ambiguous manifests and every present candidate with real FKs.
10. **Create absence proofs.** For each zero-candidate applicable dependency, bind dependency kind, subject key, semantic search scope, T, K, selection-rule version, and `absent` outcome.
11. **Determine applicability.** Use policy target-kind matrix. Status targets do not resolve themselves as status dependencies and do not resolve quote-only mapping/version/catalogue/subscription dependencies.
12. **Evaluate all independent rules.** Collect every applicable reason. A missing prerequisite suppresses only rules that require that dependency; it does not stop unrelated rules.
13. **Canonicalize reasons.** Validate each occurrence against its reason definition, deduplicate by `(reason_code, subject_key)`, then sort by `(registry ordinal, reason code, subject key)`.
14. **Reduce disposition and compute identities.** Build reason-set hash, dependency-closure hash, assessment payload/hash, assessment IDs, and run ID including run schema `1`.
15. **Acquire locks.** Derive roots for policy version, every assessment, and run; deduplicate stripes and acquire sorted two-key PostgreSQL advisory transaction locks using §11.
16. **Persist in bounded chunks.** Insert-or-compare policy artifacts if registering, run, assessments, reasons, dependency roots, typed candidates, and memberships. Root rows are inserted before deferred-validated children.
17. **Read back and reconstruct.** In the same snapshot, reload complete bundles, verify contiguous ordinals/counts/FKs, recompute canonical hashes and disposition, and compare byte-for-byte with the plan.
18. **Commit or classify retry.** Commit once. Exact existing content returns `inserted=false`; immutable differences raise typed collision; serialization/deadlock is retried by the outer service at most three times with a fresh UoW and no change to command inputs.

No step reads wall-clock time for semantic evaluation. Database transaction time is used only for non-semantic registration, persistence, and receipt evidence.

---

## 9. Dependency selection specification

All selectors use `T = dependency_market_as_of` and `K = evaluation_known_as_of`.

| Kind / subject | Scope and exact query predicates | Ordering/conflict rule | Absence/ambiguity reason | Present FK material |
|---|---|---|---|---|
| Provider mapping / `provider_mapping` | provider + provider key; load the complete scope graph where `recorded_at<=K` and `receipt_at<=K`; apply semantic interval containment at T only after graph validation | validate complete supersession graph; then select effective leaves, never ID winner | missing/not-effective/ambiguous; mismatch after singular selection | mapping ID + record ID composite FK |
| Instrument version / `instrument_version` | target economic subject ID; load complete knowledge-visible scope graph using record and receipt cutoffs; apply validity containment at T after graph validation | same complete-graph rule | missing/not-effective/ambiguous/mismatch | version ID + record ID composite FK |
| Catalogue / `catalogue_version` | provider `upstox`; load complete knowledge-visible scope graph through record/receipt cutoffs; apply effective interval at T after graph validation | same complete-graph rule | missing/not-effective/ambiguous/mismatch | catalogue version + record + ingestion run FKs |
| Catalogue membership / `catalogue_membership` | selected catalogue, target provider key, target semantic IDs; exact profile run `upstox-nse-nifty-index-derivatives-v1`; membership receipt `<=K` | zero/one only; multiple differing memberships is durable corruption because catalogue constraints require uniqueness | `unsupported_subject_scope` | catalogue membership + ingestion run + membership receipt FKs |
| Trading session / `trading_session` | exchange `NSE`, date derived from T in policy timezone, kind `regular`; session version records/receipt visible by K | graph leaves; value-only resolver prohibited | missing/ambiguous, then timezone/status/open rules | session version + record composite FK |
| Segment status / `market_segment_status` | exact provider segment; observation timestamp `<=T`; `available_at<=K`; owning result persistence `<=K` | greatest provider timestamp; greatest source order within scope; exact payload duplicates benign; conflicting equal rank ambiguous | missing/ambiguous, then unknown/not-open | event/result/raw membership FKs |
| Connection / `connection_session` | raw frame's exact connection session; lifecycle `occurred_at<=T`, `available_at<=K`; owning lifecycle batch persistence `<=K` | greatest occurred time and source order; cross-scope equal-rank conflict ambiguous | missing/ambiguous, then not-authorized/stale | lifecycle event/kind/batch membership FKs |
| Subscription / `subscription_scope` | provider + connection; all visible scopes at T/K; selected latest state per scope; exact set digest and keys | internal scope ambiguity first; then active-containing cardinality | state missing/ambiguous/not-active/mode/instrument/stale/multiple-active | lifecycle event/kind/batch plus instrument-set digest FKs |

`search_scope_payload` is canonical JSON. `selection_rule_version` is one of:

```text
temporal-successor-graph-with-receipt-v1
ranked-market-status-v1
ranked-connection-lifecycle-v1
staged-subscription-scope-v1
catalogue-membership-profile-v1
```

The generic dependency root never stores a bare arbitrary record ID. Every selected or ambiguous candidate is materialized in the checked typed-candidate table.

---

## 10. Persistence design

### 10.1 Common conventions

- IDs/hashes: `VARCHAR(71)` matching `^sha256:[0-9a-f]{64}$`.
- Controlled names: `VARCHAR(128)` with ASCII shape checks.
- Opaque provider/session/scope keys: `VARCHAR(512)` with trim/control checks.
- Decimal evidence: `NUMERIC(38,18)` where typed; canonical JSON strings elsewhere.
- All timestamps are finite `TIMESTAMPTZ`.
- JSON objects/arrays receive `jsonb_typeof` checks and application canonical-hash verification.
- All DATA-1.5 tables reject `UPDATE`, `DELETE`, and `TRUNCATE`.

### 10.2 Exact tables

#### `market_data_quality_policies`

Columns: `policy_id` PK, `policy_name`, `provider`, `observation_domain`, `canonical_payload` JSONB, `canonical_payload_hash`.  
Unique: `uq_data15_policy_semantic_name(policy_name,provider,observation_domain)`.  
Checks: `data15_policy_id_sha256`, `data15_policy_name_shape`, `data15_policy_provider_upstox`, `data15_policy_domain`, `data15_policy_payload_object`, `data15_policy_payload_hash_sha256`.  
Index: `ix_data15_policies_provider_name(provider,policy_name,policy_id)`.

#### `market_data_quality_policy_versions`

Columns: `policy_version_id` PK, `policy_id` FK, `version`, `quality_policy_schema_version`, `quality_evaluator_implementation_version`, `policy_definition_hash`, `semantic_payload` JSONB, `reason_count`, `registered_at`.  
Unique: `uq_data15_policy_versions_policy_number(policy_id,version)` and composite `uq_data15_policy_versions_id_policy(policy_version_id,policy_id)`.  
Checks: version/schema exactly `1`, evaluator label exact, reason count `69`, finite registration time, hash/payload shape.  
Indexes: policy/version and registration order.

`registered_at` is non-semantic. Concurrent exact registration keeps the first inserted timestamp; equality comparison excludes it and compares every semantic field.

#### `market_data_quality_policy_source_artifacts`

Columns: `source_artifact_id` PK, `policy_version_id` FK, `source_sha256`, `source_byte_count`, `media_type`, `parser_label`, `source_bytes` BYTEA, `canonical_payload_hash`, `registered_at`.  
Unique: `uq_data15_policy_artifacts_version_source(policy_version_id,source_sha256)`.  
Checks: bytes `1..262144`, byte count equals octet length, fixed media/parser, hashes, finite time.  
Index: version/source.

#### `market_data_quality_policy_reason_definitions`

Columns: `reason_definition_id` PK, `policy_version_id` FK, `reason_code`, `registry_ordinal`, `severity`, `applicable_target_kinds` JSONB array, `subject_keys` JSONB array, `evidence_profile`, `canonical_payload` JSONB, `canonical_payload_hash`.  
Unique: version/code, version/ordinal, and composite identity tuple used by assessment-reason FK.  
Checks: ordinal `1..69`, severity, controlled code/profile, JSON arrays/objects.  
Indexes: version/ordinal and code.

#### `market_data_quality_assessment_runs`

Columns: `assessment_run_id` PK, `assessment_run_schema_version`, `policy_version_id` FK, M, K, evaluator label, `target_count`, `ordered_target_event_ids` JSONB, `target_set_hash`, `canonical_payload_hash`, `persistence_recorded_at`.  
Checks: schema `1`, `K>=M`, target count `1..5000`, JSON array/count, evaluator label, finite time.  
Indexes: policy/context/run and persistence order.

#### `market_data_quality_assessments`

Columns: `assessment_id` PK; `event_id`, `raw_event_id`, `result_id`; `target_event_type`, `subject_id`; `policy_id`, `policy_version_id`; M, K, T; `market_time_basis`; `disposition`; `reason_count`, `reason_set_hash`; `dependency_count`, `dependency_closure_hash`; `assessment_payload` JSONB, `assessment_payload_hash`; `policy_registered_after_known_as_of`; `persistence_recorded_at`.  
FKs: event/raw to `market_observations`; result/raw to `market_normalization_results`; result/event to `market_normalization_result_events`; policy/version composites.  
Unique: exact lookup `(event_id,policy_version_id,M,K)` and `(assessment_id,event_id)` for membership.  
Checks: M/K/T ordering, T equals neither database default nor mutable value (application recomputation), disposition, counts `0..128` reasons and `0..16` dependency roots, hashes, payload object, finite time.  
Indexes: exact lookup; policy/context/disposition; event audit; persistence.

#### `market_data_quality_assessment_reasons`

Columns: `reason_occurrence_id` PK, `assessment_id` FK, `policy_version_id`, `reason_definition_id`, `reason_code`, `registry_ordinal`, `severity`, `subject_key`, `reason_ordinal`, `evidence` JSONB, `evidence_hash`.  
Composite FK binds exact definition/version/code/ordinal/severity.  
Unique: `(assessment_id,reason_code,subject_key)` and `(assessment_id,reason_ordinal)`.  
Checks: reason ordinal `0..127`, evidence object/schema, controlled subject, hashes.  
Indexes: assessment/order and reason code.

#### `market_data_quality_assessment_dependencies`

Columns: `assessment_dependency_id` PK, `assessment_id` FK, `dependency_ordinal`, `dependency_kind`, `subject_key`, `outcome`, T, K, `selection_rule_version`, `candidate_count`, `selected_candidate_ordinal`, `search_scope_payload` JSONB/hash, `canonical_payload` JSONB/hash.  
Unique: `(assessment_id,dependency_kind,subject_key)`, `(assessment_id,dependency_ordinal)`, and `(assessment_dependency_id,dependency_kind)`.  
Checks: dependency ordinal `0..15`; candidate/outcome shape: selected=`1/0`, absent=`0/NULL`, ambiguous=`2..5000/NULL`; controlled kinds; payloads/hashes.  
Indexes: assessment/order and kind/outcome.

#### `market_data_quality_dependency_candidates`

PK `(assessment_dependency_id,candidate_ordinal)`; columns include `dependency_kind`, `candidate_content_hash`, `candidate_payload` JSONB and these typed nullable FK groups:

- market candidate: `market_event_id`, `market_result_id`, `market_raw_event_id`;
- mapping: `provider_mapping_record_id`, `provider_mapping_id`;
- instrument: `instrument_version_record_id`, `instrument_version_id`;
- catalogue: `catalogue_record_id`, `catalogue_version_id`, `catalogue_ingestion_run_id`;
- membership: `catalogue_membership_id`, `catalogue_ingestion_run_id`;
- session: `trading_session_record_id`, `trading_session_version_id`;
- lifecycle: `lifecycle_event_id`, `lifecycle_kind`, `lifecycle_batch_id`, optional `instrument_keys_digest` for subscription.

Composite FK to dependency root binds kind. Every typed group has real FKs to the exact existing semantic/temporal/membership rows. `data15_dependency_candidate_kind_shape` requires exactly the columns for its kind and all other typed columns NULL. Candidate ordinal is `0..4999`; unique content hash per dependency prevents duplicate candidates.  
Indexes: dependency/order; every typed FK access path.

#### `market_data_quality_run_assessments`

Columns: `assessment_run_id`, `target_ordinal`, `event_id`, `assessment_id`.  
PK run/ordinal; unique run/event and run/assessment.  
Composite FK `(assessment_id,event_id)` and direct event FK.  
Check ordinal `0..4999`.  
Indexes: assessment-to-runs and event audit.

#### Five receipt tables

```text
market_data_quality_provider_mapping_receipts(record_id FK provider_mapping_records)
market_data_quality_instrument_version_receipts(record_id FK instrument_version_records)
market_data_quality_catalogue_version_receipts(record_id FK catalogue_version_records)
market_data_quality_trading_session_receipts(record_id FK trading_session_version_records)
market_data_quality_catalogue_membership_receipts(membership_id FK catalogue_memberships, ingestion_run_id FK catalogue_ingestion_runs)
```

The four temporal tables have primary key `record_id`; the membership table has primary key `membership_id`. Every table stores `receipt_at TIMESTAMPTZ`, `receipt_basis VARCHAR(32)`, nullable `bootstrap_revision VARCHAR(32)`, and `canonical_payload_hash VARCHAR(71)`. `legacy_bootstrap` requires revision `20260804_05`; `repository_insert` requires NULL bootstrap revision. Index `(receipt_at,<primary-key>)` is mandatory.

The membership receipt additionally stores the exact `ingestion_run_id`. A deferred consistency trigger verifies that the membership's `row_outcome_id` resolves to that same ingestion run. Membership receipt visibility prevents a later membership attached to an older catalogue version from entering an earlier `(M,K)` closure.

### 10.3 Deferred aggregate validation

- `data15_validate_policy_reason_registry()` checks exactly 69 contiguous definitions and version reason count.
- `data15_validate_assessment_aggregate()` checks reason/dependency counts, contiguous ordinals, reason severity reduction, and no children under another policy version.
- `data15_validate_dependency_aggregate()` checks candidate count/ordinals/outcome and exact typed shape.
- `data15_validate_run_membership()` checks target count, contiguous ordinals, ordered event list, and assessment context/policy equality.

Application read-back additionally recomputes every canonical hash; PostgreSQL is not extended with `pgcrypto`.

### 10.4 Durable snapshot order

Receipts first after their existing target tables, then policy → version → artifact/reasons → run → assessment → reason/dependency → candidate → membership. Snapshot query orders each table by its primary key and hashes the complete typed row payload.

---

## 11. Transaction, locks, retries, and bulk I/O

### 11.1 Advisory locks

```text
DATA15_ADVISORY_LOCK_NAMESPACE = -806150233
DATA15_LOCK_STRIPE_COUNT = 128
```

Namespace derivation is the signed first four bytes of SHA-256 over ASCII `quantkynd:data15:market-data-quality:v1`; it differs from DATA-1.4 `-1377601296`.

```text
stripe = int(SHA256(
  b"data15-lock-stripe-v1\0" + entity_namespace + b"\0" + canonical_id
)) mod 128
```

Frozen vectors:

| Root | Canonical ID | Stripe |
|---|---|---:|
| `policy_version` | `sha256:` + 64 zeroes | 125 |
| `assessment` | `sha256:` + 64 ones | 76 |
| `assessment_run` | `sha256:` + 64 twos | 83 |

Acquire deduplicated stripes ascending through `pg_advisory_xact_lock(namespace,stripe)` before any DATA-1.5 write.

### 11.2 Chunking

Reuse `plan_parameter_chunks(item_count, parameters_per_item, budget=60000)`. Maximum rows per statement are `min(1000, floor(60000/parameters_per_item))`. All proposed row shapes therefore cap at 1,000 rows per statement; 5,000-target runs use at most five chunks per table family. No awaited statement per reason or dependency is permitted.

### 11.3 Retry behavior

- unique conflict followed by equal immutable read-back: idempotent success;
- unique conflict followed by unequal immutable content: typed collision;
- PostgreSQL serialization failure/deadlock: rollback and retry entire command with a fresh UoW, maximum three attempts;
- referential/constraint failure: rollback and classify as integrity/corruption, never retry as quality warning;
- process crash before commit: no visible DATA-1.5 partial truth.

---

## 12. Migration `20260804_05`

Filename and ancestry:

```text
backend/alembic/versions/20260804_05_versioned_market_data_quality_policy.py
revision = "20260804_05"
down_revision = "20260804_04"
```

Upgrade order:

1. add `uq_trading_session_version_records_record_semantic(record_id,session_version_id)`;
2. create policy and policy-version tables;
3. create source-artifact and reason-definition tables;
4. create run and assessment tables;
5. create reason, dependency, candidate, and membership tables;
6. create five typed receipt tables;
7. capture one `transaction_timestamp()` as `legacy_receipt_at` and backfill every existing temporal record and catalogue membership in deterministic table/primary-key order with basis `legacy_bootstrap`;
8. create receipt-completeness deferrable constraint triggers on the the four existing temporal record tables and `catalogue_memberships` and `catalogue_memberships`;
9. create aggregate-validation functions/triggers;
10. create DATA-1.5 append-only row and truncate triggers on every DATA-1.5 table;
11. run deterministic row-count reconciliation and schema-object verification.

Post-migration temporal writers insert `repository_insert` receipts in the same transaction as new records. The receipt trigger rejects a commit missing that row.

Downgrade:

1. inspect all DATA-1.5 tables in sorted name order; if any contains a row, raise one deterministic error listing every non-empty table;
2. drop receipt-completeness triggers from existing temporal tables;
3. drop DATA-1.5 aggregate and append-only triggers/functions by exact name, without `IF EXISTS`;
4. drop DATA-1.5 tables in reverse FK order;
5. drop the owned session-record composite unique constraint;
6. verify schema equals `20260804_04` expected objects.

The migration does not alter roles, DATA-1.4 trigger ownership, or DATA-1.4 permissive downgrade clauses.

---

## 13. Repository and query contracts

```python
class MarketDataQualityRepository(Protocol):
    async def register_policy_bundle(self, bundle: PolicyRegistrationBundle) -> PolicyRegistrationResult: ...
    async def get_policy_bundle(self, policy_version_id: str) -> QualityPolicyBundle | None: ...
    async def load_visible_targets(self, event_ids: tuple[str, ...], known_as_of: datetime) -> tuple[TargetBundle, ...]: ...
    async def list_provider_mapping_candidates(self, scope: MappingScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_instrument_version_candidates(self, scope: InstrumentScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_catalogue_candidates(self, scope: CatalogueScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_catalogue_membership_candidates(self, scope: MembershipScope) -> DependencyCandidates: ...
    async def list_trading_session_candidates(self, scope: SessionScope, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_segment_status_candidates(self, scope: SegmentScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_connection_candidates(self, scope: ConnectionScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def list_subscription_scope_candidates(self, scope: SubscriptionScope, market_as_of: datetime, known_as_of: datetime) -> DependencyCandidates: ...
    async def acquire_write_locks(self, roots: tuple[LockRoot, ...]) -> None: ...
    async def persist_assessment_run(self, plan: AssessmentRunPlan) -> PersistenceResult: ...
    async def get_assessment_exact(self, event_id: str, policy_version_id: str, market_as_of: datetime, known_as_of: datetime) -> QualityAssessmentBundle | None: ...
    async def list_assessments_for_audit(self, cursor: AuditCursor, limit: int) -> tuple[QualityAssessmentBundle, ...]: ...
    async def reconstruct_run(self, assessment_run_id: str) -> QualityAssessmentRunBundle | None: ...
```

`TradingSessionRepository` gains:

```python
@dataclass(frozen=True)
class TradingSessionVersionState:
    value: TradingSessionVersion
    record_id: str

async def resolve_state(exchange, session_date, session_kind, known_as_of) -> TradingSessionVersionState | None
```

No method name contains `latest_eligible`, `current_policy`, `option_chain`, or implicit fallback semantics.

---

## 14. Point-in-time compatibility response

After design approval:

- remove the provisional `QuoteQualityDisposition` definition and import canonical `QualityDisposition` under that compatibility name only if required by existing internal imports;
- replace provisional `DataQualityAssessment` with an immutable read view backed by exact DATA-1.5 assessment fields; its identity does not include run, disposition, or reasons;
- change `PointInTimeQuery` to carry exact `quality_policy_version_id` and mandatory `known_as_of`;
- replace `_selected_assessment` latest-by-recorded-time behavior with exact key matching on event, policy version, M, and K; zero returns none, more than one raises durable corruption;
- do not add a runtime caller or persistence adapter to `reconstruct_option_chain` in DATA-1.5.

There is one disposition vocabulary and one assessment identity. The compatibility change is covered by focused tests and does not claim chain reconstruction acceptance.

---

## 15. Error taxonomy

```text
MarketDataQualityError
├── PolicyDocumentError
│   ├── PolicySourceEncodingError
│   ├── PolicyDuplicateKeyError
│   ├── PolicyUnknownKeyError
│   ├── PolicyScalarTypeError
│   └── PolicySemanticValidationError
├── PolicyCompatibilityError
│   ├── UnsupportedPolicySchemaError
│   └── UnsupportedQualityEvaluatorError
├── QualityCommandError
│   ├── InvalidQualityEvaluationCommandError
│   ├── UnsupportedObservationKindError
│   └── TargetNotVisibleOutcome              # non-exception result in service API
├── DependencySelectionError
│   └── DependencyAmbiguityError             # singular convenience APIs only; evaluator uses candidate result
├── QualityCollisionError
│   ├── PolicyIdentityCollisionError
│   ├── PolicyVersionCollisionError
│   ├── ReasonRegistryCollisionError
│   ├── AssessmentIdentityCollisionError
│   ├── DependencyClosureCollisionError
│   ├── AssessmentRunCollisionError
│   └── RunMembershipCollisionError
├── QualityPersistenceError
│   ├── QualityReferentialIntegrityError
│   ├── QualityDurableCorruptionError
│   └── QualityPersistenceStateError
└── QualityConcurrencyError
    ├── QualitySerializationFailure
    └── QualityRetryExhaustedError
```

Expected missing/ambiguous/ineffective/mismatched market states are data-quality reasons, not thrown run errors. An exception is raised only when a caller asks a singular convenience resolver or durable integrity is impossible to reconstruct safely.

---

## 16. Test and acceptance matrix

| Requirement family | Unit | PostgreSQL/focused | Concurrency/leakage | Migration/restore evidence |
|---|---|---|---|---|
| Parser/canonical policy | parser, vectors, equivalent bytes, semantic collision | policy registration/read-back | concurrent equal/conflicting registration | artifact/policy hashes in snapshot |
| Identity and reason registry | contracts, 69 ordinals, evidence profiles | PK/unique/FK/check/read reconstruction | hash-seed/locale/TZ subprocess tests | dump/restore identical hashes |
| Target visibility | evaluator/service | cutoff-limited target join | future result persistence and mixed invisible batch | restored exact visibility |
| Temporal dependencies/receipts | dependency-resolution unit | receipt-aware candidate SQL, graph/absence proofs | post-K insert/correction matrix | legacy bootstrap counts/time; restore |
| Quote/status rules | boundary vector suites | persisted reason/evidence reconstruction | same M/different K and vice versa | reason hashes restored |
| Lifecycle/subscription | state-machine/rank tests | batch persistence and set FKs | future authorize/unsubscribe/mode change; equal-rank conflicts | lifecycle dependency candidates restored |
| Persistence/atomicity | plan equality | append-only, aggregate triggers, rollback no orphans | identical/conflicting overlapping runs and deadlock timeout | nonempty downgrade refusal; cycle; dump/restore |
| Point-in-time compatibility | exact selector tests | exact assessment repository lookup | no latest fallback under concurrent inserts | no chain runtime path in changed-file scan |

Commands planned:

```bash
cd backend
uv run pytest tests/unit/market_data/quality -q
uv run pytest tests/integration/postgres/test_data15_policy_repository.py -q
uv run pytest tests/integration/postgres/test_data15_assessment_repository.py -q
uv run pytest tests/integration/postgres/test_data15_dependency_receipts.py -q
uv run pytest tests/integration/postgres/test_data15_concurrency.py -q
uv run pytest tests/integration/postgres/test_data15_no_future_leakage.py -q
uv run pytest tests/integration/postgres/test_data15_migration.py -q
uv run pytest tests/integration/postgres/test_data15_restore.py -q
uv run pytest -q
```

Acceptance-critical PostgreSQL tests have zero skips and assert server/client major version `17`.

---

## 17. Design self-review matrix

| Adversarial case | Preventive mechanism | Required test |
|---|---|---|
| Same semantics, different YAML bytes | semantic version separate from source artifacts | formatting/comment/key-order permutations |
| Different threshold under version 1 | content-independent version ID plus semantic collision | threshold mutation collision |
| Event/result/raw collision | composite FKs and root hash reconstruction | corrupted identity fixture aborts |
| Future dependency insertion | T/K plus receipt filters and closure collision | each dependency class inserted after K |
| Equal-time conflict | candidate-set ranking; IDs only evidence order | status/lifecycle cross-scope conflict |
| Missing temporal record | canonical absence proof | missing mapping/version/catalogue/session cases |
| Two valid mapping branches | valid graph plus multiple effective leaves → ambiguity | dual effective branch fixture |
| Absent session/status/lifecycle | controlled reasons, no arbitrary default | one test per absence |
| Crossed/locked/zero/missing quote | explicit precedence and applicability | adjacent matrix vectors |
| Decimal exponent/remainder | source exponent rejection; exact Decimal modulo | `100.05`, `100.03`, signed zero, large scale |
| Freshness/lease boundary | exact Decimal ms, inclusive thresholds | threshold minus 1µs/exact/plus 1µs |
| Concurrent identical/conflicting runs | deterministic stripes, insert-or-compare, atomic transaction | barrier-orchestrated PostgreSQL tests |
| Crash before commit | one transaction, deferred children, rollback | injected failure before membership |
| Dump/restore physical reorder | PK-ordered snapshot and canonical hashes | shuffled physical restore equivalence |
| Downgrade partial data | sorted all-table nonempty scan | only child/candidate/receipt table populated |
| Hostile hash seed/locale/TZ | canonical JSON and explicit UTC/Asia-Kolkata | subprocess matrix with two hash seeds/locales/TZs |
| More than 16 ambiguous candidates | full typed candidate table; bounded reason hash/count | 17-candidate ambiguity fixture |
| One invisible target in batch | all-or-nothing preflight before run row | mixed visible/hidden/absent target batch |
| New temporal record without receipt | deferred receipt-completeness trigger | direct SQL insert missing receipt fails commit |

All mechanisms are implementation decisions frozen here; none is deferred to coding time.

---

## 18. Changed-files allowlist and scope proof

Implementation may change only the files/tree listed in §3 plus existing focused test fixtures and the final acceptance evidence. Any additional production file requires a design amendment and re-review.

Explicit absence proof:

- no option-chain reconstruction implementation or activation;
- no latest-state materialization;
- no implied volatility, surface, realized-volatility, edge, or strategy code;
- no trade/order/fill persistence;
- no Redis, websocket, live worker, FastAPI route, frontend, broker, or execution adapter;
- no PostgreSQL role separation;
- no edits to DATA-1.4 `IF EXISTS` hardening or trigger ownership;
- no provider SDK/Protobuf type in quality contracts;
- no new third-party dependency.

---


---

## 19. Exact PostgreSQL column, key, and index catalogue

This section is normative. `ID` means `VARCHAR(71)` with the canonical SHA-256 check; `NAME` means `VARCHAR(128)` with its controlled-text check; `KEY` means `VARCHAR(512)` with trim/control checks; every timestamp has finite-instant checks. All foreign keys use `ON UPDATE NO ACTION ON DELETE NO ACTION`.

### 19.1 Root and policy tables

| Table | Exact columns | Keys and checks | Required indexes |
|---|---|---|---|
| `market_data_quality_policies` | `policy_id ID NOT NULL`, `policy_name NAME NOT NULL`, `provider NAME NOT NULL`, `observation_domain NAME NOT NULL`, `canonical_payload JSONB NOT NULL`, `canonical_payload_hash ID NOT NULL`, `registered_at TIMESTAMPTZ NOT NULL` | PK `policy_id`; UQ `(policy_name,provider,observation_domain)`; payload object; payload hash equals reconstructed policy ID material; provider fixed `upstox` | UQ index above; `(provider,policy_name,policy_id)` |
| `market_data_quality_policy_versions` | `policy_version_id ID`, `policy_id ID`, `version INTEGER`, `policy_definition JSONB`, `policy_definition_hash ID`, `quality_policy_schema_version INTEGER`, `quality_evaluator_implementation_version NAME`, `normalization_schema_version INTEGER`, `normalizer_implementation_version NAME`, `reason_definition_count INTEGER`, `registered_at TIMESTAMPTZ` all NOT NULL | PK version ID; FK policy; UQ `(policy_id,version)`; UQ `(policy_version_id,policy_id)`; version/schema=1, evaluator/normalizer fixed labels, reason count=69, JSON object | `(policy_id,version)`, `(policy_definition_hash,policy_version_id)` |
| `market_data_quality_policy_source_artifacts` | `source_artifact_id ID`, `policy_version_id ID`, `source_sha256 ID`, `source_byte_count INTEGER`, `media_type NAME`, `parser_label NAME`, `source_bytes BYTEA`, `registered_at TIMESTAMPTZ` all NOT NULL | PK artifact; FK version; UQ `(policy_version_id,source_sha256,source_byte_count,media_type,parser_label)`; byte count `1..262144`; `octet_length(source_bytes)=source_byte_count`; media/parser fixed; source hash recomputed in application | `(policy_version_id,source_artifact_id)`, `(source_sha256,source_artifact_id)` |
| `market_data_quality_policy_reason_definitions` | `reason_definition_id ID`, `policy_version_id ID`, `reason_code NAME`, `registry_ordinal INTEGER`, `severity VARCHAR(16)`, `applicable_target_kinds JSONB`, `subject_keys JSONB`, `evidence_profile NAME`, `canonical_payload JSONB`, `canonical_payload_hash ID` all NOT NULL | PK definition; FK version; UQ `(policy_version_id,reason_code)`; UQ `(policy_version_id,registry_ordinal)`; UQ `(reason_definition_id,policy_version_id,reason_code,registry_ordinal,severity)` for exact child FK; ordinal `1..69`; severity warning/error; arrays nonempty; payload object | `(policy_version_id,registry_ordinal)`, `(reason_code,policy_version_id)` |

### 19.2 Run, assessment, reason, and dependency tables

| Table | Exact columns | Keys and checks | Required indexes |
|---|---|---|---|
| `market_data_quality_assessment_runs` | `assessment_run_id ID`, `assessment_run_schema_version INTEGER`, `policy_version_id ID`, `evaluation_market_as_of TIMESTAMPTZ`, `evaluation_known_as_of TIMESTAMPTZ`, `quality_evaluator_implementation_version NAME`, `target_count INTEGER`, `ordered_target_event_ids JSONB`, `canonical_payload JSONB`, `canonical_payload_hash ID`, `persistence_recorded_at TIMESTAMPTZ` all NOT NULL | PK run; FK version; UQ `(assessment_run_id,policy_version_id,evaluation_market_as_of,evaluation_known_as_of)`; schema=1; `K>=M`; count `1..5000`; ordered IDs array length=count, sorted/unique checked by deferred function; payload object | `(policy_version_id,evaluation_market_as_of,evaluation_known_as_of,assessment_run_id)`, `(persistence_recorded_at,assessment_run_id)` |
| `market_data_quality_assessments` | `assessment_id ID`, `event_id ID`, `raw_event_id ID`, `result_id ID`, `policy_id ID`, `policy_version_id ID`, `evaluation_market_as_of TIMESTAMPTZ`, `evaluation_known_as_of TIMESTAMPTZ`, `dependency_market_as_of TIMESTAMPTZ`, `market_time_basis NAME`, `target_kind VARCHAR(32)`, `disposition VARCHAR(16)`, `reason_count INTEGER`, `dependency_count INTEGER`, `reason_set_hash ID`, `dependency_closure_hash ID`, `canonical_payload JSONB`, `canonical_payload_hash ID`, `policy_registered_after_known_as_of BOOLEAN`, `persistence_recorded_at TIMESTAMPTZ` all NOT NULL | PK assessment; UQ exact lookup `(event_id,policy_version_id,M,K)`; UQ `(assessment_id,event_id)`; composite FKs `(event_id,raw_event_id)`→observations, `(result_id,raw_event_id)`→results, `(result_id,event_id)`→result-events, `(policy_version_id,policy_id)`→versions; `K>=M`, `T<=M`, controlled basis/kind/disposition, counts reason `0..127`, dependency `1..16`, payload object | exact lookup; `(policy_version_id,M,K,assessment_id)`; `(persistence_recorded_at,assessment_id)` |
| `market_data_quality_assessment_reasons` | `reason_occurrence_id ID`, `assessment_id ID`, `policy_version_id ID`, `reason_definition_id ID`, `reason_code NAME`, `registry_ordinal INTEGER`, `severity VARCHAR(16)`, `subject_key NAME`, `reason_ordinal INTEGER`, `evidence JSONB`, `evidence_hash ID` all NOT NULL | PK occurrence; FK assessment; composite FK exact reason definition tuple; UQ `(assessment_id,reason_code,subject_key)`; UQ `(assessment_id,reason_ordinal)`; ordinal `0..127`; evidence object/schema=1 | `(assessment_id,reason_ordinal)`, `(reason_code,assessment_id)` |
| `market_data_quality_assessment_dependencies` | `assessment_dependency_id ID`, `assessment_id ID`, `dependency_ordinal INTEGER`, `dependency_kind NAME`, `subject_key NAME`, `outcome VARCHAR(16)`, `market_cutoff TIMESTAMPTZ`, `knowledge_cutoff TIMESTAMPTZ`, `selection_rule_version NAME`, `candidate_count INTEGER`, `selected_candidate_ordinal INTEGER NULL`, `search_scope_payload JSONB`, `search_scope_hash ID`, `canonical_payload JSONB`, `canonical_payload_hash ID` | PK dependency; FK assessment; UQ `(assessment_id,dependency_kind,subject_key)`; UQ `(assessment_id,dependency_ordinal)`; UQ `(assessment_dependency_id,dependency_kind)`; ordinal `0..15`; outcome selected/absent/ambiguous with exact count/selected-ordinal shape; JSON objects | `(assessment_id,dependency_ordinal)`, `(dependency_kind,outcome,assessment_dependency_id)` |
| `market_data_quality_dependency_candidates` | PK fields `assessment_dependency_id ID`, `candidate_ordinal INTEGER`; `dependency_kind NAME`, `candidate_content_hash ID`, `candidate_payload JSONB`; nullable typed groups: `market_event_id ID`, `market_result_id ID`, `market_raw_event_id ID`, `provider_mapping_record_id ID`, `provider_mapping_id ID`, `instrument_version_record_id ID`, `instrument_version_id ID`, `catalogue_record_id ID`, `catalogue_version_id ID`, `catalogue_ingestion_run_id ID`, `catalogue_membership_id ID`, `catalogue_membership_receipt_id ID`, `trading_session_record_id ID`, `trading_session_version_id ID`, `lifecycle_event_id ID`, `lifecycle_kind VARCHAR(32)`, `lifecycle_batch_id ID`, `instrument_keys_digest ID` | PK dependency/ordinal; composite FK dependency/kind; candidate ordinal `0..4999`; UQ `(assessment_dependency_id,candidate_content_hash)`; exact composite FKs to existing target/result/raw, mapping record/semantic, version record/semantic, catalogue record/semantic, session record/semantic, lifecycle event/kind/batch membership; direct FKs to ingestion, membership, receipt, set; `data15_dependency_candidate_kind_shape` requires exactly one permitted typed group | `(assessment_dependency_id,candidate_ordinal)` plus one index beginning with every nullable typed FK root |
| `market_data_quality_run_assessments` | `assessment_run_id ID`, `target_ordinal INTEGER`, `event_id ID`, `assessment_id ID` all NOT NULL | PK run/ordinal; UQ run/event; UQ run/assessment; FKs run, event, composite assessment/event; ordinal `0..4999` | `(assessment_id,assessment_run_id)`, `(event_id,assessment_run_id)` |

### 19.3 Receipt tables

Each receipt table stores its target primary key, `receipt_at TIMESTAMPTZ NOT NULL`, `receipt_basis VARCHAR(32) NOT NULL`, `bootstrap_revision VARCHAR(32) NULL`, and `canonical_payload_hash ID NOT NULL`. Checks enforce `receipt_basis IN ('legacy_bootstrap','repository_insert')`, the bootstrap/null pairing, and finite time. The four temporal receipt tables have a direct PK/FK on `record_id`; the catalogue-membership receipt table has PK/FK `membership_id` plus `ingestion_run_id ID NOT NULL` FK. Each has index `(receipt_at,<target-id>)`.

### 19.4 Exact append-only and aggregate object names

```text
data15_reject_row_mutation()
data15_reject_truncate()
data15_validate_policy_reason_registry()
data15_validate_assessment_aggregate()
data15_validate_dependency_aggregate()
data15_validate_run_membership()
data15_validate_provider_mapping_receipt()
data15_validate_instrument_version_receipt()
data15_validate_catalogue_version_receipt()
data15_validate_trading_session_receipt()
data15_validate_catalogue_membership_receipt()
```

Every DATA-1.5 table receives `data15_<table>_immutable` and `data15_<table>_truncate` triggers. Receipt-completeness triggers are `DEFERRABLE INITIALLY DEFERRED` on the five existing parent tables. Exact names are asserted by migration tests and schema-drift verification.

---

## 20. Exact dependency query shapes

The SQL below is normative in predicates and ordering. Implementations may express it with SQLAlchemy Core, but may not add a latest fallback or omit a cutoff. Temporal graph queries deliberately load the complete knowledge-visible scope graph before market-validity filtering, because filtering predecessors before graph validation would create false corruption.

### 20.1 Temporal graph candidates

Provider mapping template; instrument, catalogue, and session use the same structure with their exact scope columns and receipt tables:

```sql
SELECT r.*, m.*, q.receipt_at, q.receipt_basis
FROM provider_mapping_records AS r
JOIN provider_contract_mappings AS m ON m.mapping_id = r.mapping_id
JOIN market_data_quality_provider_mapping_receipts AS q ON q.record_id = r.record_id
WHERE m.provider = :provider
  AND m.provider_contract_key = :provider_contract_key
  AND r.recorded_at <= :known_as_of
  AND q.receipt_at <= :known_as_of
ORDER BY r.recorded_at ASC, r.record_id ASC;
```

Domain phase: reconstruct the full visible successor graph; reject missing predecessor/branch/cycle as corruption; then retain semantic values satisfying `effective_from <= T < effective_until/open-end` (or `valid_from/valid_until`); remove eligible predecessors superseded by eligible descendants; zero leaves is missing/not-effective according to whether any graph row exists; one leaf is selected; more than one different leaf is ambiguity. IDs order evidence only.

Session scope is first resolved through `trading_sessions(exchange='NSE', session_date=:date_from_T, session_kind='regular')`; its complete version-record graph is then loaded with the session receipt table and the same K predicates.

### 20.2 Knowledge-visible target

```sql
SELECT o.*, s.*, mre.event_ordinal, r.*, f.*
FROM market_observations AS o
JOIN market_normalization_result_events AS mre
  ON mre.event_id=o.event_id AND mre.raw_event_id=o.raw_event_id
JOIN market_normalization_results AS r
  ON r.result_id=mre.result_id AND r.raw_event_id=mre.raw_event_id
JOIN raw_market_frames AS f ON f.raw_event_id=o.raw_event_id
LEFT JOIN <exact quote/status subtype> AS s ON s.event_id=o.event_id
WHERE o.event_id = ANY(:ordered_event_ids)
  AND o.available_at <= :known_as_of
  AND r.persistence_recorded_at <= :known_as_of
ORDER BY o.event_id ASC;
```

The repository verifies exactly one membership and exactly one required subtype for each returned event. Schema/provider compatibility is evaluated later as a quality rule.

### 20.3 Segment status

```sql
SELECT o.*, s.*, r.result_id, r.persistence_recorded_at, mre.event_ordinal
FROM market_observations o
JOIN market_segment_status_observations s ON s.event_id=o.event_id
JOIN market_normalization_result_events mre ON mre.event_id=o.event_id
JOIN market_normalization_results r ON r.result_id=mre.result_id
WHERE o.provider='upstox' AND s.segment=:segment
  AND o.provider_timestamp <= :T
  AND o.available_at <= :K
  AND r.persistence_recorded_at <= :K
ORDER BY o.provider_timestamp DESC, o.source_order DESC,
         o.source_order_scope_id ASC, o.event_id ASC;
```

Domain ranking applies the requirements' equal-rank duplicate/ambiguity rule; event ID never chooses between different state payloads.

### 20.4 Connection and subscription lifecycle

```sql
SELECT lo.*, subtype.*, b.lifecycle_batch_id, b.persistence_recorded_at,
       bo.event_ordinal
FROM provider_lifecycle_observations lo
JOIN provider_lifecycle_batch_observations bo
  ON bo.event_id=lo.event_id AND bo.lifecycle_kind=lo.lifecycle_kind
JOIN provider_lifecycle_batches b
  ON b.lifecycle_batch_id=bo.lifecycle_batch_id AND b.lifecycle_kind=bo.lifecycle_kind
JOIN <connection-or-subscription-subtype> subtype ON subtype.event_id=lo.event_id
WHERE lo.provider='upstox'
  AND lo.connection_session_id=:connection_session_id
  AND lo.occurred_at <= :T
  AND lo.available_at <= :K
  AND b.persistence_recorded_at <= :K
ORDER BY lo.occurred_at DESC, lo.source_order DESC,
         lo.source_order_scope_id ASC, lo.event_id ASC;
```

Subscription query does not filter state, set membership, or request mode. Domain code first reconstructs every visible `subscription_scope_id`, then applies internal ambiguity, active-containing cardinality, mode, membership, and lease rules in that order.

### 20.5 Catalogue membership/profile

```sql
SELECT cm.*, ro.ingestion_run_id, ir.profile_version,
       mr.receipt_at, mr.receipt_basis
FROM catalogue_memberships cm
JOIN catalogue_row_outcomes ro ON ro.row_outcome_id=cm.row_outcome_id
JOIN catalogue_ingestion_runs ir ON ir.ingestion_run_id=ro.ingestion_run_id
JOIN market_data_quality_catalogue_membership_receipts mr
  ON mr.membership_id=cm.membership_id
 AND mr.ingestion_run_id=ir.ingestion_run_id
WHERE cm.catalogue_version_id=:catalogue_version_id
  AND cm.provider_contract_key=:provider_contract_key
  AND mr.receipt_at <= :K
ORDER BY cm.membership_id ASC;
```

The selected row must match target mapping/version/instrument IDs and profile `upstox-nse-nifty-index-derivatives-v1`. Zero yields `unsupported_subject_scope`; more than one different row is durable corruption.

---

## 21. Exhaustive rule-contract and boundary proof

The 69-row registry in §6 is the exhaustive code list. Each registry row is paired with one of the exact trigger families below; the policy parser rejects a reason whose ordinal, severity, applicability, permitted subject keys, or evidence profile differs. Test generation iterates all 69 definitions and requires one positive, one adjacent non-firing, applicability, evidence-schema, ordinal, and severity assertion per definition.

| Rule family / codes | Exact firing and suppression rule | Adjacent vectors |
|---|---|---|
| Provider/schema/scope: 10–12 | provider != `upstox`; schema !=1 or normalizer label mismatch; profile/subject/segment outside allowlist | exact supported tuple does not fire; change one component fires only its code |
| Future/freshness: 2,3,13–15 | future iff timestamp>M; otherwise age warning when `warn<=age<error`, error when `age>=error`; error suppresses warning; future suppresses both | each threshold minus 1 microsecond, exact threshold, plus 1 microsecond; M+1 microsecond future |
| Availability: 1,16 | `received` clean; `historical_import` warning; any other basis/clock shape error | exact two accepted forms and one invalid form |
| Components/orphans: 17–23 | exact required/optional tuple matrix in policy; orphan occurrence per orphan field | absent/zero/present pairs for every target kind |
| Numeric/zero: 24–29 | safely representable domain violation not covered by durable-corruption invariant; field-specific required zeros use codes 25–29 | -1/0/1 for quantities and prices; persisted invariant break aborts instead of reason |
| Pair/spread: 4,5,30,31 | bid>ask crossed; bid=ask locked; only bid<ask reaches dual-axis spread truth table; error dominates warning | one tick crossed, locked, warning/error thresholds minus epsilon/exact/plus epsilon |
| Tick: 32–33 | missing/nonpositive tick dependency error; each present bid/ask/last emits off-tick iff `price % tick_size != 0` | tick 0.05 with 100.05 clean and 100.03 off tick |
| Resolution/provenance: 34–47 | cutoff containment first; full graph missing/ineffective/ambiguous; selected semantic+record IDs must equal persisted provenance; active status required | exact match clean; change one ID/cutoff/state fires corresponding code |
| Segment: 48–49 | prefix before first `|`; required mapping underlying→NSE_INDEX, future/option→NSE_FO, status exact allowlist | no delimiter/uncontrolled prefix; correct and swapped segment |
| Session: 50–54 | complete graph zero/multiple; timezone; status scheduled; `open_at<=T<close_at` | open-1µs, exact open, close-1µs, exact close |
| Segment status: 3,15,55–58 | quote dependency ranking at T/K; target self-evaluates; missing/ambiguous before state; unknown before not-open; age independently applies when singular | no row; equal-rank conflict; UNKNOWN; each known non-open; NORMAL_OPEN |
| Connection: 59–62 | ranked state; missing/ambiguous before authorization; singular nonauthorized; authorized lease age `>43200000` stale | lease exact accepted, +1µs stale; later event excluded |
| Subscription: 63–69 | reconstruct per scope without eligibility filtering; internal ambiguity; active-containing count; then state/membership/mode/lease in frozen order | zero scopes, inactive containing, no containing, one mode mismatch, exact lease, two active containing |
| Completeness: 6–9 | each nonempty path family warning; depth warning iff provider depth > normalized depth; inconsistent count/path is corruption | empty/nonempty set and equal/greater depth |

`invalid_numeric_value` is expected to be unreachable from a valid DATA-1.4 PostgreSQL row for fields already protected by DATA-1.4 checks. Its positive unit fixture uses a safely reconstructed domain DTO; a durable row violating an existing check/hash/type invariant is corruption, not a quality reason.

---

## 22. Design completion statement

This design is complete enough for mechanical implementation: package layout, identities, parser, registry, algorithms, SQL selection semantics, tables, constraints, FKs, triggers, migration order, locking, retries, compatibility, tests, and scope are frozen. It remains unauthorized until the separate design review approves this exact document hash.
