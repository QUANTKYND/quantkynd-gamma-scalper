# DATA-1.5 — Pre-Implementation Design Gate

**Milestone:** Versioned market-data quality policy  
**Status:** **PASSED — exact design package approved for implementation**  
**Accepted baseline:** `master` at `b461d507d08546d72d952f80016b2617e216d711`  
**Feature branch:** `feature/data15-versioned-market-data-quality-policy`  
**Requirements source commit:** `478a7a917730b5acf12e27e8c3e17d97036e3154`  
**Approved canonical requirements SHA-256:** `a4c7d551d59d7685278faecb6153d84786d9dceff983669699ad78d9f0ff1266`  
**Approved design SHA-256:** `682df6d9128de06474bd48c61b470476a15dbb0337059f883d4eceea670f7598`  
**Design review SHA-256:** `cce9927dacf4440236dc2a791b6d6691f835e63aed0954fcd3ec85a35bf89122`  
**Approval record SHA-256:** `362349978bda22d74e78aab733902d3f2746579a6450cd1e24531858e7d72f55`

## 1. Gate history

The gate sequence is complete:

```text
requirements
→ adversarial requirements review
→ requirements amendments and re-review
→ final requirements consistency check
→ repository-specific design
→ separate adversarial design review
→ design approval
```

The earlier stale references to baseline `eaa243...` and branch `feature/data-1-5-versioned-market-data-quality-policy` are superseded. The only valid baseline and branch are the values in this header.

## 2. Approved artifacts

```text
docs/implementation/DATA-1.5-versioned-market-data-quality-policy-requirements.md
docs/implementation/DATA-1.5-requirements-adversarial-review.md
docs/implementation/DATA-1.5-requirements-amendment-verification.md
docs/implementation/DATA-1.5-versioned-market-data-quality-policy-design.md
docs/implementation/DATA-1.5-design-adversarial-review.md
docs/implementation/DATA-1.5-design-approval.md
```

Implementation must bind to the exact design hash. Any result-affecting change requires an amendment and another review.

## 3. Approval checklist

- [x] Exact package/file layout.
- [x] Exact deterministic identities and excluded evidence.
- [x] Strict YAML parser, semantic projection, source artifacts, and hash vectors.
- [x] Complete 69-code reason registry, applicability, evidence, and precedence.
- [x] Numbered evaluator/orchestration algorithm.
- [x] Exact T/K dependency selection, receipts, candidates, and absence proofs.
- [x] Real FKs for every present dependency; no unchecked polymorphic ID.
- [x] Exact columns/types/tables, constraints, indexes, aggregate validation, and append-only behavior.
- [x] Migration `20260804_05`, bootstrap, triggers, downgrade refusal, and schema verification.
- [x] Repeatable-read UoW, lock namespace `-806150233`, 128 stripes, vectors, chunks, retries, and rollback.
- [x] Exact assessment/run query contracts and no latest fallback.
- [x] One point-in-time compatibility plan without chain activation.
- [x] PostgreSQL 17 unit/integration/concurrency/no-leakage/migration/restore plan.
- [x] Catalogue membership receipt closes profile-membership future leakage.
- [x] Explicit exclusions and changed-file allowlist.
- [x] No application code was part of design approval.

## 4. Implementation stop conditions

Stop and return to design review if implementation discovers any missing FK target, impossible receipt trigger, unrepresentable evidence, changed reason/threshold/applicability, identity change, lock collision, migration ownership conflict, or need to touch an excluded subsystem.

## 5. Next gate

Implementation may begin. DATA-1.5 remains unaccepted until implementation completion, evidence, independent implementation review, and merge.
