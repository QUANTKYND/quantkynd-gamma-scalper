# Codex Task — SIM-1.2.1 Version and Artifact Identity Hardening

## Milestone

**SIM-1.2.1 — Simulator, configuration-schema, and artifact-version identity**

## Branch

```text
feature/deterministic-option-and-hedge-simulator
```

## Starting point

```text
5c3e6b3d32982b9fd36580f65f56e51a9c9a0535
```

## Objective

Complete the final release-identity hardening for STRAT-1/SIM-1 before merging.

The SIM-1.2 implementation is functionally complete, but the persisted version identifiers still describe the previous simulator and schema generation:

```python
SIMULATOR_VERSION = "sim-1.1"
```

while the implementation and acceptance record identify the system as SIM-1.2.

The simulation-market and run configuration schemas also remain declared as schema version `1`, even though their accepted structure changed during SIM-1.2:

- The market schema removed the duplicated futures half-spread field.
- The run schema added explicit entry assumptions and new provenance semantics.
- The path schema correctly moved to generator version `2`.

This task must make persisted identities tell the exact truth about the code and schemas that generated each run.

Do not alter pricing, hedge policies, risk behavior, paths, fills, accounting, or strategy semantics except where necessary to carry correct version metadata.

---

## Required reading

Read:

```text
AGENTS.md
docs/conventions.md
docs/data-models.md
docs/testing.md
docs/simulation/architecture.md
docs/simulation/artifacts.md
docs/simulation/numerical-conventions.md
docs/strategy/configuration-reference.md
docs/implementation/SIM-1.2-state-provenance-and-risk.md
backend/app/simulation/engine.py
backend/app/simulation/config.py
backend/app/simulation/artifacts.py
backend/app/simulation/paths.py
backend/app/simulation/run_store.py
backend/app/cli/run_gamma_simulation.py
config/simulation/nifty-synthetic-market-v1.yaml
```

Repository conventions remain in force:

- No explanatory comments in new code.
- Unknown configuration fields fail.
- New behavioral contracts require versioned identities.
- No broker, paper-order, database, Redis, or live-trading code.
- No direct frontend `useEffect`.

---

# 1. Bump the simulator implementation version

## Problem

The current branch still declares:

```python
SIMULATOR_VERSION = "sim-1.1"
```

The engine behavior has materially changed since SIM-1.1:

```text
underlying-path/executable-state separation
clock enforcement
futures-state derivation
entry quality and theta gates
hard absolute-delta control
corrected risk P&L references
failed-manifest boundary
expanded provenance
non-finite input rejection
```

Persisting these runs as `sim-1.1` makes the manifest and run identity inaccurate.

## Required correction

Change the simulator version to:

```python
SIMULATOR_VERSION = "sim-1.2"
```

Use a single source of truth.

Every location must derive from the same constant:

```text
SimulationRunConfig.simulator_version
SimulationManifest.simulator_version
CLI output
run-config.json
manifest.json
run identity
```

Do not duplicate the version string in multiple modules.

## Required tests

- `build_simulation_run_config` records `sim-1.2`.
- A completed manifest records `sim-1.2`.
- CLI JSON records `sim-1.2`.
- Changing only simulator version changes `run_config_hash`.
- Changing only simulator version changes `run_id`.
- A SIM-1.2 run cannot collide with an otherwise identical SIM-1.1 run.

---

# 2. Version the simulation-market schema correctly

## Problem

`SimulationMarketConfig` remains:

```python
schema_version: Literal[1]
```

but the accepted schema changed between the pre-SIM-1.2 branch and the current implementation.

The previous schema included:

```yaml
futures:
  half_spread_per_unit: ...
```

The current schema intentionally removed that field and assigned execution friction exclusively to the run cost model.

This is a schema-breaking change.

## Required correction

Change the simulation-market schema to:

```python
schema_version: Literal[2]
```

Update the checked-in market configuration:

```yaml
schema_version: 2
```

Rename the config file and market ID only if repository conventions require the instance name to track its schema. Preferred explicit naming:

```text
config/simulation/nifty-synthetic-market-v2.yaml
market_id: nifty-synthetic-market-v2
```

If the file remains named `v1`, document clearly that the suffix is market-scenario version rather than schema version. Renaming to `v2` is preferred because it avoids ambiguity.

Update every CLI example, test fixture, README command, and document reference.

## Loader behavior

A legacy schema-version-1 payload must fail explicitly as unsupported.

Preferred error semantics:

```text
unsupported simulation-market schema version: 1
```

Do not let it fail only as an unrelated extra-field error.

A migration utility is not required.

## Required tests

- Version-2 market config loads.
- Version-1 market config is rejected explicitly.
- Unknown version is rejected.
- The removed futures spread field remains rejected.
- Market config hash includes schema version.
- Changing schema version changes market config hash.
- All checked-in commands reference the active config filename.

---

# 3. Version the simulation-run schema correctly

## Problem

`SimulationRunConfig` remains:

```python
schema_version: Literal[1]
```

although its persisted contract changed.

The current run contract includes:

```text
entry_assumptions
separate path and executable-state provenance
revised runtime-risk behavior
SIM-1.2 simulator identity
```

Even where executable-state hash is stored in the result/manifest rather than the pre-run config, consumers must be able to distinguish the current run-config shape from the earlier schema.

## Required correction

Change to:

```python
schema_version: Literal[2]
```

Update:

```text
build_simulation_run_config
run-config.json
tests
documentation
artifact examples
```

A version-1 run-config payload should not validate as version 2.

## Required tests

- New run configs have schema version 2.
- Schema version participates in `run_config_hash`.
- Changing only run schema version changes `run_config_hash`.
- A version-1 run-config artifact is distinguishable from version 2.
- Current artifact round-trip validation passes.

---

# 4. Add an explicit manifest schema version

## Problem

`SimulationManifest` currently carries simulator version but no manifest schema version.

The manifest has evolved to include:

```text
market config identity
path config identity
underlying path hash
executable-state hash
policy hash
cost-model hashes
runtime-risk hash
entry assumptions
selected contract metadata
clock configuration
```

Downstream readers need to know which manifest structure they are parsing independently of which simulator generated it.

## Required correction

Add:

```python
manifest_schema_version: Literal[2]
```

Use `2` because the committed manifest represents the expanded provenance generation.

Populate it in running, completed, and failed manifests.

Persist it in `manifest.json`.

Do not derive manifest schema from simulator version.

## Required validation

- Running manifests may have nullable selected contract and executable-state values.
- Completed manifests require the existing completed provenance.
- Failed manifests preserve manifest schema version and all pre-failure provenance available.

## Required tests

- Running manifest has schema version 2.
- Completed manifest has schema version 2.
- Failed manifest has schema version 2.
- Unsupported manifest schema is rejected.
- Manifest JSON round-trips through `SimulationManifest`.
- Existing completed-provenance validation remains intact.

---

# 5. Clarify path, state, simulator, and schema versions

Document the distinction:

| Identity | Meaning |
|---|---|
| `generator_version` | Algorithm/schema generation of the exogenous path |
| `path_hash` | Exact exogenous path and generation inputs |
| `executable_market_state_hash` | Exact derived market-state scenario |
| `simulator_version` | Engine behavior generation |
| `SimulationMarketConfig.schema_version` | Market-config payload shape |
| `SimulationRunConfig.schema_version` | Run-config payload shape |
| `manifest_schema_version` | Manifest payload shape |
| `strategy.schema_version` | Strategy-contract payload shape |

No two fields should be described as interchangeable.

Update:

```text
docs/simulation/architecture.md
docs/simulation/artifacts.md
docs/simulation/numerical-conventions.md
docs/strategy/configuration-reference.md
docs/data-models.md
docs/testing.md
README.md
docs/implementation/SIM-1.2-state-provenance-and-risk.md
```

The implementation acceptance document must note the final SIM-1.2.1 release-identity correction rather than silently editing historical claims.

---

# 6. Add release-identity regression tests

Add a focused test module, for example:

```text
backend/tests/simulation/test_version_identity.py
```

Cover:

```text
simulator version changes run identity
market schema version changes market hash
run schema version changes run hash
manifest schema is independent of simulator version
path generator version remains 2
all CLI/artifact version fields agree
legacy market schema fails explicitly
completed and failed manifests retain schema versions
```

## Cross-artifact consistency

For one completed run, assert:

```text
CLI simulator_version
=
manifest simulator_version
=
run-config simulator_version
=
SIMULATOR_VERSION
```

Assert:

```text
manifest.market_config_hash
=
hash(market-config.json)
```

Assert:

```text
manifest.run_config_hash
=
hash(run-config.json)
```

Version fields must participate in those hashes.

---

# 7. CLI and command updates

Update every example to use the active market config filename.

The CLI success output must continue exposing:

```text
simulator_version
strategy_config_hash
market_config_hash
path_config_hash
path_hash
executable_market_state_hash
run_config_hash
policy_config_hash
option_cost_model_hash
futures_cost_model_hash
runtime_risk_hash
```

Optionally add:

```text
market_schema_version
run_schema_version
manifest_schema_version
path_generator_version
```

Adding these fields is preferred.

## Required CLI test

Run one deterministic simulation and verify all version values and hashes agree with persisted artifacts.

---

# 8. Acceptance criteria

## Simulator identity

- [x] `SIMULATOR_VERSION` is `sim-1.2`.
- [x] Run config, manifest, CLI, and run identity use one source of truth.
- [x] SIM-1.1 and SIM-1.2 runs cannot collide.

## Market schema

- [x] Market schema is version 2.
- [x] Checked-in YAML uses schema version 2.
- [x] Legacy version 1 fails explicitly.
- [x] Removed duplicate futures-spread field remains rejected.
- [x] References use the active config filename.

## Run schema

- [x] Run-config schema is version 2.
- [x] Schema version participates in run-config hash.
- [x] Version-1 and version-2 artifacts are distinguishable.

## Manifest schema

- [x] Manifest schema version exists.
- [x] Running, complete, and failed manifests carry it.
- [x] Manifest round-trip tests pass.
- [x] Manifest schema is independent of simulator version.

## Documentation

- [x] Every version field has one documented responsibility.
- [x] Acceptance documentation records SIM-1.2.1.
- [x] README examples are current.

## Verification

- [x] All backend tests pass.
- [x] Frontend lint passes.
- [x] Frontend build passes.
- [x] `git diff --check` passes.
- [x] No direct `useEffect` exists outside `useMountEffect`.
- [x] No tracked Python cache files exist.
- [x] No broker/order path is added.
- [x] Simulator remains offline and deterministic.
- [x] Intraday realized variance remains unimplemented.

## Acceptance evidence

- Starting commit: `5c3e6b3d32982b9fd36580f65f56e51a9c9a0535`.
- Simulator identity: `sim-1.2`; market, run, and manifest schemas: version 2; path generator: version 2.
- Active market: `config/simulation/nifty-synthetic-market-v2.yaml` with market ID `nifty-synthetic-market-v2`.
- Backend: `289 passed` with `UV_CACHE_DIR=/tmp/uv-cache uv run pytest`.
- Strategy validation: valid with configuration hash `sha256:0030bd06406afbbcbe7334a034c778b417c3a2d69114459e8b12a35247fbbb4d`.
- CLI verification: run `sim-2559e7609598ae0a6dd5`; market hash `sha256:5df8eed675737dab2aaf983564a229b9657f2f80ab23a75b620b8ed807ef1309`; run-config hash `sha256:2559e7609598ae0a6dd5eeb00c01627a64e944f9171df99f066d2f158630763b`.
- Cross-artifact regression: CLI, manifest, run config, market config, and path config versions agree; persisted market and run payload hashes reproduce their manifest identities.
- Frontend: `npm run lint` passed and `npm run build` passed. Vite reported only its existing large-chunk advisory.
- Hygiene: `git diff --check` passed; tracked cache/generated-artifact scan was empty; direct `useEffect` appears only in `frontend/src/shared/hooks/useMountEffect.ts`; no stale active-market filename references remain.
- Scope: no pricing, hedge, risk, path, fill, accounting, broker, or order-placement behavior changed. The simulator remains offline and deterministic, and intraday realized variance remains unimplemented.

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
SIM-1.1: COMPLETE
SIM-1.2: COMPLETE
SIM-1.2.1 VERSION IDENTITY: COMPLETE
Merge recommendation: APPROVED
Ready for DATA-1: YES
```

---

# 9. Verification commands

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Validate strategy:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.validate_strategy_config   --config ../config/strategies/nifty-long-gamma-v1.yaml
```

Run one policy with the active market config:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m app.cli.run_gamma_simulation   --strategy-config ../config/strategies/nifty-long-gamma-v1.yaml   --market-config ../config/simulation/nifty-synthetic-market-v2.yaml   --path-generator gbm   --seed 17   --policy constant_band
```

Inspect:

```text
manifest.json
run-config.json
market-config.json
CLI JSON
```

Verify all version identities.

Frontend regression:

```bash
cd ../frontend
npm run lint
npm run build
```

Repository hygiene:

```bash
cd ..
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
grep -R "useEffect" frontend/src   --exclude="useMountEffect.ts"
```

---

# 10. Suggested commit sequence

```text
1. Bump simulator and configuration schema versions
2. Add manifest schema version and validation
3. Update active config identity and all references
4. Add version-identity and artifact-consistency tests
5. Update docs and acceptance record
6. Run full verification
```

---

# 11. Codex completion report

Report:

1. Starting SHA.
2. Ending SHA.
3. Commits created.
4. Files added.
5. Files modified.
6. Files removed or renamed.
7. Final simulator version.
8. Final market schema version.
9. Final run schema version.
10. Final manifest schema version.
11. Active market config filename and market ID.
12. Legacy-schema rejection behavior.
13. Run-ID collision prevention.
14. Cross-artifact version consistency.
15. Backend test count and result.
16. CLI verification output.
17. Frontend lint result.
18. Frontend build result.
19. `git diff --check` result.
20. Direct `useEffect` scan result.
21. Known limitations.
22. Confirmation that no behavior beyond identity/version plumbing changed.
23. Confirmation that no broker/order path was added.
24. Confirmation that the simulator remains offline and deterministic.
25. Confirmation that intraday realized variance remains unimplemented.

Use this status only after all criteria pass:

```text
STRAT-1: COMPLETE
SIM-1: COMPLETE
SIM-1.1: COMPLETE
SIM-1.2: COMPLETE
SIM-1.2.1 VERSION IDENTITY: COMPLETE
Merge recommendation: APPROVED
Ready for DATA-1: YES
```
