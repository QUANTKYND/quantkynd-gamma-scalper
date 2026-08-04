# DATA-1.0 Point-in-Time Semantics Acceptance Evidence

## Repository state

- Branch: `feature/data-1-point-in-time-semantics`
- Starting SHA: `f8b7d89587752189d81d402bec45cba977349588`
- Verified implementation ending SHA: `1599a5e3fa06c5da45187bac33483d3809cba885`
- Baseline ancestry check: passed
- Starting worktree: only `docs/implementation/DATA-1.0-point-in-time-semantics-and-identity-freeze.md` was untracked

The acceptance-evidence commit follows the verified implementation ending SHA and changes only this document.

## Review correction state

- Reviewed implementation SHA: `1599a5e3fa06c5da45187bac33483d3809cba885`
- Correction-task starting SHA: `e0712457ecd977d825eb0c947364a743099ec65a`
- Corrected implementation ending SHA: `aa22fa05825ffa9d053db969e3b8825cf8839f21`
- Reviewed-SHA ancestry check: passed
- Correction-task starting worktree: clean

The correction acceptance-evidence commit follows the corrected implementation ending SHA and changes only this document.

## Commits

- `8a42fb8098a885081bc2abaa17a964fbd66ceec4 feat(data): freeze point-in-time market identity domain`
- `487f3f8b952ea18328610568e1661c8a0b5c9d86 test(data): prove point-in-time and identity invariants`
- `1599a5e3fa06c5da45187bac33483d3809cba885 docs(data): freeze DATA-1.0 semantics and scope`
- `7d5ed1dbe2bf0ef1d59bba71a69d58db02925064 fix(data): harden point-in-time reconstruction invariants`
- `07373c777508cbc68af3398b6b5c82c1cac6544f test(data): cover review correction invariants`
- `aa22fa05825ffa9d053db969e3b8825cf8839f21 docs(data): document DATA-1.0 review corrections`

## Files changed

- `backend/app/core/hashing.py`
- `backend/app/instruments/identity.py`
- `backend/app/market_data/point_in_time.py`
- `backend/app/simulation/config.py`
- `backend/tests/market_data/test_point_in_time_events.py`
- `backend/tests/market_data/test_point_in_time_identity.py`
- `docs/conventions.md`
- `docs/data-models.md`
- `docs/dependencies.md`
- `docs/design.md`
- `docs/implementation/DATA-1.0-point-in-time-semantics-and-identity-freeze.md`
- `docs/implementation/DATA-1.0-point-in-time-semantics.md`
- `docs/plan/acceptance-gates.md`
- `docs/plan/options-market-infrastructure.md`
- `docs/plan/roadmap.md`
- `docs/testing.md`

## Frozen identity model

`UnderlyingInstrumentIdentity`, `FuturesContractIdentity`, and `OptionContractIdentity` own provider-neutral economic identity. Option identity contains exchange, underlying identity, expiry exchange date, Decimal strike, option side, exercise style, settlement type, economically defining Decimal multiplier, and currency.

`UnderlyingInstrumentVersion`, `FuturesContractVersion`, and `OptionContractVersion` own inclusive `valid_from`, exclusive `valid_until`, lot size, Decimal tick size, display symbol, trading status, catalogue version, record time, and optional system-time supersession. Trading metadata changes create a new version without changing unchanged economic identity.

`ProviderContractMapping` owns provider, provider key, contract-version reference, provider payload provenance, source-row identity, effective interval, record time, and optional system-time supersession. Different providers can map to the same economic contract version.

## Frozen time model

`MarketEventTime` separates UTC-normalized `exchange_timestamp`, optional physical `received_at`, earliest eligible `available_at`, immutable record `recorded_at`, and availability basis. Naive timestamps fail. Receipt-based availability requires receipt time, availability cannot precede receipt, and record time cannot precede availability.

`PointInTimeQuery` separates `market_as_of` from optional `known_as_of`. Contract versions and provider mappings pass both effective-time and knowledge/system-time visibility. Defensible knowledge-time replay is the default. Historical imports lacking original dissemination or receipt time are marked `historical_import` and require an explicit limitation override.

## Correction, supersession, and quality model

Raw and normalized observations are immutable. A corrected normalized quote creates a new event whose `supersedes_event_id` names the prior event. The earlier event remains visible to an earlier knowledge cutoff.

Contract versions and provider mappings use exclusive `superseded_at` system-time boundaries. `DataQualityAssessment` is append-only and keyed by policy ID and version. Reconstruction selects the latest assessment visible at the knowledge cutoff, so later policy re-evaluation does not rewrite an earlier decision.

Raw observation deduplication requires a guaranteed provider event ID, scoped provider sequence, source-file and source-row identity, or explicit ingestion-event ID. Content hashes provide provenance only and cannot collapse separately transmitted identical quotes.

## Review corrections

- Provider-sequence identity now requires a non-empty explicit `provider_sequence_scope_id`. Scope is part of the raw-event hash, and no global scope is inferred.
- `InvalidCorrectionGraphError` fails closed for missing or historically ineligible targets, cross-contract or cross-event-type relations, self-supersession, cycles, and competing visible corrections of one target. Validation is deterministic under input permutation.
- `ConflictingSemanticIdentityError` rejects contract-version, provider-mapping, and normalized-event records that share a semantic ID but differ as complete immutable records. Completely equal duplicates remain idempotent.
- Normalized bid, ask, and last prices accept finite non-negative `Decimal` values. Zero and `None` remain distinct, negative values fail, and quality-policy assessments alone determine whether a zero-price quote is chain-eligible.

## Deterministic hashing and chain selection

The existing simulation canonical serializer and SHA-256 helper moved to `app.core.hashing` without changing accepted simulator identity behavior. Canonical JSON sorts mapping keys and unordered sets, normalizes finite numeric values and Decimal-equivalent text forms, normalizes aware datetimes to UTC, rejects naive timestamps and non-finite numbers, and excludes runtime timestamps from economic and behavioral identity material.

Chain reconstruction requires effective and visible contract versions and mappings, market and knowledge cutoffs, and an eligible assessment under the requested policy version. It applies visible correction relations and selects by newest exchange time, provider sequence, event order, receipt time, availability time, and stable event ID. Results sort by expiry, strike, and option side.

## Verification

- `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests`: passed with exit code 0.
- `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest`: passed, `314 passed in 7.20s`.
- `cd frontend && npm run lint`: passed with exit code 0.
- `cd frontend && npm run build`: passed, `12316 modules transformed`, production build completed in `3.19s`.
- `git diff --check`: passed with exit code 0.
- `git status --short`: clean at the verified implementation ending SHA.
- Tracked generated-artifact scan for `__pycache__`, `.pyc`, `dist`, and `node_modules`: no matches.
- Private-key and AWS access-key signature scan outside ignored build/dependency paths: no matches.

No Python formatter, linter, or type checker is configured in `backend/pyproject.toml`. The frontend build emitted the existing non-failing warning that its main minified chunk exceeds 500 kB.

## Review correction verification

- `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/market_data -q`: passed, `39 passed in 0.13s`.
- `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests`: passed with exit code 0.
- `cd backend && UV_CACHE_DIR=/tmp/uv-cache uv run pytest`: passed, `328 passed in 5.50s`.
- `cd frontend && npm run lint`: passed with exit code 0.
- `cd frontend && npm run build`: passed, `12316 modules transformed`, production build completed in `1.37s`.
- `git diff --check`: passed with exit code 0.
- `git status --short`: clean at the corrected implementation ending SHA.
- `git merge-base --is-ancestor 1599a5e3fa06c5da45187bac33483d3809cba885 HEAD`: passed with exit code 0.
- Tracked generated-artifact scan for `__pycache__`, `.pyc`, `dist`, and `node_modules`: no matches.
- Private-key and AWS access-key signature scan outside ignored build/dependency paths: no matches.

No backend formatter, linter, or type checker was added. The frontend build retained the non-failing main-chunk size warning.

## Known limitations and explicit exclusions

- The full DATA-1 gate remains open: Postgres persistence, SQLAlchemy repositories, Alembic migrations, catalogue ingestion, session-calendar integration, retention, restore testing, and provider adapters are not implemented.
- Historical imports without defensible original availability cannot support an unqualified knowledge-time replay claim.
- Quote freshness remains an input to the requested quality policy; DATA-1.0 does not introduce a persistence-backed freshness service.
- No Postgres dependency, live option feed, IV calculation or surface, strategy expansion, backtest, Redis path, paper router, live-capital route, or broker order path was introduced.
