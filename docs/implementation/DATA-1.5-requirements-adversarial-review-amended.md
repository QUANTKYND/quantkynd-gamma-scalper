# DATA-1.5 — Independent Adversarial Requirements Review

**Milestone:** Versioned market-data quality policy  
**Review status:** **COMPLETED — 23 findings recorded**  
**Resolution status:** **All 23 findings have accepted amendments in the amended requirements; independent requirements re-review is pending**
**Implementation status:** **Not authorized**  
**Reviewed branch:** `feature/data15-versioned-market-data-quality-policy`  
**Verified baseline:** `b461d507d08546d72d952f80016b2617e216d711`  
**Initial requirements/design documentation commit:** `bc17d77b9ff5e34a85bfd19bbbb8ba1834f3c89b`  
**Reviewed requirements:** `docs/implementation/DATA-1.5-versioned-market-data-quality-policy-requirements.md`  
**Review gate:** `docs/implementation/DATA-1.5-pre-implementation-design-gate.md`

---

## 1. Review method

This review attempts to invalidate the requirements before any implementation begins. It treats every result-affecting ambiguity as unsafe until the requirements freeze one deterministic answer.

The review specifically challenged:

- semantic identity versus evidence;
- canonical policy hashing and equivalent source documents;
- market-time versus knowledge-time visibility;
- hidden or future target observations;
- dependency selection and absence proofs;
- rule applicability and boundary behavior;
- reason uniqueness and evidence loss;
- assessment/run identity and many-to-many membership;
- session, status, connection, and subscription resolution;
- retry, collision, concurrency, append-only persistence, downgrade, and restore;
- compatibility with provisional point-in-time quality types;
- leakage into excluded DATA-1.6 or strategy behavior.

No application code, configuration artifact, migration, test, dependency, or runtime wiring was reviewed or authorized by this document.

---

## 2. Executive result

The requirements are strong in scope control, point-in-time intent, deterministic persistence, and acceptance rigor. They are **not yet implementation-ready** because several clauses are mutually contradictory or leave identity-affecting behavior undecided.

### Finding count

| Severity | Count |
|---|---:|
| Blocker | 6 |
| High | 11 |
| Medium | 5 |
| Low | 1 |
| **Total** | **23** |

All blocker and high findings are accepted for amendment. None is deferred. Implementation remains prohibited until the requirements document contains an explicit resolution matrix and the amended wording is independently re-reviewed.

---

## 3. Findings

## ADR-001 — Future-timestamp tolerance is unreachable

- **Severity:** Blocker
- **Requirements sections:** 8.3 Observation visibility; 12.2 Freshness
- **Failure scenario:** A quote has `provider_timestamp = evaluation_market_as_of + 500 ms`.
- **Why the wording fails:** Section 8.3 allows a target only when `provider_timestamp <= evaluation_market_as_of`. Section 12.2 says a negative age within 1,000 ms is clamped to zero and is clean. The visibility test rejects the row before the tolerance rule can run.
- **Required amendment:** Freeze one rule. Either:
  1. permit target visibility through `evaluation_market_as_of + 1,000 ms` and preserve the original timestamp for all ordering, while applying the clamp only to freshness; or
  2. remove the tolerance and require `provider_timestamp <= evaluation_market_as_of` everywhere.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-002 — Equivalent policy source bytes conflict with immutable version evidence

- **Severity:** Blocker
- **Requirements sections:** 7.2 Version identity; 7.3 Canonical policy hash; 19.1 Exact retry; 19.2 Collision
- **Failure scenario:** Policy YAML A and YAML B differ only in comments and key order. They produce the same semantic projection and `policy_definition_hash`, but different source byte hashes and byte counts.
- **Why the wording fails:** One immutable policy-version row is required to persist one source artifact hash and byte count. Exact retry requires identical immutable content, while semantic-equivalent formatting is explicitly allowed to change source evidence. The requirements do not say whether B is an idempotent retry, an evidence attachment, or a collision.
- **Required amendment:** Freeze one persistence model:
  - canonical reviewed source bytes are singular and any byte change collides; or
  - source artifacts are separate append-only evidence rows keyed by artifact hash, while policy-version equality is based only on semantic content and compatibility identity.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-003 — Assessment ownership contradicts reusable run membership

- **Severity:** Blocker
- **Requirements sections:** 10.3 Run membership; 17.2 Required assessment evidence
- **Failure scenario:** The same immutable assessment is referenced by two runs with different target batches.
- **Why the wording fails:** Section 10.3 correctly permits one assessment to be referenced by multiple runs. Section 17.2 says an assessment must durably bind `assessment_run_id`. A single-valued run ID inside the assessment makes many-to-many reuse impossible or causes the assessment payload to change between runs.
- **Required amendment:** Remove `assessment_run_id` from assessment identity/content. Persist run linkage only in append-only `market_data_quality_run_assessments` membership rows. If a non-semantic creation-run field is retained, state that it cannot determine equality, reconstruction, or eligibility.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-004 — Hidden target behavior is undefined and can leak future knowledge

- **Severity:** Blocker
- **Requirements sections:** 8.3 Observation visibility; 11.5 Corruption boundary; 20.1 Exact assessment lookup
- **Failure scenario:** The caller supplies a real `event_id`, but its observation or normalization result was recorded after `evaluation_known_as_of`.
- **Why the wording fails:** The evaluator cannot safely distinguish “does not exist” from “exists but is hidden after K” without querying beyond K. The requirements do not state whether the command returns not found, unevaluated, invalid command, ineligible, or a persisted assessment. Persisting an ineligible reason based on a hidden row would prove knowledge of the future.
- **Required amendment:** Define a non-persisting command outcome for a target not visible at `(M, K)`. The observable response must not distinguish absent from future-hidden unless the caller is explicitly using an audit API outside eligibility semantics.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-005 — `stable_hash` and canonical scalar encoding are not frozen

- **Severity:** Blocker
- **Requirements sections:** 7.1 Policy identity; 7.2 Version identity; 9.4 Closure hash; 10.1 Assessment identity; 10.2 Run identity
- **Failure scenario:** Two implementations serialize the same Decimal, timestamp, or Unicode string differently and produce different IDs.
- **Why the wording fails:** The pseudocode names `stable_hash` but does not freeze the hash algorithm, domain separation, canonical object encoding, timestamp precision, Decimal normalization, Unicode normalization, integer bounds, map ordering, or length framing. These choices directly determine every durable identity.
- **Required amendment:** Define one repository-wide canonical hash contract, including exact SHA-256 input bytes, prefixes/domain labels, UTF-8 and Unicode rules, canonical timestamp format and precision, Decimal form, array ordering, object key ordering, null handling, and test vectors.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-006 — Required dependency failure reasons are absent from the registry

- **Severity:** Blocker
- **Requirements sections:** 9 Deterministic input closure; 13.3 Re-resolution; 14.1 Session identity; 16 Controlled reason registry
- **Failure scenario:** Two equally valid mappings are visible at the same cutoffs, or a catalogue/session temporal record is present but ineffective.
- **Why the wording fails:** The requirements require missing, ambiguous, ineffective, and mismatched dependency states to become controlled reasons, but the registry lacks complete codes for mapping ambiguity, instrument-version ambiguity, catalogue ambiguity/ineffectiveness, and trading-session ambiguity. An implementation would have to invent codes or collapse distinct failures.
- **Required amendment:** Add a complete one-to-one registry mapping for every required dependency outcome, or explicitly classify some outcomes as run-aborting durable corruption. No required branch may be left without a frozen code and severity.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-007 — Normalization-result knowledge visibility has no exact clock

- **Severity:** High
- **Requirements sections:** 8.3 Observation visibility; 9 Deterministic input closure
- **Failure scenario:** The event row is available by K, but the owning normalization result or membership becomes durable later.
- **Why the wording fails:** The text requires the result to be “durably recorded by” K but does not identify the exact persisted column, its semantics, or how result and membership visibility are atomically proven. Using event `available_at`, transaction commit time, or a server default would produce different outcomes.
- **Required amendment:** Name the exact DATA-1.4 timestamp/clock used for result visibility and membership visibility, including inclusive boundary behavior. If no suitable durable field exists, require an explicit design response and schema extension rather than inventing one during implementation.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-008 — Generic dependency time language does not match heterogeneous temporal models

- **Severity:** High
- **Requirements sections:** 9.1 Visibility of dependencies; 13 Provenance rules; 14 Trading-session and market-status rules; 15 Lifecycle rules
- **Failure scenario:** A provider mapping uses validity and knowledge intervals, a lifecycle event uses `occurred_at/available_at/recorded_at`, and a session version uses effective/known intervals.
- **Why the wording fails:** Section 9.1 applies one generic “market/occurrence timestamp” and “availability/recording boundary” to all dependencies. The repository models use different axes. An implementation could accidentally compare a knowledge timestamp to market time or use physical insertion order.
- **Required amendment:** Add a dependency-kind table freezing, for each dependency, the exact market/effective cutoff column, exact knowledge cutoff column, inclusive/exclusive bounds, and total ordering.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-009 — Backdated knowledge records can rewrite an earlier assessment

- **Severity:** High
- **Requirements sections:** 9.1 Visibility; 21 No-future-leakage
- **Failure scenario:** After an assessment at K, a new temporal row is inserted with a claimed `known_from <= K`.
- **Why the wording fails:** No-future-leakage is stated in terms of relevant knowledge boundaries, but the requirements do not freeze whether those boundaries are trusted caller data, append-only receipt clocks, or both. A later physically inserted but backdated row could enter a re-evaluation at the same `(M, K)` and change the closure.
- **Required amendment:** Require a non-backdatable durable receipt/recording boundary for every selectable dependency and require it to be `<= K`. Define a collision/corruption outcome if the same assessment identity later reconstructs a different closure.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-010 — Exchange-date derivation is circular

- **Severity:** High
- **Requirements sections:** 8.2 Clock ordering; 14.1 Session identity
- **Failure scenario:** The evaluator must derive the exchange date before it can query the session record, but the text says to derive the date using the selected session timezone.
- **Why the wording fails:** The session cannot be selected until the date/scope is known, yet the date is said to depend on the selected session. This creates an implementation-dependent bootstrap.
- **Required amendment:** Derive the exchange date using the policy-owned fixed timezone `Asia/Kolkata`, then resolve the session record for that date and require its timezone to match exactly.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-011 — Subscription scope, membership, and effective mode are conflated

- **Severity:** High
- **Requirements sections:** 15.2 Subscription selection; 16.2 Error reasons
- **Failure scenario:** A subscription scope exists but its set does not contain the key; or the latest event is `mode_changed` but the new mode does not equal the quote mode.
- **Why the wording fails:** Selection is defined as requiring membership and mode equality, which makes `subscription_instrument_missing` and `subscription_mode_mismatch` unreachable: the candidate disappears before those reasons can be emitted. Accepting the state label `mode_changed` also does not prove the effective mode.
- **Required amendment:** Freeze a staged algorithm: resolve candidate scope(s), reconstruct effective mode and immutable set, then evaluate membership and mode as separate rules. Define exact ambiguity behavior before filtering by eligibility.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-012 — Multiple active subscription ambiguity has no deterministic scope rule

- **Severity:** High
- **Requirements sections:** 15.2 Subscription selection; 19.3 Locking
- **Failure scenario:** Two active subscription scopes on the same connection both contain the key and request mode.
- **Why the wording fails:** The text says ambiguity is evaluated “after deterministic scope resolution” but never defines that resolution. Choosing newest, smallest set, lexicographic ID, or provider scope would produce different results.
- **Required amendment:** Define which fields constitute one logical scope, whether duplicate active scopes are always an error, and the exact total ordering used only for evidence—not for arbitrarily choosing one eligible scope.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-013 — Orphan quote component behavior is incomplete

- **Severity:** High
- **Requirements sections:** 12.4 Required quote components; 12.5 Numeric validity
- **Failure scenario:** An underlying has no bid price but has `bid_size`; a derivative has `last_size` without `last_price`.
- **Why the wording fails:** The text validates a size only “for a present side” and does not reject an orphan size when its price is absent. It also does not freeze last-price/last-size pair semantics.
- **Required amendment:** Define side tuples explicitly. A size without its corresponding price must be either a controlled error or declared intentionally ignorable. Freeze last-trade tuple applicability for every observation kind.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-014 — Tick alignment omits last price

- **Severity:** High
- **Requirements sections:** 12.4 Required quote components; 12.7 Tick alignment
- **Failure scenario:** An underlying has only `last_price`, and it is not a multiple of tick size.
- **Why the wording fails:** Last price is required and positive, but tick alignment applies only when bid or ask is present. An off-tick last price can therefore pass when the optional book is absent.
- **Required amendment:** Explicitly state which price fields require alignment by observation kind, including last price. If last price is intentionally exempt, record the rationale and test it.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-015 — One reason code cannot explain multiple tick failures deterministically

- **Severity:** High
- **Requirements sections:** 11.3 Reason ordering; 12.7 Tick alignment; 16.3 Reason evidence
- **Failure scenario:** Both bid and ask are off tick by different remainders.
- **Why the wording fails:** Reasons must be unique by code, and the only code is `price_not_tick_aligned`. A single scalar evidence payload cannot explain both failed fields without an explicitly canonical bounded collection. Alternatively, emitting two rows violates uniqueness.
- **Required amendment:** Define reason occurrence identity as `(reason code, controlled subject/field)` or define one canonical aggregate evidence shape containing every failed field in fixed order. Apply the same decision to any rule that may fail more than once.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-016 — Dual spread thresholds do not freeze reason precedence or evidence

- **Severity:** High
- **Requirements sections:** 12.8 Spread calculation; 11.2–11.4 Evaluation behavior
- **Failure scenario:** Spread exceeds the tick error threshold but only the basis-point warning threshold, or exceeds both warning dimensions.
- **Why the wording fails:** “Ineligible-first, then warning” does not state whether both warning and error reasons are emitted, whether one code aggregates both dimensions, or which threshold is recorded. The one-code uniqueness rule can discard material evidence.
- **Required amendment:** Freeze a truth table for all combinations of tick/bps clean-warning-error states and a canonical evidence payload containing both observed metrics and both applicable thresholds.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-017 — Market-segment-status target applicability is incomplete

- **Severity:** High
- **Requirements sections:** 9 Deterministic input closure; 12.2 Freshness; 14 Segment status; 15 Lifecycle
- **Failure scenario:** A market-segment-status observation is the assessment target.
- **Why the wording fails:** Section 9 says status targets still require result/raw/session/provider/lifecycle inputs, but lifecycle rules are written for quotes and subscription rules require a provider contract key and request mode. The requirements do not say whether a status target needs connection authorization, a subscription, both, or neither.
- **Required amendment:** Add an exact applicability matrix for target quote versus target segment-status, dependency by dependency and rule by rule.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-018 — Equal-time total ordering is not executable

- **Severity:** High
- **Requirements sections:** 9.2 Deterministic tie-breaking; 14.3 Segment status selection; 15 Lifecycle selection
- **Failure scenario:** Two visible status or lifecycle events have the same semantic time and knowledge time.
- **Why the wording fails:** The text mentions “provider/source ordering when present” but does not name the exact fields or precedence for each dependency. A final deterministic ID tie-break can silently choose between semantically conflicting states rather than report ambiguity.
- **Required amendment:** For each dependency kind, freeze the complete order and distinguish benign duplicate equality from conflicting equal-rank ambiguity. Conflicting states at the same effective rank must not be arbitrarily selected.
- **Disposition:** Accepted — amend before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-019 — Policy registration time semantics are only partially specified

- **Severity:** Medium
- **Requirements sections:** 8.6 Policy knowledge; 17 Persistence
- **Failure scenario:** Policy version 1 is registered today and used to assess a historical context with `evaluation_known_as_of` years earlier.
- **Why the wording fails:** The text permits counterfactual policy input and says registration time does not alter K, but it does not explicitly state whether post-K registration is valid, whether this must be labeled counterfactual, or whether consumers may confuse it with historically available policy truth.
- **Required amendment:** State explicitly that post-K policy registration is allowed or forbidden. If allowed, persist and expose a controlled counterfactual-policy flag or equivalent audit fact without changing assessment identity.
- **Disposition:** Accepted — clarify before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-020 — Evaluator compatibility cardinality is over-broad

- **Severity:** Medium
- **Requirements sections:** 7.5 Evaluator identity
- **Failure scenario:** Two policy versions using schema version 1 require different reviewed evaluator implementations.
- **Why the wording fails:** “One policy schema version may have only one accepted evaluator implementation label” globally couples all policies and versions to one implementation label. This conflicts with the later rule that an evaluator change may require a new policy version.
- **Required amendment:** Freeze compatibility at the intended scope: likely each policy version binds exactly one schema version and one evaluator implementation label. State whether the same schema may be used by multiple implementation labels across different policy versions.
- **Disposition:** Accepted — clarify before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-021 — Policy subject scope is broader than the frozen segment table

- **Severity:** Medium
- **Requirements sections:** 7.1 Stable policy identity; 13.5 Provider segment
- **Failure scenario:** An NSE equity or non-Nifty index observation reaches the evaluator under the same provider/domain identity.
- **Why the wording fails:** The policy family name suggests all Upstox NSE normalized observations, while the segment table names only “Nifty underlying index,” futures, and options. No exact supported subject family or instrument-kind allowlist is frozen.
- **Required amendment:** Define the v1 supported economic subjects and instrument kinds precisely. Unsupported-but-well-formed subjects must have a controlled outcome.
- **Disposition:** Accepted — clarify before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-022 — Reason evidence has no canonical typed union

- **Severity:** Medium
- **Requirements sections:** 16.3 Reason evidence; 17.5 Canonical constraints
- **Failure scenario:** One implementation stores a threshold as Decimal text, another as integer micro-units, and a third as JSON number.
- **Why the wording fails:** Evidence is described as bounded and typed, but the permitted value types, nullability, units, field ordering, list bounds, and canonical encoding are not frozen. Evidence participates in collision/read-back behavior.
- **Required amendment:** Define the controlled evidence schema or explicitly require the design to propose one and then amend the requirements before approval. Include canonical examples for milliseconds, ticks, bps, identifiers, states, and multi-field failures.
- **Disposition:** Accepted — clarify before design.
- **Owner / target:** DATA-1.5 requirements owner / pre-design amendment.

## ADR-023 — Historical baseline wording is stale

- **Severity:** Low
- **Requirements sections:** 2 Verified baseline
- **Failure scenario:** A later reviewer reads “Existing DATA-1.5 branch: None found during inspection” as current state.
- **Why the wording fails:** The header correctly names the branch, but the table can be mistaken for a current claim.
- **Required amendment:** Label the row “State during initial pre-branch inspection” or replace it with the actual branch and initial documentation commit.
- **Disposition:** Accepted — clean up with the requirements amendment.
- **Owner / target:** DATA-1.5 documentation owner / pre-design amendment.

---

## 4. Required concrete adversarial examples

| Required example | Review outcome |
|---|---|
| Same policy version with one threshold changed | Must collide on semantic definition under the same `policy_version_id`; exact collision payload still requires canonical hash definition (ADR-005). |
| YAML key reorder versus semantic change | Key reorder is semantically equal, but source artifact persistence behavior is unresolved (ADR-002). |
| Quote persisted after K | Must be indistinguishable from absent to eligibility evaluation and persist nothing (ADR-004, ADR-007). |
| Freshness boundary ±1 ms | Cannot be tested coherently until visibility/tolerance contradiction is resolved (ADR-001). |
| Bid equals ask | Warning only, subject to all other rules; wording is otherwise consistent. |
| Bid one tick above ask | `market_crossed` error; spread reasons should not additionally fire unless explicitly required. |
| Spread exactly at warning/error thresholds | Inclusive behavior is stated, but dual-axis precedence/evidence remains unresolved (ADR-016). |
| Price exactly/almost tick aligned | Exact Decimal rule is sound; field applicability and multi-field evidence remain unresolved (ADR-014, ADR-015). |
| Future mapping correction | Must not affect prior `(M, K)`; requires non-backdatable receipt boundary (ADR-008, ADR-009). |
| Future session correction | Same result and closure required; exact session temporal axes must be frozen (ADR-008, ADR-010). |
| Authorization after quote | Must not authorize quote; exact equal-time/source ordering remains unresolved (ADR-018). |
| Two active subscription scopes | Must be ambiguous, but logical scope and candidate resolution are not defined (ADR-012). |
| Unsubscribe one source-order step after quote | Must not affect quote; source-order field and ordering must be named (ADR-018). |
| Lifecycle assertion older than 12 hours | Error at `>= 43,200,000 ms` or `> 43,200,000 ms` is not explicitly stated; design must not guess. Add boundary wording in the amendment. |
| Same assessment requested by two runs | Must share assessment via membership; current assessment-run binding contradicts this (ADR-003). |
| Same assessment ID with different closure | Must raise collision/corruption and persist nothing; backdated knowledge policy must prevent legitimate drift (ADR-009). |
| Failure after reasons before membership | One transaction should roll back all rows; requirement is coherent. |
| Downgrade with one child table non-empty | Must refuse before DDL and report deterministic table names; requirement is coherent. |
| Dump/restore physical row reorder | Canonical ordered digests should remain stable; exact canonical encodings remain prerequisite (ADR-005, ADR-022). |

---

## 5. Mandatory challenge-area coverage

| Area | Result |
|---:|---|
| 1. Policy/version identity | Challenged; ADR-002, ADR-005. |
| 2. Canonical policy hashing | Challenged; ADR-002, ADR-005. |
| 3. Evaluator compatibility | Challenged; ADR-020. |
| 4. Assessment/run identity | Challenged; ADR-003. |
| 5. Market-time vs knowledge-time | Challenged; ADR-001, ADR-004, ADR-007–009. |
| 6. Normalization-result visibility | Challenged; ADR-004, ADR-007. |
| 7. Mapping/version/catalogue future leakage | Challenged; ADR-008, ADR-009. |
| 8. Session/status/lifecycle future leakage | Challenged; ADR-008–012, ADR-018. |
| 9. Dependency absence proofs | Challenged; ADR-004, ADR-008, ADR-009. |
| 10. Quote-kind applicability | Challenged; ADR-013, ADR-014, ADR-017, ADR-021. |
| 11. Missing/zero/locked/crossed behavior | Challenged; orphan component gap in ADR-013. |
| 12. Tick/Decimal boundaries | Challenged; ADR-014, ADR-015. |
| 13. Spread precedence | Challenged; ADR-016. |
| 14. Lifecycle ambiguity/staleness | Challenged; ADR-011, ADR-012, ADR-018 and boundary note. |
| 15. Session date/timezone | Challenged; ADR-010. |
| 16. Reason uniqueness/order/severity | Challenged; ADR-006, ADR-015, ADR-016, ADR-022. |
| 17. Retry vs collision | Challenged; ADR-002, ADR-005. |
| 18. Concurrent overlapping runs/locks | Assessment reuse contradiction found in ADR-003; detailed lock design remains a design-gate obligation. |
| 19. Append-only/partial visibility | Requirements coherent; must be proven in design/tests. |
| 20. Real FKs/no unchecked polymorphism | Requirements coherent; design must show typed FK strategy. |
| 21. Downgrade refusal/ownership | Requirements coherent and deferred DATA-1.4 hardening remains excluded. |
| 22. Dump/restore reproducibility | Dependent on ADR-005 and ADR-022. |
| 23. Provisional `point_in_time.py` compatibility | Requirements correctly prohibit activating chain reconstruction; exact adapter remains design work. |
| 24. Leakage into excluded scope | No scope leak found in the requirements draft. |
| 25. Role separation / DATA-1.4 hardening | Correctly excluded; no mixing found in the DATA-1.5 documentation diff. |

---

## 6. Required requirements-resolution work

Before the design response begins, amend the requirements and add a resolution matrix containing, for every ADR finding:

- accepted wording change;
- exact frozen decision;
- whether identity, schema, thresholds, reason registry, tests, or scope changed;
- any new canonical test vector required;
- explicit confirmation that no finding is left for implementation-time interpretation.

At minimum, the amendment must freeze:

1. target future-timestamp visibility;
2. semantic-equivalent source artifact persistence;
3. assessment versus run membership;
4. invisible target command behavior;
5. canonical hash encoding;
6. complete dependency-failure reason registry;
7. exact result/membership knowledge clocks;
8. per-dependency market and knowledge axes;
9. non-backdatable receipt semantics;
10. session-date bootstrap;
11. subscription scope, membership, effective mode, and ambiguity;
12. quote component tuple semantics;
13. price-field tick applicability;
14. repeated reason occurrence/evidence shape;
15. spread precedence truth table;
16. status-target applicability matrix;
17. equal-time conflict handling;
18. policy registration/counterfactual semantics;
19. evaluator compatibility scope;
20. v1 economic-subject allowlist;
21. canonical reason-evidence union.

---

## 7. Gate decision

```text
requirements draft                         COMPLETE
independent adversarial requirements review COMPLETE
requirements amendment / resolution matrix  REQUIRED
pre-implementation design response           NOT AUTHORIZED YET
implementation                               NOT AUTHORIZED
```

The review does not reject DATA-1.5. It prevents ambiguous requirements from becoming durable identities and irreversible schema decisions.

**Final decision:** **NOT APPROVED FOR DESIGN OR IMPLEMENTATION until all blocker/high findings are amended and independently re-reviewed.**
---

## 8. Resolution addendum

The requirements owner accepted every finding `ADR-001` through `ADR-023`. Normative resolutions are incorporated into:

```text
docs/implementation/DATA-1.5-versioned-market-data-quality-policy-requirements.md
```

The amended document now freezes:

- target knowledge visibility separately from market-time eligibility;
- a reachable and testable one-second provider-clock tolerance;
- append-only source artifacts separate from semantic policy versions;
- assessment/run many-to-many membership;
- non-persisting, non-disclosing `target_not_visible`;
- the exact existing repository canonical JSON/SHA-256 contract and test vectors;
- complete dependency ambiguity/effectiveness reasons;
- exact result/event persistence clocks and dependency temporal axes;
- DATA-1.5-owned non-backdatable dependency receipt facts;
- non-circular Asia/Kolkata session-date derivation;
- staged subscription scope/state/set/mode evaluation;
- quote tuple/orphan semantics;
- tick applicability for bid, ask, and last price;
- `(reason_code, subject_key)` reason occurrence identity;
- one aggregate dual-axis spread reason;
- quote versus segment-status applicability;
- equal-time conflict handling that never chooses by ID;
- counterfactual policy-registration audit evidence;
- per-policy-version evaluator compatibility;
- the exact Nifty index-derivatives v1 subject allowlist;
- a bounded canonical typed reason-evidence union;
- corrected baseline history.

No finding was deferred to implementation-time interpretation.

This addendum records remediation, not independent approval. The next gate remains an independent re-review of the amended requirements. Design and implementation remain unauthorized until that re-review passes.
