# DATA-1.5 — Independent Adversarial Design Review

**Reviewed design:** `DATA-1.5-versioned-market-data-quality-policy-design.md`  
**Reviewed design SHA-256:** `682df6d9128de06474bd48c61b470476a15dbb0337059f883d4eceea670f7598`  
**Requirements baseline:** branch SHA `478a7a917730b5acf12e27e8c3e17d97036e3154`  
**Review mode:** separate adversarial pass performed after freezing the design text; it is not an external human or third-party review.  
**Implementation status at review start:** not authorized.

## 1. Review result

The design was challenged against every checkbox in the pre-implementation gate, all ADR/RR resolutions, repository source anchors, and the mandatory hostile cases. Ten issues were identified during the pass; all ten are resolved in the reviewed design bytes named above. No blocker, high, medium, low, or open question remains.

| ID | Initial severity | Challenge | Resolution verified in reviewed design | Status |
|---|---|---|---|---|
| DREV-001 | blocker | The original gate contained stale `eaa243...` baseline and an obsolete branch spelling. | Approval package includes a corrected gate anchored to `b461...`, branch `feature/data15...`, requirements SHA `478a...`, and this design hash. | resolved |
| DREV-002 | high | Mixed visible/invisible targets could otherwise create a partial run or disclose hidden existence. | §8 requires all-target cutoff preflight; any missing/hidden target yields one non-persisting command outcome and no run row. | resolved |
| DREV-003 | high | Receipt rows could be omitted by direct temporal writes, allowing caller-supplied `recorded_at` to become de facto receipt time. | §§10–12 require four typed receipt tables, atomic repository insertion, legacy bootstrap, and deferred completeness triggers on existing temporal tables. | resolved |
| DREV-004 | high | A generic dependency table could reintroduce unchecked polymorphic IDs. | §10 uses a generic root only for canonical order; every present candidate has exact typed nullable FK columns, composite FKs, and a kind-shape constraint. | resolved |
| DREV-005 | high | Reason evidence is bounded to 16 IDs while ambiguity may contain thousands of candidates. | Full candidates are rows; reason evidence stores dependency ID, count, and candidate-set hash. A 17-candidate test is mandatory. | resolved |
| DREV-006 | medium | Repository-generated registration timestamps can differ on exact retries. | Version/artifact `registered_at` is non-semantic, first-insert-only, and excluded from equality; every semantic field remains compared. | resolved |
| DREV-007 | medium | A status target could recursively select itself as a status dependency. | §8/§9 applicability explicitly excludes self-status dependency and quote-only dependencies for status targets. | resolved |
| DREV-008 | medium | Leaving `_selected_assessment` latest-by-persistence would violate exact lookup despite a correct new repository. | §14 replaces provisional identity/vocabulary and requires exact event/version/M/K matching with no max/latest fallback. | resolved |
| DREV-009 | blocker | Requirements §§14.1–14.2 retained stale `provider_timestamp` session wording after RR-002, conflicting with §§8.2–8.3 and the explicit supersession matrix. | The bundled canonical requirements replace both references with `dependency_market_as_of`; the design binds the corrected requirements SHA and uses T in session SQL and rules. | resolved |
| DREV-010 | high | Catalogue membership/profile evidence had no repository-owned receipt, so a membership appended later to an older catalogue could leak into an earlier K. | §§9–12 and 19–20 add a typed membership receipt, legacy bootstrap, atomic writer integration, deferred parent trigger, and receipt-aware selector. | resolved |

## 2. Checklist

- [x] Baseline and source anchors verified.
- [x] ADR-001 through ADR-023 and RR-001 through RR-004 are reflected.
- [x] Policy/version identities exclude mutable evidence.
- [x] Semantic policy hash covers every result-affecting field.
- [x] Evaluator compatibility is bound to one policy version.
- [x] Assessment identity is independent of result and run packaging.
- [x] M and K are mandatory and ordered.
- [x] Result persistence and atomic membership govern target knowledge visibility.
- [x] Provider timestamp is the explicit v1 market-time basis.
- [x] Every dependency selector is T/K bounded and has deterministic conflict semantics.
- [x] Future records and future target timestamps cannot import post-M state.
- [x] Absence proofs include scope, T, K, and selector version.
- [x] All 69 reasons have frozen ordinals, severity, applicability, subject keys, and evidence profiles.
- [x] Disposition reduction and rule suppression/precedence are deterministic.
- [x] Durable corruption aborts the complete run.
- [x] Present dependencies have real FKs; generic roots cannot carry arbitrary IDs.
- [x] Exact tables, columns, constraints, indexes, triggers, aggregates, and migration order are specified.
- [x] DATA-1.5 lock namespace, 128 stripes, vectors, ordering, retries, and chunk formulas are specified.
- [x] Full run visibility is atomic.
- [x] Exact lookup never falls back to latest policy/assessment.
- [x] Point-in-time provisional types have one explicit compatibility plan.
- [x] PostgreSQL 17 migration/concurrency/no-leakage/restore evidence is planned with zero skips.
- [x] Option chain, IV, strategy, Redis, broker, roles, and DATA-1.4 hardening remain excluded.
- [x] No implementation choice is deferred to coding time.

## 3. Mandatory examples replayed

The review replayed same-version threshold mutation, source key reorder, post-K target/result, each freshness boundary, locked/crossed markets, exact spread/tick boundaries, future mapping/session/lifecycle changes, two active subscription scopes, one-step unsubscribe, 12-hour lease, concurrent same assessment across runs, closure collision, injected failure before membership, child-only downgrade data, physical row reorder, hostile hash seed/locale/TZ, and a 17-candidate ambiguity. Every case has a named mechanism and test in §§7–17.

## 4. Decision

**APPROVED FOR IMPLEMENTATION**, conditional only on committing the corrected canonical requirements, this exact design, this review, the approval record, and the corrected gate together before application code begins. Any result-affecting deviation requires a design amendment and another review. Documentation approval does not accept the eventual implementation.
