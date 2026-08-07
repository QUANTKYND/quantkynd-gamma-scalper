# DATA-1.5 — Design Approval

**Decision:** **APPROVED FOR IMPLEMENTATION**  
**Milestone:** Versioned market-data quality policy  
**Requirements source branch SHA:** `478a7a917730b5acf12e27e8c3e17d97036e3154`  
**Approved canonical requirements SHA-256:** `a4c7d551d59d7685278faecb6153d84786d9dceff983669699ad78d9f0ff1266`  
**Approved design file:** `docs/implementation/DATA-1.5-versioned-market-data-quality-policy-design.md`  
**Approved design SHA-256:** `682df6d9128de06474bd48c61b470476a15dbb0337059f883d4eceea670f7598`  
**Review file:** `docs/implementation/DATA-1.5-design-adversarial-review.md`  
**Review SHA-256:** `cce9927dacf4440236dc2a791b6d6691f835e63aed0954fcd3ec85a35bf89122`

## Authorization boundary

Implementation may begin only after the corrected canonical requirements and this exact documentation package are committed to `feature/data15-versioned-market-data-quality-policy`. The implementation must conform to the approved design without result-affecting interpretation.

Authorized implementation surfaces are limited to the design's §3 file tree and focused fixtures/evidence. The implementation may create migration `20260804_05`, the v1 policy YAML, quality-domain modules, repository/UoW/model/verification changes, point-in-time compatibility adaptations, and tests described by the design.

Not authorized:

- option-chain reconstruction activation;
- latest-state materialization;
- IV/surface/edge/strategy work;
- Redis/live/broker/execution paths;
- database-role separation;
- DATA-1.4 downgrade hardening;
- a new dependency;
- an implicit latest/current policy;
- changes to the approved identities, 69-code registry, thresholds, table/FK model, T/K semantics, lock namespace/stripe count, migration ancestry, or acceptance gates without a reviewed design amendment.

## Required implementation checkpoints

1. Domain contracts, parser, policy artifact, and pure evaluator.
2. Receipt-aware dependency ports/selectors and exact PostgreSQL schema/migration.
3. Repository/UoW orchestration, concurrency, and point-in-time compatibility.
4. PostgreSQL 17 migration/no-leakage/restore evidence and full regression.
5. Independent implementation review before merge.

This approval authorizes coding; it does not accept or merge DATA-1.5.
