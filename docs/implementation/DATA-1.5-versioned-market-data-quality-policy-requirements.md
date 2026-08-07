# DATA-1.5 — Versioned Market-Data Quality Policy

## Pre-Implementation Requirements Draft

**Status:** Requirements draft for adversarial review. Implementation is not authorized.

**Repository:** `QUANTKYND/quantkynd-gamma-scalper`

**Verified starting branch:** `master`

**Verified starting SHA:** `b461d507d08546d72d952f80016b2617e216d711`

**Initial requirements/design documentation commit:** `bc17d77b9ff5e34a85bfd19bbbb8ba1834f3c89b`

**Current Alembic head:** `20260804_04`

**Feature branch:** `feature/data15-versioned-market-data-quality-policy`

**Proposed next Alembic revision:** `20260804_05`

**Baseline note:** `b461d507d08546d72d952f80016b2617e216d711`
was the `master` HEAD from which DATA-1.5 design work began. It includes
independently completed and merged DATA-1.4 downgrade hardening. DATA-1.5
neither implements nor claims that work.

---

## 1. Workflow position and authorization boundary

DATA-1.5 follows the repository milestone sequence:

```text
requirements draft
    ↓
adversarial review
    ↓
pre-implementation design response
    ↓
design approval
    ↓
implementation checkpoint
    ↓
implementation completion
    ↓
acceptance evidence
    ↓
independent review
    ↓
merge
```

This document completes only the **requirements draft**. It does not authorize application code, migrations, tests, dependency changes, API wiring, or runtime integration.

The next permitted change is an independent adversarial review of these requirements. A design response may be drafted only after review findings are either incorporated or explicitly rejected with rationale. Implementation remains prohibited until the design response is independently approved.

---

## 2. Verified baseline

The repository inspection established the following baseline:

| Item | Verified state |
|---|---|
| `master` | `b461d507d08546d72d952f80016b2617e216d711` |
| DATA-1.4 implementation | `725e708d1ea2a89514d90bbf3008bd9e234ccd5f` |
| DATA-1.4 evidence | `137db9416bc93d7f008464a134e7430a83e9d5ea` |
| DATA-1.4 migration | `20260804_04` |
| DATA-1.4 status | Accepted and merged |
| Cleanup requested before branching | Already committed in `eaa243172a759f545c09bdff19fdacfbaad77e37` |
| Cleanup effect | Removed the stale sentence “This evidence does not accept DATA-1.4” from `docs/plan/acceptance-gates.md` |
| Existing DATA-1.5 branch | None found during inspection |

No additional cleanup commit is required before DATA-1.5 branching.

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
- quote freshness and future-timestamp tolerance;
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

The semantic policy family identity must be deterministic:

```text
policy_id = stable_hash({
  "entity": "market_data_quality_policy",
  "policy_name": <controlled-name>,
  "provider": <provider>,
  "observation_domain": <controlled-domain>
})
```

For DATA-1.5 v1, the controlled values are proposed as:

```text
policy_name: upstox_nse_market_observation_quality
provider: upstox
observation_domain: normalized_market_observation
```

Descriptions, file names, timestamps, authors, comments, and repository paths must not enter `policy_id`.

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

### 7.3 Canonical policy hash

A policy version must persist:

- exact canonical semantic projection;
- `policy_definition_hash` over that projection;
- policy schema version;
- canonical evaluator implementation label;
- exact source artifact byte hash;
- source artifact byte count.

The canonical semantic projection must include every result-affecting field and exclude comments and presentation-only metadata. Unknown keys, duplicate keys, aliases, implicit type coercion, environment substitution, anchors, non-finite numbers, and ambiguous timestamps must fail closed.

Equivalent source formatting—whitespace, comments, and mapping key order—may change the source artifact hash but must not change the canonical policy hash. Any semantic field change must change the canonical policy hash.

### 7.4 Policy source

The proposed reviewed source location is:

```text
config/data_quality/upstox-nse-market-observation-quality-v1.yaml
```

The eventual design response may propose another exact path, but it must preserve strict local, repository-owned, reviewable configuration with no network retrieval or runtime mutation.

### 7.5 Evaluator identity

The initial compatibility pair is proposed as:

```text
quality_policy_schema_version: 1
quality_evaluator_implementation_version: market-data-quality-evaluator-1
```

One policy schema version may have only one accepted evaluator implementation label. A result-affecting evaluator change requires a new policy version or evaluator schema, never silent replacement under the same accepted identity.

---

## 8. Evaluation-time semantics

### 8.1 Mandatory cutoffs

Every assessment command must provide both:

- `evaluation_market_as_of`: the market-state cutoff being reconstructed;
- `evaluation_known_as_of`: the latest information the evaluator is allowed to know.

Neither may default to current wall-clock time, database time, process start time, observation persistence time, or the newest durable row.

### 8.2 Clock ordering

The evaluator must reject the command if:

```text
evaluation_known_as_of < evaluation_market_as_of
```

All semantic and evidence timestamps must be finite and timezone-aware. UTC is the canonical internal representation. Exchange-date derivation must use `Asia/Kolkata` through the selected trading-session version.

### 8.3 Observation visibility

A normalized observation is visible to an assessment only when all are true:

1. `provider_timestamp <= evaluation_market_as_of`;
2. `available_at <= evaluation_known_as_of`;
3. its DATA-1.4 normalization result was durably recorded by `evaluation_known_as_of`;
4. its exact event membership belongs to the selected committed normalization result;
5. its normalization schema version is explicitly supported by the policy version.

DATA-1.5 must not substitute `persistence_recorded_at` for market time. It is only a knowledge/durability boundary.

### 8.4 Market-time basis for v1

DATA-1.3/DATA-1.4 do not carry a defensible exchange timestamp for quote observations. Therefore DATA-1.5 v1 must explicitly use persisted `provider_timestamp` as the market-time basis and record:

```text
market_time_basis: provider_timestamp_v1
```

No synthetic exchange timestamp may be invented.

### 8.5 Policy selection

The caller must name the exact `policy_version_id`. DATA-1.5 must not implement “latest policy,” “active policy,” effective-date selection, or policy fallback.

### 8.6 Policy knowledge

An explicitly requested immutable policy version is a counterfactual evaluation input, not a market observation. Its registration timestamp must not silently alter `evaluation_known_as_of`. The assessment must still record when the policy version was registered as evidence.

---

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
- point-in-time re-resolved provider mapping at observation market time and evaluation knowledge time;
- point-in-time re-resolved instrument version at observation market time and evaluation knowledge time;
- point-in-time re-resolved catalogue version at observation market time and evaluation knowledge time;
- trading-session identity, version, and temporal record for the derived exchange date;
- latest visible market-segment status at or before the observation market time;
- latest visible connection lifecycle state at or before the observation market time;
- latest visible matching subscription lifecycle state at or before the observation market time;
- immutable subscription instrument-set digest and ordered keys;
- all policy parameters and reason definitions applicable to the observation kind.

For a market-segment-status observation, quote-only dependencies are not applicable, but the result/raw/session/provider/lifecycle inputs and exact applicability decisions must still be represented.

### 9.1 Visibility of dependencies

A dependency is selectable only if its own market/occurrence timestamp is not later than the target observation market time and its availability/recording boundary is not later than `evaluation_known_as_of`.

Future lifecycle, status, session corrections, catalogue records, mapping records, or instrument records must never influence an earlier assessment.

### 9.2 Deterministic tie-breaking

Every latest-visible selection must define a total order using semantic time, provider/source ordering when present, knowledge time, and deterministic ID as final tie-breaker. Physical row order, insertion order, query-plan order, and Python set/dict iteration must not influence selection.

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

Run membership must preserve the canonical sorted target order using contiguous zero-based ordinals. The same immutable assessment may be referenced by multiple runs without duplication or mutation.

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

### 11.3 Reason ordering

Reasons must be unique and ordered by:

```text
(policy registry ordinal, reason code)
```

Observed values, threshold values, and units are evidence, not ordering inputs.

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

Quote freshness age is:

```text
quote_age = evaluation_market_as_of - quote.provider_timestamp
```

For a market-segment-status observation assessed as the target, its own age is `evaluation_market_as_of - status.provider_timestamp`. When status is a dependency of a quote, dependency age is instead `quote.provider_timestamp - status.provider_timestamp`; a status event after the quote is never selectable.

A target timestamp more than `1,000 ms` after `evaluation_market_as_of` is ineligible. An age between zero and the warning threshold is clean. Warning and ineligible thresholds are inclusive at the boundary shown below:

| Observation kind | Feed response | Warning at or above | Ineligible at or above |
|---|---:|---:|---:|
| underlying quote | live feed | 3,000 ms | 10,000 ms |
| futures quote | live feed | 2,000 ms | 5,000 ms |
| option quote | live feed | 2,000 ms | 5,000 ms |
| any quote | initial feed | 15,000 ms | 60,000 ms |
| market segment status | any | 60,000 ms | 300,000 ms |

A negative target age within the one-second tolerance is clamped to zero for freshness only and records no reason. It must not change visibility or market-time ordering. Status dependencies are never allowed to be later than the quote and therefore receive no future-tolerance clamp.

### 12.3 Availability basis

- `received` is clean.
- `historical_import` produces warning `historical_import_availability`.
- An unsupported or internally inconsistent availability basis is ineligible.

This warning does not make historical data unusable for research. A later consumer may separately require defensible live availability; DATA-1.5 must preserve the basis and warning rather than silently reclassify it.

### 12.4 Required quote components

#### Underlying index observation

- `last_price` is required, finite, and strictly positive.
- Bid and ask are optional only as a pair.
- Both absent is allowed.
- Exactly one present is ineligible.
- If both are present, both must be strictly positive and all book/spread/tick rules apply.
- If a size is present for a present side, it must be a positive integer. A zero size is ineligible.

#### Futures observation

Required and strictly positive:

- bid price;
- ask price;
- bid size;
- ask size.

Last price, last size, volume, and open interest are optional but must satisfy their numeric domain when present.

#### Option observation

Required and strictly positive:

- bid price;
- ask price;
- bid size;
- ask size.

Last price, last size, volume, and open interest are optional but must satisfy their numeric domain when present.

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

When bid or ask is present, each price must be an exact integer multiple of the selected instrument-version tick size using exact Decimal arithmetic. No float conversion or tolerance is permitted.

A non-aligned price is ineligible with `price_not_tick_aligned`.

### 12.8 Spread calculation

For an uncrossed two-sided quote:

```text
spread = ask - bid
mid = (ask + bid) / 2
spread_ticks = spread / tick_size
spread_bps = (spread / mid) * 10000
```

All calculations use exact Decimal values. Thresholds are evaluated ineligible-first, then warning. Meeting either the tick or basis-point threshold fires the corresponding severity.

| Kind | Warning ticks | Error ticks | Warning bps | Error bps |
|---|---:|---:|---:|---:|
| underlying with book | 5 | 20 | 15 | 75 |
| future | 4 | 12 | 20 | 75 |
| option | 5 | 20 | 1,000 | 5,000 |

A locked market has zero spread and receives only `market_locked`, not a spread warning.

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
resolution_market_as_of <= provider_timestamp
resolution_known_as_of <= evaluation_known_as_of
```

A cutoff after the assessment context is ineligible and must never be hidden by re-resolution.

### 13.3 Re-resolution

At `(provider_timestamp, evaluation_known_as_of)`, the evaluator must independently resolve:

- provider mapping state;
- instrument version state;
- catalogue version state.

The selected semantic IDs and temporal record IDs must match the observation’s persisted provenance. Missing, ambiguous, ineffective, or mismatched states are ineligible with controlled reasons.

### 13.4 Instrument status

The selected instrument version must have `trading_status = active`. Suspended, expired, delisted, missing, or unsupported status is ineligible.

### 13.5 Provider segment

The provider segment is the prefix before the first `|` in the validated provider contract key.

For the accepted v1 profile:

| Instrument kind | Required segment |
|---|---|
| Nifty underlying index | `NSE_INDEX` |
| future | `NSE_FO` |
| option | `NSE_FO` |

An unparseable key or kind/segment mismatch is ineligible.

---

## 14. Trading-session and market-status rules

### 14.1 Session identity

The evaluator must derive the exchange date from `provider_timestamp` using the selected session timezone, then resolve the exact `regular` trading-session version as of `evaluation_known_as_of`.

The session repository must expose an exact state including the temporal `record_id`; returning only the semantic value is insufficient provenance for DATA-1.5.

### 14.2 Session eligibility

The selected session must:

- exist;
- be `scheduled`;
- use `Asia/Kolkata`;
- satisfy `open_at <= provider_timestamp < close_at`.

Pre-open, closing, post-close, cancelled, closed-calendar, absent, or ambiguous sessions are ineligible for policy v1.

### 14.3 Segment status selection

Select the latest visible status for the exact provider segment with:

```text
status.provider_timestamp <= quote.provider_timestamp
status.available_at <= evaluation_known_as_of
status result persistence <= evaluation_known_as_of
```

The selected status must be known and equal `NORMAL_OPEN`. Missing, unknown, pre-open, normal-close, closing-start, or closing-end status is ineligible.

A future status event must not validate or invalidate an earlier quote.

---

## 15. Connection and subscription lifecycle rules

Lifecycle eligibility is evaluated at the quote’s `provider_timestamp`, not at a later wall-clock time.

### 15.1 Connection selection

Use the target raw frame’s exact `connection_session_id`. Select the latest visible normalized connection lifecycle event for that session satisfying:

```text
occurred_at <= quote.provider_timestamp
available_at <= evaluation_known_as_of
recorded_at <= evaluation_known_as_of
```

The state must be `authorized`.

Missing state, connecting, connected-but-not-authorized, reconnecting, closing, closed, or failed is ineligible.

### 15.2 Subscription selection

A matching subscription must have:

- the same provider and connection session;
- an immutable instrument set containing the target provider contract key;
- the same request mode as the quote;
- a latest visible state at or before the quote market time;
- state `subscribed` or `mode_changed`.

`subscribe_requested`, `mode_change_requested`, `unsubscribe_requested`, `unsubscribed`, or `subscription_failed` is ineligible.

No matching subscription is ineligible. More than one active matching subscription after deterministic scope resolution is ineligible as ambiguous rather than arbitrarily selected.

### 15.3 Lifecycle staleness

The selected connection and subscription assertions must:

- occur on the same Asia/Kolkata exchange date as the quote;
- be no more than `43,200,000 ms` (12 hours) older than the quote timestamp.

An older assertion is ineligible with a stale lifecycle reason. This is a bounded evidence lease, not a requirement for periodic provider heartbeats.

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
| `unsupported_provider` | Observation provider is not supported by the policy. |
| `unsupported_normalization_schema` | Normalization schema/implementation is not supported. |
| `provider_timestamp_in_future` | Timestamp exceeds the allowed future tolerance. |
| `quote_stale` | Quote age reached the ineligible threshold. |
| `status_stale` | Segment-status age reached the ineligible threshold. |
| `availability_basis_invalid` | Availability basis or clock shape is unsupported. |
| `required_last_price_missing` | Required underlying last price is absent. |
| `bid_missing` | Required bid is absent. |
| `ask_missing` | Required ask is absent. |
| `bid_size_missing` | Required bid size is absent. |
| `ask_size_missing` | Required ask size is absent. |
| `one_sided_quote` | Exactly one of bid or ask is present where pair semantics apply. |
| `invalid_numeric_value` | Safely decoded numeric value is non-finite, negative, non-integral, or outside the policy domain. |
| `bid_zero` | Required bid is zero. |
| `ask_zero` | Required ask is zero. |
| `bid_size_zero` | Required bid size is zero. |
| `ask_size_zero` | Required ask size is zero. |
| `last_price_zero` | Present or required last price is zero. |
| `market_crossed` | Bid exceeds ask. |
| `spread_limit_exceeded` | Tick or basis-point spread reached an error threshold. |
| `tick_size_missing_or_invalid` | Required tick size is absent, non-positive, or unusable. |
| `price_not_tick_aligned` | Bid or ask is not an exact tick multiple. |
| `resolution_cutoff_after_evaluation` | Persisted resolution used information beyond the assessment context. |
| `instrument_version_missing` | Point-in-time instrument version cannot be resolved. |
| `instrument_version_mismatch` | Re-resolved version differs from persisted provenance. |
| `instrument_version_not_effective` | Persisted/resolved version is not valid at the quote context. |
| `instrument_trading_status_not_active` | Instrument status is not active. |
| `provider_mapping_missing` | Point-in-time provider mapping cannot be resolved. |
| `provider_mapping_mismatch` | Re-resolved mapping differs from persisted provenance. |
| `provider_mapping_not_effective` | Persisted/resolved mapping is not effective at the quote context. |
| `catalogue_provenance_missing` | Point-in-time catalogue state cannot be resolved. |
| `catalogue_provenance_mismatch` | Re-resolved catalogue differs from persisted provenance. |
| `provider_segment_unresolvable` | Provider key does not yield a controlled segment. |
| `provider_segment_mismatch` | Segment is inconsistent with the instrument kind/profile. |
| `trading_session_missing` | Required trading-session state cannot be resolved. |
| `trading_session_not_scheduled` | Selected session is not scheduled. |
| `outside_regular_session` | Quote timestamp is outside `[open_at, close_at)`. |
| `segment_status_missing` | No visible segment status exists at quote time. |
| `segment_status_unknown` | Latest visible status is unknown. |
| `segment_not_normal_open` | Latest visible known status is not `NORMAL_OPEN`. |
| `connection_state_missing` | No visible connection lifecycle state exists. |
| `connection_not_authorized` | Selected connection state is not authorized. |
| `connection_state_stale` | Selected connection assertion exceeds the lifecycle lease. |
| `subscription_state_missing` | No matching visible subscription state exists. |
| `subscription_not_active` | Selected subscription is not subscribed/mode-changed. |
| `subscription_mode_mismatch` | Subscription request mode differs from quote request mode. |
| `subscription_instrument_missing` | Target provider key is absent from the immutable subscription set. |
| `subscription_state_stale` | Selected subscription assertion exceeds the lifecycle lease. |
| `ambiguous_active_subscription` | Multiple active matching subscription scopes remain. |

### 16.3 Reason evidence

Each fired reason must persist bounded, typed evidence sufficient to explain it without free-form text, including where applicable:

- observed value;
- threshold value;
- unit (`milliseconds`, `ticks`, `basis_points`, `state`, `count`, `identifier`);
- dependency ID;
- policy rule ID;
- reason ordinal.

Provider secrets, tokens, raw socket errors, tracebacks, URLs, account identifiers, and unbounded provider messages are forbidden.

---

## 17. Persistence requirements

### 17.1 Proposed tables

The design response must specify an append-only schema equivalent in integrity to the following logical tables:

1. `market_data_quality_policies`
2. `market_data_quality_policy_versions`
3. `market_data_quality_policy_reason_definitions`
4. `market_data_quality_assessment_runs`
5. `market_data_quality_assessments`
6. `market_data_quality_assessment_reasons`
7. `market_data_quality_assessment_dependencies`
8. `market_data_quality_run_assessments`

The design may split dependency types into additional typed tables. It must not weaken referential integrity through an unchecked polymorphic `(kind, id)` reference.

### 17.2 Required assessment evidence

An assessment must durably bind:

- `assessment_id`;
- `assessment_run_id` membership;
- `event_id`, `raw_event_id`, and normalization `result_id`;
- `policy_id` and `policy_version_id`;
- policy/evaluator schema and implementation labels;
- evaluation market and knowledge cutoffs;
- market-time basis;
- disposition;
- ordered reason count and reason-set hash;
- dependency closure hash;
- exact selected singleton dependency IDs and record IDs where present;
- canonical dependency manifest, including absence proofs;
- assessment canonical payload hash;
- finite persistence-recorded timestamp as non-semantic evidence.

Every present event/result/raw/policy/temporal dependency must have a real foreign key to the exact semantic and temporal row. Generic JSON alone is insufficient.

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

Re-running the same policy registration or assessment command with identical immutable content must succeed idempotently and return `inserted = false` or an equivalent explicit retry result.

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

### 20.1 Exact assessment lookup

Required lookup key:

```text
(event_id, policy_version_id, evaluation_market_as_of, evaluation_known_as_of)
```

The query returns exactly one assessment or none. Multiple matching rows are durable corruption.

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

Acceptance tests must demonstrate that an assessment at `(M, K)` is unchanged by adding any record whose relevant knowledge boundary is after `K` or whose relevant market/occurrence time is after the target observation time.

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

## 27. Completion criterion

DATA-1.5 is complete only when an independently reviewed implementation can reproduce, from DATA-1.4 durable truth and one exact policy/context, the same immutable assessment, ordered reasons, disposition, and dependency closure across retries, process restarts, concurrent execution, migration cycles, and PostgreSQL dump/restore—without future leakage and without implementing any downstream chain, analytics, strategy, or execution behavior.

Until then, DATA-1 remains active.
