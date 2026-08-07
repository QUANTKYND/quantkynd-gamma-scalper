# Acceptance Gates

## Strategy Contract gate

- One underlying and one structure.
- Exact selection, entry, hedge, exit, sizing, and risk rules.
- Versioned configuration and hash.
- No discretionary gaps.

## Deterministic option engine gate

- Strategy, simulation-market, path, policy, cost, runtime-risk, and accounting inputs are explicit and hashed.
- Underlying-path and executable market-state hashes are distinct, stable, and reproducible from persisted artifacts.
- Expiry dates and year fractions derive from one session clock.
- Every executable timestamp and step fraction validates against the configured weekday session clock.
- Reference pricing tests pass.
- Put-call parity passes.
- IV round trips pass over the approved domain.
- Greeks match finite differences within tolerance.
- Units and conventions are documented.
- Invalid inputs fail explicitly.

## Hedge simulator gate

- Deterministic replay by seed.
- Exit and risk evaluation precede any same-timestamp routine hedge.
- Premium risk includes contract multipliers and configured entry costs before fills are journaled.
- Position P&L, session P&L, session hedge count, and total hedge count retain distinct semantics.
- Entry costs are included in position and first-session P&L; overnight gaps are included in new-session P&L.
- Spread, liquidity, matched-contract, and daily-theta entry gates execute before fills; expected edge is explicitly deferred to EDGE-1.
- A post-policy absolute-delta breach forces a reducing hedge or exits deterministically if contract granularity cannot satisfy the cap.
- Pre-hedge trigger delta and post-hedge residual delta are separately recorded and summarized.
- Ledger reconciles to machine or accounting tolerance.
- Frictionless higher-frequency hedging reduces hedge error in controlled cases.
- More trading increases modeled costs.
- Cost increases affect band width in the expected direction for the baseline formula.
- Policies receive identical paths and information.
- P&L attribution sums to terminal P&L.
- Post-identity selection, engine, and reconciliation failures persist immutable failed manifests.

## Point-in-time data gate

DATA-1.0 satisfies the semantic sub-gate when deterministic economic identity is separate from contract versions and provider mappings; market and knowledge clocks are explicit; append-only corrections and quality reassessments preserve earlier results; canonical Decimal/time hashing is stable; and focused no-future-leakage tests pass. DATA-1.1 adds a narrower persistence sub-gate: semantic IDs are separate from append-only durable record IDs; locked writes enforce one strictly later same-scope successor; single-snapshot reads validate graphs and apply market eligibility before supersession; one unit of work represents exactly one final transaction; migration `20260804_02` preserves legacy semantic IDs or refuses ambiguous `superseded_at`; destructive tests require exact names, sentinels, opt-in, local-host safety, and advisory locks; and real migration and dump/restore equivalence passes with zero skipped PostgreSQL tests. DATA-1.2 adds a narrower provider-ingestion sub-gate for local Upstox BOD Nifty catalogue ingestion: artifact identity is split from semantic and physical source rows; row-order permutation and runtime timestamp rebinding preserve semantic identities; commit mode uses one accepted write-boundary knowledge timestamp; malformed in-profile rows fail closed; every non-root catalogue explicitly names the current knowledge leaf; version and mapping successors also attach to their current knowledge leaves; provider binding is compared by stable economic instrument ID; market-time reads use transitive lineage suppression so each eligible descendant hides every eligible ancestor even through ineligible intermediates while separate roots fail closed; and PostgreSQL 17 migration, concurrency, overlapping historical query, and restore equivalence pass with zero skipped acceptance-critical tests. DATA-1.2 status: ACCEPTED. Market-event persistence is still required for the full DATA-1 gate.

DATA-1.3 status: ACCEPTED. The independently reviewed normalization sub-gate provides immutable raw identity and exact capture hashes; caller-owned market/knowledge cutoffs; owned and bounded Upstox V3 decoding; controlled provider-identity boundaries; actual mapping/version/economic provenance; deterministic partial results; union-scoped deferred declarations; closed offline lifecycle transitions; byte-identical fixtures and canonical replay; and a one-transaction read-only PostgreSQL resolver. No event persistence, live wiring, quality policy, or execution path is implied. DATA-1 remains ACTIVE until those remaining full-gate requirements are completed.

DATA-1.4 status: implementation complete; acceptance evidence recorded; independent review pending. Revision `20260804_04` persists immutable raw frames, deterministic normalization results, normalized quote/status observations and failures, subscription instrument sets, and ordered raw and normalized provider lifecycle batches. It enforces append-only storage, deterministic identity and collision handling, bounded lock striping and chunk planning, typed lifecycle subtypes, deferred batch reconciliation, guarded downgrade refusal, exact owned lifecycle-function cleanup, migration drift checks, and dump/restore verification. This evidence does not accept DATA-1.4. DATA-1 remains ACTIVE because quality policy, point-in-time chain reconstruction, retention, live-state rebuilding, trade persistence, analytics, and execution remain incomplete.

- Economic contract identity is stable and trading metadata is validity-bounded.
- Historical chain reconstruction is deterministic.
- No future contract or quote leakage.
- Quote quality and exclusions are persisted.
- Exchange-session and timezone behavior is tested.
- Database migrations and restore path are tested.

## IV surface gate

- Valid prices solve IV or expose explicit failure.
- Price-IV round trips pass.
- Surface inputs and exclusions are reconstructable.
- Static-arbitrage diagnostics are visible.
- Implied variance declares strike coverage and interpolation risk.

## Opportunity engine gate

- Physical and implied variance horizons match.
- Net edge includes theta, option costs, expected hedge costs, and model-risk buffer.
- Eligibility rules use only point-in-time state.
- Rejected candidates expose reason codes.
- Opportunity results are reproducible from snapshot and configuration IDs.

## Historical replay gate

- Every decision, intent, order, fill, mark, and ledger entry is reconstructable.
- Same inputs produce the same event stream.
- Fill rules are conservative and explicit.
- Expiry and settlement reconcile.
- No same-event or future-event fill leakage.

## Robustness gate

- Out-of-sample evaluation exists.
- Neighboring parameters do not collapse performance.
- Costs and latency are stressed.
- Regime results are reported.
- Simple baselines remain included.
- Any selected policy has a documented reason beyond maximum backtest P&L.

## Live read-only gate

LIVE-RV-1 is a precursor and does not pass this gate. It accepts only the selectable underlying history, one-process LTPC multiplexing, visible freshness, and provisional close-to-close overlay. Durable restart recovery, sequence-gap provenance, option state, surfaces, Greeks, and shadow decisions remain required for full LIVE-1 acceptance.

- Feed and subscription state are separate from authentication state.
- Sequence gaps and freshness are visible.
- Redis loss does not lose durable truth.
- Current state survives worker restart or rebuilds deterministically.
- Shadow decisions run without order submission across multiple sessions.

## Paper execution gate

- Risk precedes every order path.
- Idempotency prevents duplicates.
- Partial fills and cancel-replace work.
- Unknown acknowledgement state blocks unsafe retries.
- Positions and cash derive from fills and ledger entries.
- Reconciliation differences create lockouts.
- Kill switch works in tests.

## Paper acceptance gate

- Multi-session paper campaign completed.
- Failure drills completed.
- Every order and hedge is reconstructable.
- Greeks and positions match independent checks.
- Risk rules fired correctly.
- P&L attribution is stable and believable.
- Data freshness and missing-data behavior are visible.
- Restart recovery does not duplicate actions.
- No live-capital route exists.
