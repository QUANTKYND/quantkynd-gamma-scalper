# DATA-1.5 — Versioned Market-Data Quality Policy

## Amended Pre-Implementation Requirements

**Status:** Requirements approved as the input to pre-implementation design after adversarial review, amendments, follow-up re-review, and final consistency verification. Requirements alone do not authorize implementation; authorization is governed by the approved design gate.

**Repository:** `QUANTKYND/quantkynd-gamma-scalper`

**Verified starting branch:** `master`

**Verified starting SHA:** `b461d507d08546d72d952f80016b2617e216d711`

**Initial requirements/design documentation commit:** `bc17d77b9ff5e34a85bfd19bbbb8ba1834f3c89b`

**Current Alembic head:** `20260804_04`

**Feature branch:** `feature/data15-versioned-market-data-quality-policy`

**Proposed next Alembic revision:** `20260804_05`

---

## 1. Workflow position and authorization boundary

DATA-1.5 follows the repository milestone sequence:

```text
requirements draft
    ↓
independent adversarial requirements review
    ↓
requirements amendment / resolution matrix
    ↓
independent requirements re-review
    ↓
pre-implementation design response
    ↓
independent design approval
    ↓
implementation checkpoint
    ↓
implementation completion
    ↓
acceptance evidence
    ↓
independent implementation review
    ↓
merge
```

The requirements draft, first adversarial review, and follow-up re-review are complete. This document incorporates the accepted resolutions for findings `ADR-001` through `ADR-023` and follow-up findings `RR-001` through `RR-004`.

The requirements re-review and final consistency verification are complete. The next permitted phase is the pre-implementation design response and its separate adversarial approval. No application code, configuration artifact, migration, test, dependency, API wiring, or runtime integration is authorized by this requirements document alone.

## 2. Verified baseline

The repository inspection established the following baseline:

| Item | Verified state |
|---|---|
| `master` at DATA-1.5 branch creation | `b461d507d08546d72d952f80016b2617e216d711` |
| DATA-1.4 implementation | `725e708d1ea2a89514d90bbf3008bd9e234ccd5f` |
| DATA-1.4 evidence | `137db9416bc93d7f008464a134e7430a83e9d5ea` |
| DATA-1.4 migration | `20260804_04` |
| DATA-1.4 status | Accepted and merged |
| DATA-1.4 downgrade-hardening commit | `a6c3b0755eecbe4191befb5ed7abab19b1871464` |
| DATA-1.4 downgrade-hardening merge | `b461d507d08546d72d952f80016b2617e216d711` |
| Earlier acceptance-wording cleanup | `eaa243172a759f545c09bdff19fdacfbaad77e37` |
| DATA-1.5 feature branch | `feature/data15-versioned-market-data-quality-policy` |
| Initial DATA-1.5 documentation commit | `bc17d77b9ff5e34a85bfd19bbbb8ba1834f3c89b` |

The DATA-1.5 branch was created from exact `master` SHA `b461d507d08546d72d952f80016b2617e216d711`. That baseline already contains independently completed DATA-1.4 downgrade hardening. DATA-1.5 neither implements nor claims that work.

### 2.1 Existing source anchors that DATA-1.5 must preserve

- `backend/app/market_data/point_in_time.py` already contains provisional `QuoteQualityDisposition`, `PointInTimeQuery`, and `DataQualityAssessment` types. They are not an accepted DATA-1.5 implementation and must not silently dictate the final schema.
- `backend/app/market_data/normalization/models.py` defines normalized quote and market-segment-status observations, including provider timestamps, availability clocks, request modes, feed unions, prices, sizes, depth metadata, and economic/provenance references.
- `backend/app/persistence/postgres/models.py` persists DATA-1.4 raw frames, normalization results, normalized observations, quote subtypes, status observations, and provider lifecycle data.
- `backend/app/persistence/postgres/repositories.py` provides immutable insert-or-compare behavior, deterministic collisions, temporal resolution, and DATA-1.4 persistence.
- `backend/app/persistence/postgres/unit_of_work.py` provides one repeatable-read transaction and a final, non-reusable unit of work.
- `backend/app/instruments/identity.py` defines economic identities, contract versions, trading status, tick size, and provider mappings with market-time and knowledge-time validity.
- `backend/app/instruments/sessions.py` defines Asia/Kolkata trading-session identities and versions.
- `backend/app/instruments/ports.py` exposes temporal catalogue, mapping, version, and trading-session repositories.
- `backend/alembic/versions/20260804_04_append_only_market_events.py` is the migration predecessor.
- `backend/app/persistence/postgres/verification.py` and the existing restore verifier are the durable snapshot and dump/restore extension points.

DATA-1.5 must extend these boundaries narrowly rather than create a parallel persistence or time model.

---

## 3. Goal

DATA-1.5 must define and persist a deterministic, immutable, versioned market-data quality policy that evaluates DATA-1.4 observations and produces reproducible eligibility decisions for later point-in-time state reconstruction and analytics.

The required dependency flow is:

```text
persisted DATA-1.4 observation
        ↓
explicit immutable quality-policy version
        ↓
explicit market-as-of and known-as-of evaluation context
        ↓
deterministic dependency selection and rule evaluation
        ↓
eligible / warning / ineligible
        ↓
controlled ordered reason codes and exact provenance
```

The output must answer all of the following without discretionary interpretation:

1. Which exact observation was assessed?
2. Which exact policy version and evaluator semantics were used?
3. Which market and knowledge cutoffs governed the assessment?
4. Which exact instrument, mapping, catalogue, session, status, connection, and subscription records were used or found absent?
5. Which controlled rules fired, in what stable order, and with what severity?
6. Is the observation eligible for later use under that exact policy/context?
7. Can the complete result be regenerated byte-for-byte from durable inputs?

---

## 4. In scope

DATA-1.5 must cover:

- quality-policy semantic identity;
- immutable policy versions and canonical hashes;
- strict policy-document parsing and canonicalization;
- explicit evaluator schema and implementation identity;
- market-time and known-as-of evaluation semantics;
- quote freshness and strict future-timestamp ineligibility;
- required and optional quote components by instrument kind;
- zero bid/ask and zero size handling;
- crossed and locked markets;
- invalid, negative, or non-finite values;
- absolute tick-spread and relative basis-point spread constraints;
- tick-size alignment;
- provider segment consistency;
- connection lifecycle status;
- subscription lifecycle status, request mode, and instrument membership;
- stale lifecycle/subscription evidence;
- trading-session eligibility;
- market-segment status eligibility;
- instrument-version, provider-mapping, and catalogue provenance;
- deterministic reason codes, severity, disposition, and ordering;
- exact retry, idempotency, concurrency, and collision behavior;
- append-only reassessment for a new policy version or evaluation context;
- persistence schema and migration design;
- point-in-time assessment querying;
- no-future-leakage tests;
- PostgreSQL 17 migration, concurrency, durability, and restore verification;
- acceptance evidence and independent review requirements.

---

## 5. Explicitly out of scope

DATA-1.5 must not implement or modify:

- option-chain reconstruction;
- latest-state materialization;
- implied volatility;
- volatility surfaces;
- expected edge;
- strategy decisions;
- trade persistence;
- Redis or live runtime wiring;
- broker, order, fill, or execution paths;
- retention or archival policy;
- frontend or public API integration;
- policy activation scheduling or an implicit “current policy” pointer;
- automatic reassessment workers;
- correction/supersession of DATA-1.4 market observations;
- runtime/migration PostgreSQL role separation;
- additional hardening of permissive `IF EXISTS` downgrade clauses.

The two deferred DATA-1.4 findings—database-role separation and additional `IF EXISTS` downgrade hardening—must remain separate work and must not be mixed into DATA-1.5 commits, tests, evidence, or acceptance claims.

---

## 6. Required terminology

### 6.1 Policy

A stable semantic policy family, such as the Upstox NSE normalized-observation quality policy. A policy is not executable without an explicit version.

### 6.2 Policy version

An immutable, fully specified rule set with exact thresholds, applicability, reason registry, severity mapping, disposition reduction, canonical serialization, and evaluator compatibility.

### 6.3 Evaluation context

The pair:

```text
evaluation_market_as_of
evaluation_known_as_of
```

Both are mandatory, finite, timezone-aware UTC instants.

### 6.4 Assessment

The immutable decision for one normalized observation under one exact policy version and one exact evaluation context.

### 6.5 Dependency closure

The complete, canonical set of durable records and explicit absence proofs that influenced an assessment.

### 6.6 Disposition

Exactly one of:

```text
eligible
warning
ineligible
```

`warning` remains eligible for downstream use but carries one or more warning reasons. `ineligible` must not be used by downstream reconstruction under the same policy/context.

### 6.7 Severity

Exactly one of:

```text
warning
error
```

Any error reason produces `ineligible`. If there are no errors but one or more warnings, the disposition is `warning`. No reasons produces `eligible`.

---

## 7. Quality-policy identity and immutability

### 7.1 Stable policy identity

The semantic policy family identity is deterministic:

```text
policy_id = stable_hash({
  "entity": "market_data_quality_policy",
  "policy_name": <controlled-name>,
  "provider": <provider>,
  "observation_domain": <controlled-domain>
})
```

For DATA-1.5 v1, the controlled values are frozen as:

```text
policy_name: upstox_nse_nifty_index_derivatives_quality
provider: upstox
observation_domain: normalized_market_observation
```

Descriptions, file names, timestamps, authors, comments, repository paths, source-artifact identities, and policy registration evidence do not enter `policy_id`.

The v1 subject allowlist is limited to normalized observations whose provenance resolves through catalogue profile `upstox-nse-nifty-index-derivatives-v1` and whose economic subject is one of:

- the single underlying NSE index root contained in that profile;
- a futures contract on that root;
- an option contract on that root;
- an NSE provider market-segment-status observation for `NSE_INDEX` or `NSE_FO`.

A well-formed observation outside this allowlist is ineligible with `unsupported_subject_scope`; it is not silently treated as another policy family.

### 7.2 Version identity

The immutable version identity must be deterministic and content-independent so conflicting content under the same semantic version collides:

```text
policy_version_id = stable_hash({
  "entity": "market_data_quality_policy_version",
  "policy_id": policy_id,
  "version": positive_integer
})
```

Version `1` is the only version permitted by DATA-1.5 acceptance. A later semantic change requires version `2` or higher and a separately reviewed migration/configuration change.

### 7.3 Canonical hash contract and policy hash

All DATA-1.5 deterministic identities and content hashes use the existing repository functions `app.core.hashing.canonical_json` and `app.core.hashing.stable_hash` without a milestone-local alternative.

The frozen v1 contract is:

1. `stable_hash(payload)` is SHA-256 over the UTF-8 bytes of `canonical_json(payload)` and is rendered as `sha256:<64 lowercase hex>`.
2. Mapping keys must be strings and are emitted by JSON `sort_keys=True`.
3. JSON uses `ensure_ascii=False` and separators `(",", ":")` with no insignificant whitespace.
4. List and tuple order is preserved. Set/frozenset members are normalized and sorted by their canonical JSON representation.
5. `None`, booleans, and strings remain JSON null/boolean/string values. DATA-1.5 controlled identifiers, codes, units, keys, and schema labels are ASCII; unrestricted Unicode is not allowed in identity-bearing controlled text.
6. Integers are serialized as canonical base-10 strings through `Decimal(value).normalize()`; booleans are never accepted as integers.
7. Finite `Decimal` values are serialized as canonical base-10 strings without exponent notation; all signed zero forms serialize as `"0"`.
8. Float values are forbidden in DATA-1.5 semantic projections and evidence. The repository helper's float support is not used by this milestone.
9. Aware datetimes are converted to UTC and serialized using Python `datetime.isoformat()`. Naive datetimes are rejected. Dates use ISO `YYYY-MM-DD`.
10. Every identity payload contains a controlled `entity` field. No implicit wall-clock, locale, timezone, host, process, random value, unordered iteration, or database-generated value enters canonical input.

Required frozen vectors:

| Canonical JSON | Expected hash |
|---|---|
| `{"entity":"market_data_quality_policy","observation_domain":"normalized_market_observation","policy_name":"upstox_nse_nifty_index_derivatives_quality","provider":"upstox"}` | `sha256:eb8daac12517a8e65f25e2a0aee14cda8eeb4a3b2308a80719f747bdcb333d01` |
| `{"entity":"market_data_quality_policy_version","policy_id":"sha256:0000000000000000000000000000000000000000000000000000000000000000","version":"1"}` | `sha256:85eafa1a1b1517e373c0784d2842d11b065cd8c0ae3502d1aeb1398e4bea929d` |
| `{"at":"2026-08-07T12:34:56.123456+00:00","entity":"canonical_hash_test","price":"100.05","text":"ASCII","values":[null,true,"0","-3"]}` | `sha256:dcadb9cc36527b1507f5edb90916e72ea9cf774d65fa29b07d76829b52e2b0f8` |

A policy version persists its exact canonical semantic projection and `policy_definition_hash`. The semantic projection includes every result-affecting field and excludes comments and presentation-only metadata. Unknown keys, duplicate keys, aliases, implicit coercion, environment substitution, YAML anchors, non-finite numbers, floats, ambiguous timestamps, and unrestricted identity-bearing Unicode fail closed.

### 7.4 Policy source and equivalent artifacts

The reviewed source location is:

```text
config/data_quality/upstox-nse-market-observation-quality-v1.yaml
```

Policy-version semantics and source bytes are separate immutable objects:

- `market_data_quality_policy_versions` owns the semantic projection, `policy_definition_hash`, schema version, evaluator label, and semantic version identity, plus a repository-owned non-semantic `registered_at` persistence timestamp;
- `market_data_quality_policy_source_artifacts` owns each exact source byte artifact, source SHA-256, byte count, media type, parser label, and FK to the policy version.

Registering different bytes that produce the same semantic projection and compatibility identity is an idempotent policy-version retry plus insertion-or-compare of a new source-artifact row. It is not a policy-version collision. Re-registering the same artifact is fully idempotent.

The same `policy_version_id` with a different semantic projection, policy hash, schema version, evaluator label, reason registry, applicability, or threshold is a typed collision. Source artifacts never select or mutate policy semantics.

### 7.5 Evaluator identity

The initial compatibility pair is frozen as:

```text
quality_policy_schema_version: 1
quality_evaluator_implementation_version: market-data-quality-evaluator-1
```

Each policy version binds exactly one policy schema version and exactly one evaluator implementation label. The same policy schema version may be used by different evaluator labels only across different policy versions. Any result-affecting evaluator change requires a new policy version and a new reviewed evaluator label; silent replacement under an existing policy version is prohibited.

## 8. Evaluation-time semantics

### 8.1 Mandatory cutoffs

Every assessment command must provide both:

- `evaluation_market_as_of`: the market-state cutoff being reconstructed;
- `evaluation_known_as_of`: the latest information the evaluator is allowed to know.

Neither may default to current wall-clock time, database time, process start time, observation persistence time, or the newest durable row.

### 8.2 Clock ordering and exchange-date bootstrap

The evaluator rejects the command if:

```text
evaluation_known_as_of < evaluation_market_as_of
```

All semantic and evidence timestamps are finite, timezone-aware UTC instants.

The exchange date is derived from `dependency_market_as_of`, defined in §8.3, using the policy-owned fixed timezone `Asia/Kolkata` before any trading-session lookup. The selected session version must then declare exactly `Asia/Kolkata`; any mismatch is ineligible with `trading_session_timezone_mismatch`. Session selection never determines the timezone used to discover its own identity.

### 8.3 Target knowledge visibility and market-time eligibility

Target loading, target durability visibility, and target market-time eligibility are distinct.

An explicitly requested event is knowledge-visible only when all are true:

1. its normalized event `available_at <= evaluation_known_as_of`;
2. the observation belongs to one exact committed normalization result;
3. its owning normalization result `persistence_recorded_at <= evaluation_known_as_of`;
4. its result/event membership is present and valid in that same committed atomic DATA-1.4 persistence transaction.

Normalization schema and implementation compatibility are not target-visibility conditions. After the target is knowledge-visible, the evaluator applies the provider/schema/implementation checks in §12.1. A visible target with an unsupported normalization schema or implementation produces error `unsupported_normalization_schema` and an `ineligible` assessment; it must not be converted into `target_not_visible`.

The normalized event's semantic `recorded_at` is provenance evidence only. It is not the authoritative repository-persistence or knowledge-time boundary. DATA-1.5 must not invent or assume a per-observation `persistence_recorded_at` column. If the design introduces one, it must be repository-owned, immutable, and reconciled with the owning result's atomic persistence boundary.

The command performs a cutoff-limited lookup. If no knowledge-visible target is found, it returns non-persisting outcome `target_not_visible`. That outcome does not distinguish nonexistent data from data hidden after the knowledge cutoff. No assessment, run, reason, dependency, or membership row is written.

After a target is knowledge-visible, market-time eligibility is evaluated as a rule rather than used to hide the target:

```text
future_offset = provider_timestamp - evaluation_market_as_of
```

- `future_offset <= 0`: normal freshness evaluation;
- `future_offset > 0`: emit error `provider_timestamp_in_future`; disposition is `ineligible`; no stale or freshness-warning reason is additionally emitted.

DATA-1.5 v1 has no clean or warning tolerance for a target timestamp after `evaluation_market_as_of`.

For every market-time dependency selection, define:

```text
dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)
```

`dependency_market_as_of` must be used for:

- provider-mapping resolution;
- instrument-version resolution;
- catalogue resolution;
- exchange-date derivation;
- trading-session identity and eligibility;
- market-segment-status selection;
- connection lifecycle selection;
- subscription lifecycle selection;
- lifecycle and dependency-age calculations.

The original `provider_timestamp` remains unchanged and is retained for target identity, future-offset evidence, target freshness evidence, and audit reconstruction. A dependency whose market or occurrence timestamp is after `dependency_market_as_of` is never selectable for the assessment.

### 8.4 Market-time basis for v1

DATA-1.3/DATA-1.4 do not carry a defensible exchange timestamp for quote observations. Therefore DATA-1.5 v1 must explicitly use persisted `provider_timestamp` as the market-time basis and record:

```text
market_time_basis: provider_timestamp_v1
```

No synthetic exchange timestamp may be invented.

### 8.5 Policy selection

The caller must name the exact `policy_version_id`. DATA-1.5 must not implement “latest policy,” “active policy,” effective-date selection, or policy fallback.

### 8.6 Policy knowledge and counterfactual use

An explicitly requested immutable policy version is a counterfactual evaluation input, not a market observation. Registration after `evaluation_known_as_of` is allowed and does not alter the assessment identity or disposition.

Each assessment persists non-semantic audit fact:

```text
policy_registered_after_known_as_of = policy_version.registered_at > evaluation_known_as_of
```

The exact registration timestamp and this derived boolean are returned by audit reconstruction so consumers cannot mistake counterfactual evaluation for historically available policy truth. They do not enter policy identity, assessment identity, reason ordering, or eligibility.

## 9. Deterministic input closure

An assessment must use one repeatable-read transaction and must bind an exact dependency closure before evaluation.

For a quote observation, the closure must include or explicitly prove absence of:

- target market observation row;
- target quote subtype row;
- normalization result and event membership;
- raw frame identity and connection session;
- exact persisted provider mapping semantic row and temporal record;
- exact persisted instrument version semantic row and temporal record;
- exact persisted catalogue version semantic row and temporal record;
- point-in-time re-resolved provider mapping at `dependency_market_as_of` and evaluation knowledge time;
- point-in-time re-resolved instrument version at `dependency_market_as_of` and evaluation knowledge time;
- point-in-time re-resolved catalogue version at `dependency_market_as_of` and evaluation knowledge time;
- trading-session identity, version, and temporal record for the derived exchange date;
- latest visible market-segment status at or before `dependency_market_as_of`;
- latest visible connection lifecycle state at or before `dependency_market_as_of`;
- latest visible matching subscription lifecycle state at or before `dependency_market_as_of`;
- immutable subscription instrument-set digest and ordered keys;
- all policy parameters and reason definitions applicable to the observation kind.

For a market-segment-status observation, quote-only dependencies are not applicable, but the result/raw/session/provider/lifecycle inputs and exact applicability decisions must still be represented.

### 9.1 Dependency-kind temporal axes and receipt boundaries

For all market/effective selectors in this section:

```text
T = dependency_market_as_of
K = evaluation_known_as_of
```

Every dependency is filtered by an exact market/effective axis and an exact non-backdatable knowledge/receipt axis. Inclusive lower bounds and exclusive upper bounds are mandatory.

| Dependency kind | Market/effective visibility at `T` | Knowledge visibility at `K` | Authoritative durable receipt boundary |
|---|---|---|---|
| Normalized target event | loaded explicitly; future offset is evaluated by §8.3 | `available_at <= K`, exact owning result, and exact committed membership | owning normalization result `persistence_recorded_at`; membership inherits the same atomic transaction |
| Normalization result and membership | exact result owning target | `persistence_recorded_at <= K` | result `persistence_recorded_at`; membership inherits the same transaction |
| Provider mapping temporal record | `effective_from <= T < effective_until` or open end | asserted temporal knowledge interval is visible at `K` and receipt fact `<= K` | typed DATA-1.5 receipt fact keyed to exact temporal `record_id` unless an accepted repository-owned persistence clock already exists |
| Instrument/contract version temporal record | `valid_from <= T < valid_until` or open end | asserted temporal knowledge interval is visible at `K` and receipt fact `<= K` | typed DATA-1.5 receipt fact keyed to exact temporal `record_id` unless an accepted repository-owned persistence clock already exists |
| Catalogue version temporal record | `effective_from <= T < effective_until` or open end | asserted temporal knowledge interval is visible at `K` and receipt fact `<= K` | typed DATA-1.5 receipt fact keyed to exact temporal `record_id` unless an accepted repository-owned persistence clock already exists |
| Trading-session version | session identity derived from policy timezone and exchange date at `T`; `open_at/close_at` are eligibility bounds | asserted temporal knowledge interval is visible at `K` and receipt fact `<= K` | typed DATA-1.5 receipt fact keyed to exact temporal `record_id` unless an accepted repository-owned persistence clock already exists |
| Segment-status observation | `provider_timestamp <= T` | `available_at <= K`, exact owning result, and owning result persistence `<= K` | owning normalization result `persistence_recorded_at` |
| Connection lifecycle observation | `occurred_at <= T` | semantic availability/knowledge conditions are visible at `K` and authoritative receipt `<= K` | accepted existing repository-owned persistence clock when present; otherwise typed DATA-1.5 receipt fact keyed to the exact lifecycle row |
| Subscription lifecycle observation | `occurred_at <= T` | semantic availability/knowledge conditions are visible at `K` and authoritative receipt `<= K` | accepted existing repository-owned persistence clock when present; otherwise typed DATA-1.5 receipt fact keyed to the exact lifecycle row |
| Subscription instrument set | selected scope's immutable set identity | set and owning lifecycle assertion are visible at `K`, with authoritative receipt `<= K` | accepted existing repository-owned persistence clock when present; otherwise typed DATA-1.5 receipt fact keyed to the exact set/lifecycle row |

The normalized observation's semantic `recorded_at` and caller-supplied temporal-record `recorded_at` values remain provenance and asserted bitemporal evidence. They must not substitute for an authoritative repository-owned receipt boundary.

For a dependency type that already has an accepted DATA-1.4 repository-owned `persistence_recorded_at` or equivalent immutable persistence boundary, that existing field remains authoritative and must not be duplicated.

For provider-mapping, instrument-version, catalogue-version, trading-session, lifecycle, or subscription-set rows that lack such a boundary, DATA-1.5 must create typed, append-only receipt facts with real FKs to the exact durable row. Unchecked generic `(kind, id)` references are prohibited.

For rows already present when migration `20260804_05` runs:

```text
legacy_receipt_at = migration bootstrap transaction timestamp
```

For rows inserted after the migration, the receipt fact must be created atomically with the durable row, the timestamp must be repository-owned, and caller-supplied or backdated receipt times are prohibited.

A dependency is selectable only when its asserted temporal visibility conditions and its authoritative receipt boundary are both visible by `K`.

Consequences of legacy bootstrap are frozen:

- legacy rows are selectable only when `K >= legacy_receipt_at`;
- DATA-1.5 does not claim defensible knowledge visibility for those legacy rows before `legacy_receipt_at`;
- legacy receipt times must not be backdated to caller-supplied semantic `recorded_at` values;
- adding a receipt fact must not change existing semantic identity or market-validity intervals;
- the bootstrap timestamp and affected typed row counts must be included in migration and acceptance evidence.

Reconstructing the same `assessment_id` with a different dependency closure, selected IDs, absence proofs, receipt facts, or canonical evidence is a typed assessment collision/durable-corruption failure and persists nothing.

### 9.2 Deterministic selection and equal-time conflicts

Temporal mapping, instrument-version, catalogue, and session selectors must return zero or one effective temporal state after applying §9.1. More than one different effective state is a controlled ambiguity reason; deterministic ID order may order evidence but may not choose a winner.

For segment-status and lifecycle observations:

1. select the greatest eligible semantic timestamp (`provider_timestamp` or `occurred_at`);
2. within one `source_order_scope_id`, select the greatest `source_order` at that timestamp;
3. exact duplicate semantic payloads across scopes are benign duplicates and are represented in evidence sorted by event ID;
4. different state payloads at the same effective rank across scopes are ambiguous;
5. `available_at` and the authoritative repository-owned persistence or receipt boundary are visibility filters, not state-precedence fields; semantic `recorded_at` is provenance only;
6. deterministic IDs are final evidence-order keys only and never resolve conflicting states.

Ambiguity produces the dependency-specific controlled reason and no arbitrary state is used to satisfy downstream eligibility.

### 9.3 Absence proofs

A missing dependency is not represented only by SQL `NULL`. The canonical dependency manifest must include:

- dependency kind;
- searched semantic scope;
- market cutoff;
- knowledge cutoff;
- deterministic selection rule version;
- explicit `absent` outcome.

This prevents a later row from being mistaken for an input that was available during the original assessment.

### 9.4 Closure hash

The evaluator must compute and persist a canonical `dependency_closure_hash`. It must change if any selected dependency ID, selected immutable content hash, absence proof, cutoff, selection rule, or applicable policy parameter changes.

---

## 10. Assessment and run identity

### 10.1 Assessment identity

The assessment semantic identity must be independent of batch/run packaging and independent of the result:

```text
assessment_id = stable_hash({
  "entity": "market_data_quality_assessment",
  "event_id": event_id,
  "policy_version_id": policy_version_id,
  "evaluation_market_as_of": evaluation_market_as_of,
  "evaluation_known_as_of": evaluation_known_as_of
})
```

Disposition, reasons, dependency hash, evaluator label, and persistence timestamps are immutable evidence excluded from identity. The same assessment identity with different evidence is a collision, not a new assessment.

### 10.2 Run identity

A run groups one or more assessments:

```text
assessment_run_id = stable_hash({
  "entity": "market_data_quality_assessment_run",
  "policy_version_id": policy_version_id,
  "evaluation_market_as_of": evaluation_market_as_of,
  "evaluation_known_as_of": evaluation_known_as_of,
  "ordered_target_event_ids": sorted_unique_event_ids,
  "quality_evaluator_implementation_version": implementation_label
})
```

The implementation may include an explicit run-schema version in the identity. It may not include wall-clock time, database-generated IDs, random UUIDs, process IDs, host names, or physical insert order.

### 10.3 Run membership

Assessment content and identity contain no `assessment_run_id` and no creation-run field. Run linkage exists only in append-only `market_data_quality_run_assessments` rows.

Run membership preserves canonical sorted target order using contiguous zero-based ordinals. The same immutable assessment may be referenced by multiple runs without duplication or mutation. A membership collision is evaluated independently from assessment equality.

### 10.4 Reassessment

A new policy version, market cutoff, or knowledge cutoff creates a new assessment identity. Earlier assessments remain immutable and queryable. DATA-1.5 must not update a prior disposition or overwrite prior reasons.

---

## 11. Evaluation behavior

### 11.1 Full evaluation

The evaluator must execute every applicable rule and collect all applicable reasons. It must not stop after the first warning or error.

### 11.2 Applicability

Each policy rule must declare:

- controlled rule identifier;
- applicable observation kinds;
- required dependencies;
- exact threshold/unit fields;
- reason code;
- severity;
- deterministic registry ordinal.

A non-applicable rule produces no reason. Missing data required to determine applicability must fail closed with a controlled error reason unless the policy explicitly declares the component optional.

### 11.3 Reason occurrence identity and ordering

A reason occurrence is uniquely identified within an assessment by:

```text
(reason_code, subject_key)
```

`subject_key` is a controlled ASCII value from the reason definition, such as `observation`, `bid_price`, `ask_price`, `last_price`, `bid_size`, `ask_size`, `bid_ask_spread`, `provider_mapping`, `trading_session`, or `subscription_scope`.

Reasons are unique and ordered by:

```text
(policy registry ordinal, reason code, subject_key)
```

Observed values, thresholds, units, dependency IDs, physical row order, and hash-map iteration are never ordering inputs. A reason definition freezes its permitted subject keys and evidence schema.

### 11.4 Disposition reduction

```text
any error reason                 → ineligible
no errors + one or more warnings → warning
no reasons                       → eligible
```

A policy definition that maps the same reason code to multiple severities or ordinals is invalid.

### 11.5 Corruption boundary

Market-quality defects become controlled reasons. Durable corruption aborts the entire assessment run and persists nothing.

Examples of run-aborting corruption include:

- deterministic ID does not match reconstructed identity;
- typed columns disagree with canonical payload;
- result membership is incomplete or non-contiguous;
- raw/result/event identity linkage is broken;
- a present temporal record points to another semantic identity;
- immutable content under one deterministic ID differs;
- persisted canonical hashes do not recompute.

Invalid numeric market values may become quality reasons only when the row can still be reconstructed safely and identity/provenance integrity remains intact.

---

## 12. Initial policy v1 rules

The following thresholds are the proposed frozen v1 baseline for adversarial review. They are research-quality gates, not strategy or execution rules. Any change before design approval must be recorded as a requirements amendment.

### 12.1 Supported provider and schema

```text
provider: upstox
normalization_schema_version: 1
normalizer_implementation_version: upstox-v3-normalizer-1
exchange_timezone: Asia/Kolkata
supported_session_kind: regular
```

A provider/schema/implementation mismatch is ineligible.

### 12.2 Freshness

For a knowledge-visible target quote:

```text
quote_age = evaluation_market_as_of - quote.provider_timestamp
```

For a market-segment-status target, its age is `evaluation_market_as_of - status.provider_timestamp`. When status is a dependency of another target, dependency age is `dependency_market_as_of - status.provider_timestamp`; a later status is never selectable.

Future timestamp behavior is governed by §8.3. Any negative target age emits `provider_timestamp_in_future`, makes the target ineligible, and suppresses stale and freshness-warning reasons. No clean or warning future-timestamp tolerance exists in v1.

Warning and ineligible thresholds are inclusive:

| Observation kind | Feed response | Warning at or above | Ineligible at or above |
|---|---:|---:|---:|
| underlying quote | live feed | 3,000 ms | 10,000 ms |
| futures quote | live feed | 2,000 ms | 5,000 ms |
| option quote | live feed | 2,000 ms | 5,000 ms |
| any quote | initial feed | 15,000 ms | 60,000 ms |
| market segment status | any | 60,000 ms | 300,000 ms |

At the error threshold only the error reason is emitted; the warning reason is not additionally emitted.

### 12.3 Availability basis

- `received` is clean.
- `historical_import` produces warning `historical_import_availability`.
- An unsupported or internally inconsistent availability basis is ineligible.

This warning does not make historical data unusable for research. A later consumer may separately require defensible live availability; DATA-1.5 must preserve the basis and warning rather than silently reclassify it.

### 12.4 Required quote components and tuple semantics

Bid and ask sides are tuples:

```text
bid_side = (bid_price, bid_size)
ask_side = (ask_price, ask_size)
last_trade = (last_price, last_size, last_trade_at)
```

A size or timestamp without its corresponding price is an orphan component and is ineligible with `orphan_quote_component` using the orphan field as `subject_key`.

#### Underlying index observation

- `last_price` is required, finite, strictly positive, and tick-aligned.
- `last_size` and `last_trade_at` are optional only when `last_price` is present; because `last_price` is required, either may independently be absent.
- Bid and ask prices are optional only as a pair: both absent is allowed; exactly one present produces `one_sided_quote`.
- When bid/ask prices are absent, bid/ask sizes must also be absent.
- When a side price is present, its size may be absent for the underlying index; if present it must be a positive integer.

#### Futures observation

Required and strictly positive:

- bid price and bid size;
- ask price and ask size.

`last_price` is optional. `last_size` and `last_trade_at` must be absent when `last_price` is absent; when `last_price` is present either may independently be absent but must be valid when present.

#### Option observation

Required and strictly positive:

- bid price and bid size;
- ask price and ask size.

`last_price` is optional. `last_size` and `last_trade_at` must be absent when `last_price` is absent; when `last_price` is present either may independently be absent but must be valid when present.

#### Market-segment-status observation

Quote component rules are not applicable.

### 12.5 Numeric validity

Every numeric value considered by the evaluator must be the declared type, finite where applicable, and inside the persisted domain bounds.

- Negative price: ineligible.
- Non-finite price: ineligible when safely representable; otherwise durable corruption.
- Negative or non-integral quantity: ineligible when safely representable; otherwise durable corruption.
- Zero required bid/ask: ineligible.
- Zero required bid/ask size: ineligible.
- Optional zero last price is ineligible if present; absence is allowed for derivatives.

### 12.6 Crossed and locked markets

When both bid and ask are present:

- `bid > ask`: error `market_crossed` → ineligible.
- `bid = ask`: warning `market_locked`.
- `bid < ask`: continue to spread evaluation.

A locked market must still pass positive-price, positive-size, provenance, session, lifecycle, and freshness checks.

### 12.7 Tick alignment

Every present executable price field—`bid_price`, `ask_price`, and `last_price`—must be an exact integer multiple of the selected instrument-version tick size using exact Decimal arithmetic. `previous_close_price` is provenance-only in DATA-1.5 v1 and is not an executable quote component; it must still be finite and non-negative under DATA-1.4 invariants but is not quality-gated for tick alignment.

Each off-tick field emits `price_not_tick_aligned` with that field as `subject_key`, permitting multiple deterministic occurrences such as `(price_not_tick_aligned, bid_price)` and `(price_not_tick_aligned, ask_price)`. No float conversion or tolerance is permitted.

### 12.8 Spread calculation and precedence

For an uncrossed two-sided quote:

```text
spread = ask - bid
mid = (ask + bid) / 2
spread_ticks = spread / tick_size
spread_bps = (spread / mid) * 10000
```

All calculations use exact Decimal values.

| Kind | Warning ticks | Error ticks | Warning bps | Error bps |
|---|---:|---:|---:|---:|
| underlying with book | 5 | 20 | 15 | 75 |
| future | 4 | 12 | 20 | 75 |
| option | 5 | 20 | 1,000 | 5,000 |

Each dimension is classified independently as `clean`, `warning`, or `error` using inclusive thresholds. Final behavior is frozen:

| Tick state | Bps state | Emitted spread reason |
|---|---|---|
| clean | clean | none |
| warning | clean/warning | `spread_warning` |
| clean | warning | `spread_warning` |
| error | any | `spread_limit_exceeded` |
| any | error | `spread_limit_exceeded` |

Exactly one spread reason may fire, with subject key `bid_ask_spread`. Its canonical evidence always contains both observed metrics and all four applicable thresholds, so a dominant error does not discard the other dimension.

A locked market receives `market_locked` and no spread reason. A crossed market receives `market_crossed` and no locked/spread reason.

### 12.9 Normalization completeness metadata

The following produce warnings but do not independently make the quote ineligible:

- unadopted schema paths present;
- present unadopted message paths present;
- secondary payload paths present;
- provider depth greater than normalized depth.

Counts and path sets must be carried as bounded evidence. An internal count/path inconsistency is durable corruption, not a warning.

---

## 13. Provenance rules

### 13.1 Persisted provenance completeness

Every quote assessment requires all of the following persisted DATA-1.4 provenance:

- economic subject ID;
- provider contract key;
- provider mapping ID and temporal record ID;
- instrument/contract version ID and temporal record ID;
- catalogue version ID and temporal record ID;
- normalization resolution market cutoff;
- normalization resolution knowledge cutoff.

Missing persisted provenance is ineligible unless it violates DATA-1.4 table/domain invariants, in which case the run aborts as corruption.

### 13.2 Cutoff containment

The normalization resolution cutoffs must satisfy:

```text
resolution_market_as_of <= dependency_market_as_of
resolution_known_as_of <= evaluation_known_as_of
```

A cutoff after the assessment context is ineligible and must never be hidden by re-resolution.

### 13.3 Re-resolution

At `(dependency_market_as_of, evaluation_known_as_of)`, the evaluator must independently resolve:

- provider mapping state;
- instrument version state;
- catalogue version state.

The selected semantic IDs and temporal record IDs must match the observation’s persisted provenance. Missing, ambiguous, ineffective, or mismatched states are ineligible with controlled reasons.

### 13.4 Instrument status

The selected instrument version must have `trading_status = active`. Suspended, expired, delisted, missing, or unsupported status is ineligible.

### 13.5 Provider segment and subject scope

The provider segment is the prefix before the first `|` in the validated provider contract key.

For v1:

| Subject | Required segment |
|---|---|
| allowlisted underlying NSE index | `NSE_INDEX` |
| allowlisted future | `NSE_FO` |
| allowlisted option | `NSE_FO` |
| status target | exact segment `NSE_INDEX` or `NSE_FO` |

An unparseable key produces `provider_segment_unresolvable`. A kind/segment mismatch produces `provider_segment_mismatch`. A well-formed subject outside the exact v1 allowlist produces `unsupported_subject_scope`.

## 14. Trading-session and market-status rules

### 14.1 Session identity

The evaluator derives the exchange date from `dependency_market_as_of` using policy timezone `Asia/Kolkata`, then resolves the exact `(exchange, session_date, regular)` trading-session identity as of `evaluation_known_as_of`.

The session repository must return the semantic version and temporal `record_id`. Zero visible versions produces `trading_session_missing`. More than one different visible version produces `trading_session_ambiguous`. The selected version must declare `Asia/Kolkata`; mismatch produces `trading_session_timezone_mismatch`.

### 14.2 Session eligibility

The selected session must:

- exist;
- be `scheduled`;
- use `Asia/Kolkata`;
- satisfy `open_at <= dependency_market_as_of < close_at`.

Pre-open, closing, post-close, cancelled, closed-calendar, absent, or ambiguous sessions are ineligible for policy v1.

### 14.3 Segment status selection

For a quote target, select the latest visible status for the exact provider segment using §9.1 and §9.2. The selected status must be known and equal `NORMAL_OPEN`.

- no status: `segment_status_missing`;
- conflicting equal-rank statuses: `segment_status_ambiguous`;
- unknown provider status: `segment_status_unknown`;
- known status other than `NORMAL_OPEN`: `segment_not_normal_open`.

For a market-segment-status target, the target is not selected again as its own dependency. Its own known/name value is evaluated by the same `segment_status_unknown` / `segment_not_normal_open` rules.

A later status event never validates or invalidates an earlier quote.

## 15. Connection and subscription lifecycle rules

Lifecycle eligibility is evaluated at `dependency_market_as_of`, not at the target’s possibly later `provider_timestamp` and not at a later wall-clock time.

### 15.1 Connection selection

Use the target raw frame's exact `connection_session_id`. Select visible connection lifecycle observations using §9.1 and §9.2.

- no visible state: `connection_state_missing`;
- conflicting equal-rank state payloads: `connection_state_ambiguous`;
- exactly one selected state other than `authorized`: `connection_not_authorized`;
- selected authorized assertion older than the §15.3 lease: `connection_state_stale`.

A conflicting state is never resolved by event ID. A later authorization, failure, reconnect, close, or other state cannot affect an earlier target.

### 15.2 Subscription scope, state, membership, and mode

Subscription evaluation is staged; eligibility filters never hide a reason.

1. Candidate logical scopes are all scopes with the same provider and connection session whose lifecycle history is visible at `(T, K)`.
2. One logical scope is identified by immutable `subscription_scope_id`. Instrument-set digest, request mode, and state changes are attributes/history of that scope, not scope identity.
3. For each scope, reconstruct the latest visible state using §9.2, its effective request mode, and its exact immutable instrument set.
4. Conflicting equal-rank state records inside one scope produce `subscription_state_ambiguous` and that scope cannot satisfy eligibility.
5. Let `active_containing` be scopes whose reconstructed state is `subscribed` or `mode_changed` and whose immutable set contains the target provider key.
6. If `active_containing` has more than one scope, emit `ambiguous_active_subscription`; no scope is chosen by recency, set size, mode, or ID.
7. If `active_containing` has exactly one scope, evaluate its effective mode and lease independently:
   - mode differs from quote mode → `subscription_mode_mismatch`;
   - assertion exceeds §15.3 lease → `subscription_state_stale`.
8. If `active_containing` is empty:
   - no visible candidate scope → `subscription_state_missing`;
   - one or more visible scopes contain the key but all are inactive → one `subscription_not_active` occurrence with all relevant scope IDs in sorted evidence;
   - visible scopes exist but none contains the key → `subscription_instrument_missing`.

A `mode_changed` state is active only when its reconstructed effective mode is present and equals the mode carried by that lifecycle record; the state label alone never proves the mode.

### 15.3 Lifecycle staleness

Selected connection and subscription assertions must occur on the same `Asia/Kolkata` exchange date derived from `dependency_market_as_of` and satisfy:

```text
dependency_market_as_of - assertion.occurred_at <= 43,200,000 ms
```

Exactly `43,200,000 ms` old is accepted. Greater than `43,200,000 ms` is stale and ineligible. This is a bounded evidence lease, not a provider-heartbeat requirement.

### 15.4 No future lifecycle leakage

A later authorized, subscribed, mode-changed, failed, unsubscribed, or closed event must not affect an earlier quote assessment.

---

## 16. Controlled reason registry

The policy version must own a complete ordered registry. Codes are lowercase snake case, ASCII, bounded to 128 bytes, unique, and never provider-supplied free text.

The proposed v1 registry is below. The final policy document must assign a stable ordinal to every code.

### 16.1 Warning reasons

| Code | Meaning |
|---|---|
| `historical_import_availability` | Observation availability is historical-import rather than received. |
| `quote_age_warning` | Quote age reached the warning threshold but not the error threshold. |
| `status_age_warning` | Segment-status age reached the warning threshold but not the error threshold. |
| `market_locked` | Bid equals ask. |
| `spread_warning` | Tick or basis-point spread reached a warning threshold. |
| `unadopted_schema_paths_present` | Normalizer reported unadopted schema paths. |
| `present_unadopted_message_paths` | Present provider message fields were deliberately unadopted. |
| `secondary_payload_paths_present` | Ignored secondary payload paths were present. |
| `depth_truncated` | Provider depth exceeded normalized depth retained by DATA-1.3. |

### 16.2 Error reasons

| Code | Meaning |
|---|---|
| `unsupported_provider` | Observation provider is unsupported. |
| `unsupported_normalization_schema` | Normalization schema/implementation is unsupported. |
| `unsupported_subject_scope` | Subject is outside the exact v1 catalogue/profile allowlist. |
| `provider_timestamp_in_future` | Target provider timestamp is later than `evaluation_market_as_of`. |
| `quote_stale` | Quote age reached the error threshold. |
| `status_stale` | Segment-status age reached the error threshold. |
| `availability_basis_invalid` | Availability basis or clock shape is unsupported. |
| `required_last_price_missing` | Required underlying last price is absent. |
| `bid_missing` | Required bid is absent. |
| `ask_missing` | Required ask is absent. |
| `bid_size_missing` | Required bid size is absent. |
| `ask_size_missing` | Required ask size is absent. |
| `one_sided_quote` | Exactly one bid/ask price is present where pair semantics apply. |
| `orphan_quote_component` | Size/timestamp exists without its corresponding price. |
| `invalid_numeric_value` | Safely decoded numeric value violates its domain. |
| `bid_zero` | Required bid is zero. |
| `ask_zero` | Required ask is zero. |
| `bid_size_zero` | Required bid size is zero. |
| `ask_size_zero` | Required ask size is zero. |
| `last_price_zero` | Present or required last price is zero. |
| `market_crossed` | Bid exceeds ask. |
| `spread_limit_exceeded` | Tick or basis-point spread reached an error threshold. |
| `tick_size_missing_or_invalid` | Tick size is absent, non-positive, or unusable. |
| `price_not_tick_aligned` | A controlled price field is off tick. |
| `resolution_cutoff_after_evaluation` | Persisted resolution used information beyond assessment context. |
| `instrument_version_missing` | Point-in-time instrument version cannot be resolved. |
| `instrument_version_ambiguous` | Multiple different versions are effective at the same context. |
| `instrument_version_mismatch` | Re-resolved version differs from persisted provenance. |
| `instrument_version_not_effective` | Persisted/resolved version is not effective. |
| `instrument_trading_status_not_active` | Trading status is not active. |
| `provider_mapping_missing` | Point-in-time provider mapping cannot be resolved. |
| `provider_mapping_ambiguous` | Multiple different mappings are effective at the same context. |
| `provider_mapping_mismatch` | Re-resolved mapping differs from persisted provenance. |
| `provider_mapping_not_effective` | Persisted/resolved mapping is not effective. |
| `catalogue_provenance_missing` | Point-in-time catalogue state cannot be resolved. |
| `catalogue_provenance_ambiguous` | Multiple different catalogue states are effective. |
| `catalogue_provenance_mismatch` | Re-resolved catalogue differs from persisted provenance. |
| `catalogue_provenance_not_effective` | Catalogue state is not effective at the target context. |
| `provider_segment_unresolvable` | Provider key does not yield a controlled segment. |
| `provider_segment_mismatch` | Segment conflicts with the subject kind/profile. |
| `trading_session_missing` | Required session state cannot be resolved. |
| `trading_session_ambiguous` | Multiple different session versions are visible. |
| `trading_session_timezone_mismatch` | Session timezone is not `Asia/Kolkata`. |
| `trading_session_not_scheduled` | Session is not scheduled. |
| `outside_regular_session` | Target timestamp is outside `[open_at, close_at)`. |
| `segment_status_missing` | No visible segment status exists. |
| `segment_status_ambiguous` | Conflicting equal-rank status states exist. |
| `segment_status_unknown` | Latest visible status is unknown. |
| `segment_not_normal_open` | Latest visible known status is not `NORMAL_OPEN`. |
| `connection_state_missing` | No visible connection state exists. |
| `connection_state_ambiguous` | Conflicting equal-rank connection states exist. |
| `connection_not_authorized` | Selected connection state is not authorized. |
| `connection_state_stale` | Connection assertion exceeds the lifecycle lease. |
| `subscription_state_missing` | No visible subscription scope exists. |
| `subscription_state_ambiguous` | Conflicting equal-rank state exists within a scope. |
| `subscription_not_active` | Selected subscription is not active. |
| `subscription_mode_mismatch` | Effective mode differs from quote mode. |
| `subscription_instrument_missing` | Target key is absent from the immutable set. |
| `subscription_state_stale` | Subscription assertion exceeds the lifecycle lease. |
| `ambiguous_active_subscription` | Multiple active matching scopes remain. |

### 16.3 Canonical reason evidence

Each reason occurrence persists one canonical evidence object with schema version `1`:

```text
{
  "schema_version": 1,
  "subject_key": <controlled ASCII>,
  "observed": [<named typed value>, ...],
  "thresholds": [<named typed value>, ...],
  "dependency_ids": [<sha256 identifier>, ...],
  "details": [<named typed value>, ...]
}
```

A named typed value is:

```text
{
  "name": <controlled ASCII>,
  "type": "integer" | "decimal" | "timestamp" | "identifier" |
          "state" | "boolean" | "controlled_text",
  "value": <canonical string, except boolean>,
  "unit": "none" | "milliseconds" | "ticks" | "basis_points" |
          "price" | "quantity" | "count" | "state" | "identifier"
}
```

Rules:

- `observed`, `thresholds`, and `details` are sorted by `name`, unique by `name`, and each contains at most 16 entries;
- `dependency_ids` is sorted, unique, and contains at most 16 entries;
- integer values are base-10 strings; decimals use repository canonical Decimal text; timestamps use UTC repository canonical datetime text;
- null values are represented by absence of the named item, not a string sentinel;
- each reason definition freezes required/optional evidence names, value types, units, and permitted subject keys;
- evidence is included in assessment collision/read-back comparison but not reason ordering;
- secrets, tokens, account identifiers, URLs, tracebacks, raw socket errors, provider free text, and unbounded messages are forbidden.

Examples:

```json
{"schema_version":1,"subject_key":"bid_price","observed":[{"name":"price","type":"decimal","value":"100.03","unit":"price"},{"name":"remainder","type":"decimal","value":"0.03","unit":"price"}],"thresholds":[{"name":"tick_size","type":"decimal","value":"0.05","unit":"price"}],"dependency_ids":[],"details":[]}
```

```json
{"schema_version":1,"subject_key":"bid_ask_spread","observed":[{"name":"spread_bps","type":"decimal","value":"80","unit":"basis_points"},{"name":"spread_ticks","type":"decimal","value":"6","unit":"ticks"}],"thresholds":[{"name":"error_bps","type":"decimal","value":"75","unit":"basis_points"},{"name":"error_ticks","type":"decimal","value":"12","unit":"ticks"},{"name":"warning_bps","type":"decimal","value":"20","unit":"basis_points"},{"name":"warning_ticks","type":"decimal","value":"4","unit":"ticks"}],"dependency_ids":[],"details":[]}
```

## 17. Persistence requirements

### 17.1 Required logical tables

The append-only schema contains at least:

1. `market_data_quality_policies`
2. `market_data_quality_policy_versions`
3. `market_data_quality_policy_source_artifacts`
4. `market_data_quality_policy_reason_definitions`
5. `market_data_quality_assessment_runs`
6. `market_data_quality_assessments`
7. `market_data_quality_assessment_reasons`
8. typed FK-bearing assessment dependency tables plus, if retained, one canonical dependency manifest table
9. typed FK-bearing dependency receipt tables for durable rows that lack an accepted repository-owned persistence boundary
10. `market_data_quality_run_assessments`

The design may split dependency types further. It may not weaken integrity through an unchecked polymorphic `(kind, id)` reference.

### 17.2 Required assessment evidence

An assessment durably binds:

- `assessment_id`;
- `event_id`, `raw_event_id`, and normalization `result_id`;
- `policy_id` and `policy_version_id`;
- policy/evaluator schema and implementation labels;
- evaluation market and knowledge cutoffs;
- market-time basis;
- disposition;
- ordered reason count and reason-set hash;
- dependency closure hash;
- exact selected singleton dependency IDs and record IDs where present;
- canonical dependency manifest including absence proofs;
- assessment canonical payload hash;
- non-semantic `policy_registered_after_known_as_of` audit fact;
- finite persistence-recorded timestamp as non-semantic evidence.

An assessment contains no run ID. Run/assessment linkage exists exclusively in `market_data_quality_run_assessments`.

Every present event/result/raw/policy/temporal dependency has a real FK to its exact semantic and temporal row. Generic JSON alone is insufficient.

### 17.3 Append-only enforcement

Every DATA-1.5 table must reject:

- `UPDATE`;
- `DELETE`;
- `TRUNCATE`.

The migration must own a DATA-1.5-specific rejection function and triggers. It must not modify DATA-1.4 trigger ownership or deferred downgrade clauses.

### 17.4 Database-generated identity

Sequences, identity columns, random UUIDs, `gen_random_uuid`, server-generated semantic timestamps, and database-default semantic IDs are prohibited.

### 17.5 Canonical constraints

The database must repeat critical bounds:

- canonical `sha256:<64 lowercase hex>` IDs/hashes;
- positive version numbers;
- supported enums;
- finite timestamps;
- finite numeric evidence;
- bounded UTF-8/control-safe reason codes and identifiers;
- contiguous bounded ordinals;
- count reconciliation;
- policy schema/evaluator label compatibility;
- disposition/severity reduction shape;
- exact target identity uniqueness.

Application validation and read reconstruction must repeat these checks.

### 17.6 Visibility boundary

A run and its assessments, reasons, dependencies, and memberships are one atomic transaction. Partial assessment visibility is prohibited.

---

## 18. Migration requirements

The proposed migration is:

```text
backend/alembic/versions/20260804_05_versioned_market_data_quality_policy.py
```

with:

```text
revision = "20260804_05"
down_revision = "20260804_04"
```

The design response must freeze:

- the single repository-owned migration bootstrap timestamp used as `legacy_receipt_at`;
- the exact typed legacy rows receiving bootstrap receipt facts and deterministic row-count evidence;
- atomic post-migration creation of receipt facts for newly inserted dependency rows;
- exact table creation order;
- exact FK/unique/check/index names;
- append-only function and trigger names;
- deferred aggregate-validation strategy;
- durable-model registration order;
- downgrade dependency order;
- non-empty-table downgrade refusal;
- exact schema drift checks.

The downgrade must refuse destructive removal when any DATA-1.5 table contains rows and must report the exact non-empty table names in deterministic order.

DATA-1.5 must not edit DATA-1.4’s existing permissive `IF EXISTS` statements as part of this migration.

---

## 19. Retry, idempotency, collision, and concurrency

### 19.1 Exact retry

Re-running the same policy registration or assessment command with identical semantic content succeeds idempotently.

For policy registration:

- same semantic policy version plus same source bytes: policy and artifact both return `inserted = false`;
- same semantic policy version plus different semantically equivalent source bytes: policy returns `inserted = false`; the new source artifact is inserted-or-compared independently;
- same policy-version identity plus different semantic content or compatibility identity: collision.

For assessments, semantic equality includes the exact dependency closure, ordered reasons with subject keys/evidence, disposition, and canonical payload. Non-semantic persistence timestamps and run packaging do not affect equality.

### 19.2 Collision

The same deterministic identity with different immutable content must raise a typed collision error. It must never:

- overwrite the existing row;
- add a second row under a random ID;
- merge reason sets;
- select one result by insertion order;
- downgrade the conflict to a warning.

Required typed conflicts include at least:

- policy identity conflict;
- policy-version content conflict;
- reason-registry conflict;
- assessment identity conflict;
- dependency-closure conflict;
- assessment-run identity conflict;
- run-membership conflict.

### 19.3 Locking

Use a DATA-1.5-specific advisory-lock namespace and a bounded deterministic stripe count. Lock roots must include policy/version identities, assessment identities, and run identities. Stripes must be deduplicated and acquired in sorted order before writes.

The exact namespace and stripe count must be frozen by the design response and tested against accidental reuse of DATA-1.2/DATA-1.4 namespaces.

### 19.4 Bulk I/O

The implementation must use deterministic bounded parameter chunks. One awaited SQL round-trip per reason or dependency is not acceptable for production paths.

### 19.5 Transaction behavior

- One final transaction per policy registration or assessment run.
- Prevalidation before opening the transaction where possible.
- Repeatable-read snapshot.
- No network or wall-clock dependency during evaluation.
- Any error rolls back the entire run.
- Unit-of-work instances remain final and non-reusable.

### 19.6 Concurrency cases

Acceptance must prove:

- concurrent identical policy registration is idempotent;
- concurrent conflicting policy registration yields one durable winner and typed conflict;
- concurrent identical assessment run yields one exact durable result;
- concurrent same assessment in different run packaging reuses the immutable assessment safely;
- overlapping assessment sets do not deadlock;
- conflicting evidence under one assessment ID fails deterministically;
- rollback leaves no orphan reasons, dependencies, or memberships.

---

## 20. Point-in-time query contract

DATA-1.5 must expose repository/domain queries for assessments without implementing option-chain reconstruction.

### 20.1 Exact assessment lookup and invisible targets

Required durable lookup key:

```text
(event_id, policy_version_id, evaluation_market_as_of, evaluation_known_as_of)
```

It returns exactly one assessment or none; multiple matches are durable corruption.

The evaluation command first performs the cutoff-limited target lookup defined in §8.3. `target_not_visible` is a non-persisting command outcome and does not become an assessment or quality reason. An audit-only API may reveal whether an event exists outside the cutoff, but it must be separately named, separately authorized, and unusable as an eligibility selector.

### 20.2 No implicit latest selection

Downstream eligibility must never silently choose:

- latest policy version;
- latest assessment by persistence time;
- newest known-as-of context;
- nearest market cutoff;
- any assessment from another evaluator schema.

Missing exact assessment means `unevaluated`, not eligible.

### 20.3 Audit listing

A separately named audit query may list assessments in deterministic order. It must not be reusable as an eligibility selector without the caller supplying the exact policy/context.

### 20.4 Compatibility with provisional point-in-time code

The design response must explicitly address the existing provisional quality types in `backend/app/market_data/point_in_time.py`.

Permitted outcomes are:

- replace them with imports/adapters to the accepted DATA-1.5 contracts after design approval; or
- retain a compatibility wrapper whose semantics are exactly equivalent.

DATA-1.5 must not extend or activate `reconstruct_option_chain`, latest-state materialization, or downstream chain selection.

---

## 21. No-future-leakage requirements

Acceptance tests must demonstrate that an assessment at `(M, K)` is unchanged by adding any record whose relevant knowledge boundary is after `K` or whose relevant market/occurrence time is after `dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)`.

The matrix must include at least:

1. future quote;
2. future normalization result persistence;
3. future market-segment status;
4. future connection authorization/failure/close;
5. future subscription activation/mode change/unsubscribe/failure;
6. future trading-session correction;
7. future provider-mapping correction;
8. future instrument-version correction;
9. future catalogue correction;
10. future policy version;
11. later reassessment of the same event;
12. same market cutoff with two knowledge cutoffs;
13. same knowledge cutoff with two market cutoffs;
14. historical-import availability with and without a defensibility requirement in a consumer fixture;
15. equal timestamps requiring deterministic ID/source-order tie-breaks.

Tests must prove both result stability and dependency-closure stability.

---

## 22. Test requirements

### 22.1 Domain and canonicalization tests

- policy ID/version ID vectors;
- policy semantic hash vectors;
- source formatting permutation;
- duplicate/unknown key rejection;
- threshold/unit validation;
- assessment/run ID vectors;
- reason ordering and uniqueness;
- disposition reduction;
- Decimal spread/tick boundary vectors;
- freshness boundary vectors;
- provider-segment mapping;
- lifecycle lease boundaries;
- deterministic dependency manifest and hash.

### 22.2 Rule matrix tests

Each reason code must have:

- one positive firing test;
- one adjacent non-firing boundary test;
- applicability tests by observation kind;
- stable observed/threshold/unit evidence;
- stable ordinal/severity.

### 22.3 Repository tests

- exact policy registration retry;
- content collision;
- full assessment reconstruction;
- present and absent dependency manifests;
- real FKs for all present dependencies;
- no orphan rows;
- append-only update/delete/truncate rejection;
- read-after-write canonical recomputation;
- explicit exact assessment lookup;
- audit ordering.

### 22.4 PostgreSQL 17 tests

Acceptance-critical tests must run against the repository’s PostgreSQL 17 container with zero skips. They must cover:

- upgrade from `20260804_04` to `20260804_05`;
- schema object names and drift;
- downgrade of an empty DATA-1.5 schema;
- refusal to downgrade non-empty DATA-1.5 tables;
- upgrade/downgrade/upgrade cycle;
- append-only triggers;
- deferred aggregate checks;
- concurrency and deadlock timeout behavior;
- exact dump/restore equivalence.

### 22.5 Full regression

Run the complete backend test suite and all focused DATA-1.0 through DATA-1.4 suites. DATA-1.5 must not weaken existing normalization, persistence, migration, restore, or no-future-leakage behavior.

---

## 23. Durable verification and restore

DATA-1.5 tables must be added to the durable model registry and ordered durable snapshot.

The snapshot must include:

- deterministic row counts;
- canonical ordered row digests;
- policy semantic hashes;
- reason-registry hashes;
- assessment and run hashes;
- dependency closure hashes;
- membership/reason/dependency ordinal integrity.

PostgreSQL 17 `pg_dump` and `pg_restore` acceptance must show:

- identical schema revision;
- identical DATA-1.0 through DATA-1.5 durable counts;
- identical canonical digests;
- identical exact policy and assessment reconstruction;
- no skipped acceptance-critical checks.

Host PostgreSQL clients with a different major version must not be used as final acceptance evidence.

---

## 24. Acceptance evidence

The final evidence document must record at minimum:

- starting and ending SHAs;
- reviewed implementation SHA;
- migration revision and down revision;
- exact policy artifact path and hashes;
- policy/evaluator schema and implementation labels;
- complete controlled reason registry hash;
- focused test commands and pass counts;
- full backend test command and pass count;
- PostgreSQL server/client versions;
- migration upgrade/downgrade evidence;
- append-only mutation rejection evidence;
- concurrency/idempotency/collision evidence;
- no-future-leakage matrix results;
- dump/restore source and target digests;
- schema drift result;
- explicit statement that deferred database-role and DATA-1.4 downgrade hardening were not changed;
- explicit statement that no chain, IV, surface, strategy, Redis, broker, or execution path was introduced;
- known limitations and independent-review status.

Evidence created by the implementer does not itself accept DATA-1.5. Independent review is mandatory.

---

## 25. Independent review requirements

The reviewer must inspect code, migration, tests, and evidence rather than relying on summaries. Review must specifically challenge:

- semantic identity versus mutable evidence;
- policy-version collisions;
- hidden wall-clock/default-time use;
- future leakage through every dependency class;
- session timezone/date boundaries;
- zero, missing, locked, crossed, and spread boundaries;
- lifecycle selection and ambiguity;
- exact provenance and real foreign keys;
- absent-dependency reproducibility;
- reason ordering and disposition reduction;
- retry and concurrent collision behavior;
- partial transaction visibility;
- append-only enforcement including truncate;
- downgrade refusal;
- durable snapshot and restore equivalence;
- scope leakage into excluded milestones;
- accidental inclusion of the two deferred DATA-1.4 findings.

A blocker or high-severity correctness finding prevents acceptance. Medium/low findings must be either corrected or explicitly deferred with owner, rationale, and milestone.

---

## 26. Design-approval gate

The DATA-1.5 design may be approved only when the design response provides all of the following:

1. exact package/file layout;
2. exact domain contracts and deterministic identity material;
3. exact canonical policy schema and parsing rules;
4. exact evaluator algorithm and rule ordering;
5. exact dependency-selection queries and tie-breaks;
6. exact reason registry, severity, applicability, and evidence shape;
7. exact table/column/constraint/index/FK design;
8. exact handling of present and absent dependencies without polymorphic FK gaps;
9. exact migration and downgrade order;
10. exact unit-of-work and transaction boundary;
11. exact advisory-lock namespace, stripe count, and acquisition order;
12. exact retry/collision error taxonomy;
13. exact point-in-time query APIs;
14. exact compatibility plan for provisional point-in-time quality types;
15. exact PostgreSQL/concurrency/no-leakage/restore acceptance plan;
16. explicit proof that every out-of-scope item remains absent;
17. explicit proof that deferred role separation and DATA-1.4 downgrade hardening remain untouched;
18. adversarial review findings and resolution matrix.

No implementation checkpoint may begin while any item remains “to be decided during implementation.”

---

## 27. Target applicability matrix

The following matrix is result-affecting and frozen for v1:

| Dependency/rule family | Quote target | Segment-status target |
|---|---:|---:|
| Raw frame, normalization result, exact membership | Required | Required |
| Provider/schema/availability/freshness | Required | Required |
| Economic identity, provider mapping, instrument version, catalogue | Required | Not applicable |
| Tick size, quote components, locked/crossed/spread | Required as applicable | Not applicable |
| Trading-session identity/version and scheduled/open interval | Required | Required |
| Segment-status dependency | Required | Target evaluates its own status; no self-dependency |
| Connection lifecycle for raw frame's session | Required | Required |
| Subscription scope/set/mode | Required | Not applicable |
| Provider segment consistency | Derived from provider key | Exact target segment must be `NSE_INDEX` or `NSE_FO` |

A non-applicable dependency creates neither an absence proof nor a quality reason; applicability itself is included in the canonical policy projection.

---

## 28. Adversarial-review resolution matrix

The independent review is recorded in `docs/implementation/DATA-1.5-requirements-adversarial-review.md`. All findings are accepted and resolved as follows:

| Finding | Frozen resolution | Changed surface |
|---|---|---|
| ADR-001 | Separate knowledge visibility from market-time eligibility; any target timestamp after `evaluation_market_as_of` is ineligible, and dependencies use `dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)`. | Time semantics/tests |
| ADR-002 | Separate append-only source-artifact rows from semantic policy-version equality. | Schema/identity/retry |
| ADR-003 | Remove run ID from assessment; use many-to-many membership only. | Schema/identity |
| ADR-004 | Invisible/absent target returns indistinguishable non-persisting `target_not_visible`. | Command contract/security |
| ADR-005 | Freeze exact existing repository canonical JSON/SHA-256 contract and vectors. | All identities/hashes |
| ADR-006 | Add complete dependency ambiguity/effectiveness reason codes. | Reason registry/tests |
| ADR-007 | Freeze event `available_at`, owning result `persistence_recorded_at`, and atomic membership visibility; event semantic `recorded_at` is provenance only. | Knowledge clocks |
| ADR-008 | Add dependency-kind market/knowledge axis table. | Selectors/tests |
| ADR-009 | Require repository-owned non-backdatable receipt boundaries, including conservative migration bootstrap for legacy rows; changed closure under the same assessment ID is collision/corruption. | Persistence/selectors/migration |
| ADR-010 | Derive exchange date with policy-owned `Asia/Kolkata`, then validate session timezone. | Session semantics |
| ADR-011 | Stage subscription scope resolution, state reconstruction, membership, and mode checks. | Lifecycle rules |
| ADR-012 | Freeze `subscription_scope_id`; multiple active matching scopes are always ambiguous. | Lifecycle identity |
| ADR-013 | Freeze side/last-trade tuple and orphan-component behavior. | Quote rules/reasons |
| ADR-014 | Tick-align every present bid, ask, and last price. | Tick rule/tests |
| ADR-015 | Reason occurrence identity is `(reason_code, subject_key)`. | Schema/ordering/evidence |
| ADR-016 | Emit exactly one aggregate spread reason using a complete truth table and dual-metric evidence. | Spread rules/evidence |
| ADR-017 | Add exact quote/status target applicability matrix. | Applicability/closure |
| ADR-018 | Freeze per-kind equal-time selection; IDs order evidence but never choose conflicting states. | Selector ambiguity |
| ADR-019 | Allow counterfactual post-K policy registration and persist a non-semantic audit flag. | Audit evidence |
| ADR-020 | Bind one schema and evaluator label per policy version; schema may span labels only across versions. | Compatibility identity |
| ADR-021 | Limit v1 to the exact Nifty index-derivatives catalogue profile and two status segments. | Policy scope/reason |
| ADR-022 | Freeze canonical bounded typed reason-evidence union. | Evidence/schema/hash |
| ADR-023 | Replace stale pre-branch baseline wording with actual baseline and branch history. | Documentation |

No finding is deferred to implementation-time interpretation. These amendments supersede any earlier wording in this document that conflicts with §§7–28.

---

## 29. Independent requirements re-review findings and resolution matrix

The follow-up re-review identified four findings. All are accepted and incorporated into this canonical requirements document:

| Finding | Severity | Frozen resolution | Changed surface |
|---|---|---|---|
| RR-001 | Blocker | The non-suffixed requirements and review paths are the only canonical documents. Suffixed `-amended` copies must be removed from the branch. | Documentation identity |
| RR-002 | Blocker | No future-timestamp tolerance exists. Any `provider_timestamp > evaluation_market_as_of` is ineligible; every dependency selector uses `dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)`. | Time semantics/selectors/tests |
| RR-003 | Blocker | Target durability visibility uses event `available_at`, exact atomic result membership, and owning result `persistence_recorded_at`. Event semantic `recorded_at` is provenance only. | Knowledge clocks/query contract |
| RR-004 | High | Existing accepted repository persistence clocks remain authoritative; other dependency rows receive typed repository-owned receipt facts. Legacy rows use the migration bootstrap transaction timestamp and are not claimed visible before it. | Migration/persistence/selectors/evidence |

The amended requirements may proceed to design only after a final consistency verification confirms:

- every `ADR-001` through `ADR-023` and `RR-001` through `RR-004` resolution is reflected in normative wording;
- only the canonical non-suffixed requirements and review files remain;
- canonical vectors reproduce exactly with `app.core.hashing`;
- no reason branch remains unnamed;
- target invisibility cannot leak post-cutoff existence;
- future target timestamps cannot admit post-`evaluation_market_as_of` dependencies;
- assessment/run many-to-many semantics are internally consistent;
- target and dependency receipt clocks match repository temporal models;
- legacy bootstrap behavior is deterministic and conservatively bounded;
- no implementation, migration, configuration, or test code was introduced during requirements resolution.

A blocker or high-severity verification finding keeps design and implementation unauthorized.

---
## 30. Completion criterion

DATA-1.5 is complete only when an independently reviewed implementation can reproduce, from DATA-1.4 durable truth and one exact policy/context, the same immutable assessment, ordered reasons, disposition, and dependency closure across retries, process restarts, concurrent execution, migration cycles, and PostgreSQL dump/restore—without future leakage and without implementing any downstream chain, analytics, strategy, or execution behavior.

Until then, DATA-1 remains active.
