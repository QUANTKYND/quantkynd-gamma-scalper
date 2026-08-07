# DATA-1.5 — Pre-Implementation Design Gate

**Milestone:** Versioned market-data quality policy

**Status:** Design work may begin only after adversarial requirements review. Implementation is not authorized.

**Verified baseline branch:** `master`

**Verified baseline SHA:** `b461d507d08546d72d952f80016b2617e216d711`

**Initial DATA-1.5 documentation commit:** `bc17d77b9ff5e34a85bfd19bbbb8ba1834f3c89b`

**Feature branch:** `feature/data15-versioned-market-data-quality-policy`

**Requirements input:** `docs/implementation/DATA-1.5-versioned-market-data-quality-policy-requirements.md`

**Baseline note:** `b461d507d08546d72d952f80016b2617e216d711`
was the `master` HEAD from which DATA-1.5 design work began. It includes
independently completed and merged DATA-1.4 downgrade hardening. DATA-1.5
neither implements nor claims that work.

---

## 1. Purpose

This gate controls the transition from the DATA-1.5 requirements draft to an implementation-authorizing design.

It requires two separate review artifacts:

```text
requirements draft
    ↓
independent adversarial requirements review
    ↓
requirements amendment / resolution matrix
    ↓
pre-implementation design response
    ↓
independent design approval
```

No application code, migration, tests, configuration artifact, dependency, API, or runtime wiring may be written under this gate.

---

## 2. Required branch discipline

The design work must begin from exact accepted `master` SHA:

```text
eaa243172a759f545c09bdff19fdacfbaad77e37
```

Proposed branch:

```text
feature/data-1-5-versioned-market-data-quality-policy
```

Before any branch is created, verify that `docs/plan/acceptance-gates.md` no longer contains:

```text
This evidence does not accept DATA-1.4
```

That cleanup is already present in the verified baseline and must not be repeated as a new DATA-1.5 commit.

Only documentation files may change before design approval.

---

## 3. Required adversarial requirements review

Create:

```text
docs/implementation/DATA-1.5-requirements-adversarial-review.md
```

The reviewer must not rewrite the requirements silently. For each finding, record:

- finding ID;
- severity: blocker, high, medium, low, or question;
- exact requirements section;
- failure scenario;
- why current wording is insufficient or contradictory;
- required amendment or explicit decision;
- disposition: accepted, rejected, deferred, or clarified;
- owner and target milestone for any deferral.

### 3.1 Mandatory challenge areas

The review must attempt to break:

1. policy and version identity;
2. canonical policy hashing;
3. evaluator implementation compatibility;
4. assessment and run identity;
5. market-time versus knowledge-time semantics;
6. visibility through normalization-result persistence;
7. future leakage through mapping/version/catalogue corrections;
8. future leakage through session/status/lifecycle records;
9. exact dependency absence proofs;
10. quote-kind applicability;
11. missing, zero, invalid, locked, and crossed quote behavior;
12. tick alignment and Decimal boundary calculations;
13. spread threshold precedence;
14. lifecycle ambiguity and stale-state semantics;
15. session date/timezone boundaries;
16. reason uniqueness, order, severity, and disposition reduction;
17. exact retry versus semantic collision;
18. concurrent overlapping runs and lock ordering;
19. append-only enforcement and partial visibility;
20. real foreign-key coverage without unchecked polymorphic dependencies;
21. downgrade refusal and migration ownership;
22. dump/restore reproducibility;
23. compatibility with provisional quality types in `point_in_time.py`;
24. leakage into chain reconstruction or other excluded scope;
25. accidental inclusion of database-role separation or DATA-1.4 `IF EXISTS` hardening.

### 3.2 Required adversarial examples

At minimum, the reviewer must reason through these concrete cases:

- identical policy version ID with one threshold changed;
- YAML key reorder versus semantic threshold change;
- quote persisted after the assessment knowledge cutoff;
- quote timestamp one millisecond inside/outside every freshness boundary;
- bid/ask exactly equal;
- bid one tick above ask;
- spread exactly at warning/error thresholds;
- price exactly and almost tick-aligned;
- future mapping correction that rebinds the provider key;
- future session correction that changes open/close;
- authorized connection after quote time but not before it;
- two active matching subscription scopes;
- unsubscribe one source-order step after the quote;
- lifecycle assertion older than 12 hours;
- same assessment requested in two concurrent runs;
- same assessment ID reconstructed with different dependency closure;
- assessment run failing after reasons are inserted but before membership completion;
- downgrade with only a child table non-empty;
- dump/restore where row order differs physically.

A review that merely states “looks complete” does not pass this gate.

---

## 4. Requirements resolution

After adversarial review, update the requirements document only through explicit amendments. Add a resolution section or separate matrix containing:

- finding ID;
- accepted wording change or rejection rationale;
- resulting frozen decision;
- whether identity, schema, thresholds, tests, or scope changed.

Any result-affecting ambiguity must be resolved before the design response. “Decide during implementation” is not permitted.

---

## 5. Required pre-implementation design response

Create:

```text
docs/implementation/DATA-1.5-versioned-market-data-quality-policy-design.md
```

The design response must be repository-specific, source-anchored, and complete enough that implementation becomes mechanical rather than interpretive.

### 5.1 Status header

The document must begin with:

```text
Status: Proposed for independent design review; implementation is not authorized.
```

It must record:

- exact baseline and branch SHAs;
- worktree status at branch creation;
- current Alembic head;
- PostgreSQL server/client versions available for acceptance;
- files changed in the design phase;
- confirmation that no implementation/configuration/test/migration code changed.

### 5.2 Repository findings

Inspect and cite exact classes/functions/tables in:

- `backend/app/market_data/point_in_time.py`;
- `backend/app/market_data/normalization/models.py`;
- `backend/app/market_data/persistence/`;
- `backend/app/persistence/postgres/models.py`;
- `backend/app/persistence/postgres/repositories.py`;
- `backend/app/persistence/postgres/unit_of_work.py`;
- `backend/app/persistence/postgres/verification.py`;
- `backend/app/instruments/identity.py`;
- `backend/app/instruments/sessions.py`;
- `backend/app/instruments/ports.py`;
- migration `20260804_04`;
- existing database safety and restore verifier;
- focused DATA-1.0 through DATA-1.4 tests.

The response must identify every source/requirements mismatch. It must not pretend a required API, state wrapper, FK target, trigger, or test helper already exists.

### 5.3 Exact proposed package layout

Provide the exact file tree for:

- policy domain contracts;
- strict policy parser/canonicalizer;
- evaluator and rule registry;
- service/orchestration boundary;
- repository ports;
- PostgreSQL models/mappings/repositories;
- migration;
- CLI or offline verification entry point, if any;
- fixtures;
- tests;
- acceptance evidence.

State import-direction rules and prove provider SDK/Protobuf, SQLAlchemy, FastAPI, Redis, and broker types do not cross forbidden boundaries.

### 5.4 Identity tables

For every durable object, provide a table with:

- semantic purpose;
- deterministic primary key;
- exact included identity material;
- exact excluded evidence;
- collision behavior;
- retry behavior;
- foreign-key targets.

Include policy, policy version, reason definition, assessment run, assessment, reason row, dependency/absence proof, and run membership.

### 5.5 Canonical policy schema

Provide:

- complete schema tree;
- every required/optional field;
- exact types and units;
- bounds;
- unknown/duplicate-key behavior;
- canonical Decimal/time/string representation;
- semantic projection;
- source artifact hash calculation;
- semantic policy hash calculation;
- schema/evaluator compatibility matrix;
- at least three canonical hash test vectors.

The design must explain how comments and key order can change source bytes without changing policy semantics, while any threshold/reason/applicability change creates a semantic mismatch under the same version identity.

### 5.6 Evaluation algorithm

Provide numbered pseudocode from command validation through final reconstruction. It must freeze:

1. command and cutoff validation;
2. target ordering/deduplication;
3. transaction start;
4. policy registration/read integrity;
5. target observation visibility;
6. exact result/raw membership binding;
7. dependency resolution;
8. absence-proof creation;
9. rule applicability;
10. full rule evaluation;
11. reason sorting/deduplication;
12. disposition reduction;
13. identity/hash calculation;
14. advisory-lock acquisition;
15. bounded bulk insertion;
16. read-back reconstruction;
17. commit;
18. retry/collision response.

No wall-clock, unordered iteration, implicit latest selection, or network lookup may remain unspecified.

### 5.7 Dependency selection specification

For each dependency kind, provide:

- semantic scope;
- required market/occurrence cutoff;
- required knowledge cutoff;
- exact SQL/domain query;
- total ordering and tie-breaker;
- exact selected IDs/content hashes;
- absence-manifest shape;
- reason on absence/ambiguity;
- real FK strategy when present.

Cover mapping, instrument version, catalogue version, trading-session version/record, segment status, connection lifecycle, subscription lifecycle, and instrument-set membership.

The design must add or adapt a trading-session state API that returns the temporal record ID; a value-only session lookup does not pass.

### 5.8 Rule specification

For every rule and reason code, provide:

- rule ID;
- registry ordinal;
- applicable observation kinds;
- exact prerequisites;
- exact formula;
- boundary inclusion/exclusion;
- severity;
- evidence fields/units;
- adjacent test vectors.

Show exact Decimal examples for tick alignment and spread calculations. Show exact millisecond examples for freshness and lifecycle leases.

### 5.9 Persistence design

For every table, specify:

- exact name and purpose;
- all columns and PostgreSQL types;
- primary/unique/foreign keys;
- check constraints;
- indexes and intended queries;
- append-only triggers;
- aggregate/deferred validation;
- canonical payload/hash fields;
- read reconstruction checks;
- durable snapshot order.

Unchecked polymorphic dependency references do not pass. Every present dependency must have a real FK. If generic dependency rows are retained for canonical ordering, pair them with typed FK-bearing columns/tables and prove consistency.

### 5.10 Migration `20260804_05`

Freeze:

- exact filename;
- down revision;
- creation order;
- prerequisite unique constraints on existing tables, if any;
- trigger/function ownership;
- deferred validation functions;
- indexes;
- durable registry changes;
- downgrade order;
- deterministic non-empty refusal;
- schema drift verification.

Do not alter runtime/migration roles or DATA-1.4 `IF EXISTS` clauses.

### 5.11 Transaction and concurrency design

Provide:

- exact unit-of-work extension;
- transaction isolation and visibility root;
- DATA-1.5 advisory-lock namespace and stripe count;
- collision-proof namespace selection;
- root-to-stripe calculation test vectors;
- sorted lock acquisition order;
- parameter-budget chunk formulas;
- insert-or-compare/read-back strategy;
- rollback behavior;
- concurrent test orchestration and timeouts.

### 5.12 Query contracts

Specify exact domain/repository methods for:

- registering/getting an exact policy version;
- persisting an assessment run;
- exact assessment lookup by event/policy/context;
- deterministic audit listing;
- reconstructing full reasons and dependencies;
- verification snapshot reads.

No method may imply “latest eligible quote,” option-chain reconstruction, or current-state materialization.

### 5.13 Compatibility response

Explain exactly what happens to provisional `QuoteQualityDisposition`, `PointInTimeQuery`, `DataQualityAssessment`, and `_selected_assessment` code in `backend/app/market_data/point_in_time.py`.

The design must prevent two competing quality identities or disposition vocabularies. It must also prevent DATA-1.5 from activating the provisional option-chain reconstruction path.

### 5.14 Error taxonomy

List exact typed errors and their inheritance for:

- invalid policy document;
- unsupported policy schema/evaluator;
- policy/version/reason collisions;
- invalid evaluation command;
- unsupported observation kind;
- dependency ambiguity;
- assessment/run/dependency collision;
- referential integrity failure;
- durable corruption;
- concurrency/serialization failure.

Distinguish market-quality reasons from run-aborting errors.

### 5.15 Test and acceptance matrix

Map every requirement to:

- unit test;
- focused repository test;
- PostgreSQL test;
- concurrency test;
- no-future-leakage test;
- migration test;
- restore test;
- evidence item.

Name proposed test files and commands. Acceptance-critical PostgreSQL tests must have zero skips.

### 5.16 Scope proof

Include a changed-files allowlist and explicit absence proof for:

- option-chain reconstruction;
- latest-state materialization;
- IV and surfaces;
- edge and strategy;
- trade persistence;
- Redis/live wiring;
- broker/execution;
- database-role separation;
- DATA-1.4 `IF EXISTS` hardening.

---

## 6. Mandatory design self-review

Before submitting the design, the author must include a self-review matrix that attempts to invalidate it under:

- semantically identical policy source with different bytes;
- semantically different policy under same version;
- event/result/raw identity collision;
- future dependency insertion;
- equal-time ordering ambiguity;
- missing temporal record;
- two valid mapping branches;
- absent session/status/lifecycle;
- crossed/locked/zero/missing quote boundaries;
- Decimal exponent and tick remainder edge cases;
- stale snapshot and lifecycle boundaries;
- concurrent identical and conflicting runs;
- process crash before commit;
- dump/restore physical reorder;
- downgrade with partial data;
- hostile hash-seed/runtime locale/timezone.

For each case, name the exact design mechanism and test that prevents nondeterminism, leakage, or partial truth.

---

## 7. Independent design approval checklist

The reviewer may approve only when all answers are explicit and mutually consistent:

- [ ] Baseline and source anchors verified.
- [ ] Requirements review findings resolved.
- [ ] Policy and version identities exclude mutable evidence.
- [ ] Canonical policy hash includes every result-affecting field.
- [ ] Evaluator compatibility cannot change silently.
- [ ] Assessment identity is independent of result and run packaging.
- [ ] Both evaluation cutoffs are mandatory.
- [ ] Result persistence is part of knowledge visibility.
- [ ] Provider timestamp is the explicit v1 market-time basis.
- [ ] All dependency selectors are point-in-time and totally ordered.
- [ ] Future records cannot influence earlier assessments.
- [ ] Absence proofs are canonical and cutoff-bound.
- [ ] Every rule, threshold, boundary, reason, severity, and ordinal is frozen.
- [ ] Disposition reduction is deterministic.
- [ ] Durable corruption aborts rather than becoming a warning.
- [ ] Present dependencies have real foreign keys.
- [ ] No unchecked polymorphic dependency hole remains.
- [ ] Schema, triggers, aggregate validation, and downgrade are exact.
- [ ] Retry/collision/concurrency semantics are exact.
- [ ] Full run visibility is atomic.
- [ ] Exact lookup never falls back to latest policy/assessment.
- [ ] Provisional point-in-time quality code has one compatibility plan.
- [ ] No downstream chain/analytics/strategy/execution behavior is introduced.
- [ ] Deferred role and downgrade-hardening findings remain untouched.
- [ ] PostgreSQL 17 migration/concurrency/restore evidence is fully planned.
- [ ] No implementation decision is deferred to coding time.

A failed checkbox blocks design approval.

---

## 8. Stop condition

Stop after committing the requirements review, any explicit requirements amendment, and the proposed design response.

Do not create migration `20260804_05`, policy YAML, application modules, tests, database objects, CLI behavior, or runtime wiring until a separate independent review explicitly approves the design for implementation.
