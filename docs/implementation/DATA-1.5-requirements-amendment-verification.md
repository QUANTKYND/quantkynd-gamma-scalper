# DATA-1.5 — Requirements Amendment Verification

**Verification type:** Consolidated amendment and follow-up re-review correction check  
**Independence:** Not final approval; post-commit consistency verification remains required by the gate  
**Implementation status:** Not authorized

## Result

All findings `ADR-001` through `ADR-023` and follow-up findings `RR-001` through `RR-004` have a normative resolution in the canonical requirements draft. No finding is deferred to implementation-time interpretation.

| Finding | Verification result | Normative resolution |
|---|---|---|
| ADR-001 | Addressed | Target knowledge visibility is separate from market-time eligibility; any future target is ineligible and dependency selectors use the bounded dependency cutoff. |
| ADR-002 | Addressed | Policy source artifacts are append-only evidence rows separate from semantic policy-version equality. |
| ADR-003 | Addressed | Assessments contain no run ID; run linkage exists only through many-to-many membership. |
| ADR-004 | Addressed | Invisible and nonexistent targets share non-persisting outcome `target_not_visible`. |
| ADR-005 | Addressed | Exact existing `canonical_json`/`stable_hash` behavior and three expected vectors are frozen. |
| ADR-006 | Addressed | Missing ambiguity/effectiveness reason codes were added. |
| ADR-007 | Addressed | Event `available_at`, owning result `persistence_recorded_at`, and atomic membership visibility are named; event semantic `recorded_at` is provenance only. |
| ADR-008 | Addressed | A dependency-kind temporal-axis table freezes market and knowledge filters. |
| ADR-009 | Addressed | Required dependencies bind accepted repository persistence clocks or typed non-backdatable receipt facts, with conservative migration bootstrap for legacy rows; closure drift is collision/corruption. |
| ADR-010 | Addressed | Exchange date is derived with policy-owned `Asia/Kolkata` before session resolution. |
| ADR-011 | Addressed | Subscription scope, state, immutable set, and effective mode are evaluated in stages. |
| ADR-012 | Addressed | Logical scope identity is `subscription_scope_id`; multiple active containing scopes are ambiguous. |
| ADR-013 | Addressed | Bid/ask/last tuples and orphan component behavior are frozen. |
| ADR-014 | Addressed | Every present bid, ask, and last price is tick-aligned. |
| ADR-015 | Addressed | Reason occurrence identity is `(reason_code, subject_key)`. |
| ADR-016 | Addressed | One aggregate spread reason is selected by a complete tick/bps truth table with both metrics in evidence. |
| ADR-017 | Addressed | Quote and market-segment-status targets have an explicit applicability matrix. |
| ADR-018 | Addressed | Equal-time conflicts cannot be resolved by deterministic ID; IDs only order evidence. |
| ADR-019 | Addressed | Post-K policy registration is allowed and exposed by a non-semantic counterfactual audit flag. |
| ADR-020 | Addressed | Each policy version binds one schema and one evaluator label. |
| ADR-021 | Addressed | v1 scope is restricted to the exact Nifty index-derivatives profile and `NSE_INDEX`/`NSE_FO` status targets. |
| ADR-022 | Addressed | A bounded canonical typed evidence union is frozen. |
| ADR-023 | Addressed | Baseline wording is corrected to the actual branch-creation history. |

## Follow-up re-review findings

| Finding | Verification result | Normative resolution |
|---|---|---|
| RR-001 | Addressed in replacement set | Non-suffixed requirements and review files are canonical; suffixed duplicates must be removed during commit. |
| RR-002 | Addressed | Future targets are always ineligible, and all market-time dependencies use the bounded dependency cutoff. |
| RR-003 | Addressed | Target durability visibility uses event availability, exact atomic membership, and owning result persistence time; event semantic `recorded_at` is not a persistence clock. |
| RR-004 | Addressed | Existing authoritative persistence clocks are reused; other rows receive typed receipt facts, and legacy rows use the migration bootstrap transaction timestamp. |

## Cross-consistency checks

- The assessment identity remains independent of disposition, reasons, dependency closure, persistence timestamp, and run packaging.
- The assessment equality/collision comparison includes closure, ordered reason occurrences, typed evidence, and disposition.
- Policy source byte changes do not mutate policy semantics.
- Source artifacts cannot select a policy version or serve as an implicit current-policy pointer.
- A target hidden after `known_as_of` cannot produce a persisted reason that reveals its existence.
- Provider timestamps are never rewritten; any target after `evaluation_market_as_of` is ineligible.
- Dependency selectors are bounded by `dependency_market_as_of = min(provider_timestamp, evaluation_market_as_of)`.
- Session discovery is no longer circular.
- Subscription eligibility no longer filters away mode, membership, or inactivity reasons.
- Locked and crossed quotes do not also emit spread reasons.
- Tick failures can explain multiple fields without duplicate-code ambiguity.
- Market-segment-status targets do not require quote-only mapping, instrument, catalogue, or subscription dependencies.
- No database-role separation, DATA-1.4 downgrade hardening, chain reconstruction, IV, strategy, Redis, broker, or execution work was introduced.

## Remaining gate

This verification is not final approval. The next permitted step is to commit the canonical replacement files, remove the two suffixed duplicates, and perform a post-commit consistency re-review. Application code, migrations, configuration, and tests remain unauthorized until that gate passes.
