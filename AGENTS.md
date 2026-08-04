# AGENTS.md

This repository is governed by the documentation in `docs/`.

## Mandatory reading order

Before changing code, read:

1. `docs/README.md`
2. `docs/conventions.md`
3. `docs/design.md`
4. `docs/data-models.md`
5. `docs/api.md`
6. `docs/environment.md`
7. `docs/dependencies.md`
8. `docs/testing.md`
9. The relevant plan under `docs/plan/`

For market-facing or stateful work, also read:

- `docs/performance.md`
- `docs/observability.md`
- `docs/security.md`
- `docs/plan/acceptance-gates.md`

## Working rules

- Identify the active milestone and its acceptance gate before implementation.
- Do not broaden scope beyond the active milestone without updating the plan first.
- Update documentation in the same change as any architecture, dependency, data-model, API, convention, environment, or operational change.
- Do not add a dependency without updating `docs/dependencies.md` with purpose, owner, phase, and removal criteria.
- Do not add or change an API procedure without updating `docs/api.md`.
- Do not add or change a durable model without updating `docs/data-models.md` and the migration plan.
- Preserve deterministic research runs, immutable manifests, dataset identity, strategy configuration, and source commit provenance.
- All market decisions must be reconstructable from persisted inputs, state, policy version, risk result, intents, orders, fills, and marks.
- The MVP is paper-only. No live-capital execution path may be introduced before the paper-trading acceptance gate is passed and explicitly approved.

## Frontend rules

- Direct `useEffect` usage is banned in app and feature code.
- Use the five approved replacements in `docs/conventions.md`.
- The only approved mount-only wrapper is `useMountEffect` in shared infrastructure.
- Data fetching uses RTK Query.
- Derive render state inline from props, query results, and store selectors.
- User-driven behavior belongs in event handlers.
- Reset component state with `key` when identity changes.
- Keep high-frequency market events out of local component state.

## Comment rule

- New code carries no explanatory comments.
- Names, types, schemas, and small functions explain behavior.
- Prose belongs in `docs/`.
- Existing comments stay unless the surrounding code is removed.
- Do not churn existing comments merely to satisfy this rule.
- `biome-ignore` directives and generated-file headers are exempt.

## Completion requirements

A change is not complete until:

- Relevant tests pass.
- Static checks pass.
- API and data contracts remain explicit.
- Failure behavior is covered.
- Documentation is updated.
- Generated artifacts and caches are not committed.
- `git diff --check` passes.
