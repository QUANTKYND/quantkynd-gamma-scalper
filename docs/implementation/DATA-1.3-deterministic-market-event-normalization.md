# DATA-1.3 Deterministic Market-Event Normalization — Implementation Evidence

## Status

Implementation complete; acceptance evidence recorded; independent review pending.

This evidence does not accept or merge DATA-1.3. The feature branch remains paper-only and must stop after push.

## Provenance

- Branch: `feature/deterministic-market-event-normalization`
- Original baseline: `b2bb70ad6d8156f060c82c819f7c20335eef1f12`
- Approved corrected checkpoint: `c323d49a5b12bb36daeeb19a0068acf1fbf46c76`
- Post-checkpoint starting SHA: `c323d49a5b12bb36daeeb19a0068acf1fbf46c76`
- Completion implementation SHA: `6fb7980` (`test(data): add deterministic normalization fixtures and CLIs`)
- Evidence snapshot SHA: `a27c27c` (`docs(data): record DATA-1.3 review-pending evidence`)

Implementation commits from the original baseline:

```text
b0daaf4 docs(data): authorize deterministic market normalization
0c34015 build(data): own Upstox V3 protobuf schema
3f194b1 feat(data): define market normalization contracts
8cca678 feat(data): add market subject resolution boundary
2ecb3a5 feat(data): decode Upstox V3 market frames
6f15598 feat(data): normalize Upstox V3 market observations
f74d9c7 test(data): prove normalization boundary invariants
a4b75e7 docs(data): authorize checkpoint corrections
36d17f7 fix(data): correct normalization checkpoint contracts
fb5832f fix(data): harden protobuf ownership verification
c323d49 test(data): prove corrected normalization checkpoint
1f45343 feat(data): complete normalization and lifecycle contracts
6fb7980 test(data): add deterministic normalization fixtures and CLIs
```

## Implemented contracts

The slice owns immutable raw frame identity, strict live/historical availability rules, exact caller-supplied market and knowledge cutoffs, bounded Upstox V3 decoding, provider-neutral quote/status observations, deterministic partial results, and full/adopted hash boundaries. Direct quote construction enforces signed-64-bit quantities, safe-integer open interest, bounded and reconciled depth, selected-union/request-mode consistency, and controlled sorted path tuples.

`CatalogueMarketSubjectResolver` processes sorted unique keys in one unit of work. The PostgreSQL factory always selects read-only repeatable-read and never commits. It distinguishes unknown, stale, and ambiguous provider mapping outcomes; loads the exact version and immutable identity; preserves actual mapping provenance and exact UTC caller cutoffs; and propagates unexpected infrastructure/integrity failures.

Connection and subscription lifecycle models use immutable raw/normalized events, closed transition sets, deterministic identities, strict time/source-order rules, absent provider sequences, sorted unique subscription-key digests, and controlled redacted failures. Reconnect requires a new non-empty session and source-order scope. These contracts and CLIs remain offline-only.

Deferred declarations are fixed per selected feed union. Frame declarations are the sorted union across decoded primary entries. Failed subjects retain the selected union, declaration, reliably present nested-message paths, and structural depth count without evaluating deferred values.

## Proto and dependency ownership

- Schema: official Upstox Market Data Feed V3, vendored as `MarketDataFeed.proto`.
- Proto SHA-256: `ded335a0c7d2054011c2c0e06f276007a3186d1e212268d85d665788e42916c4`.
- Runtime: `protobuf 7.35.1`, declared range `>=7.35,<8`.
- Generator: `grpcio-tools 1.82.1`, verification/regeneration only.
- Descriptor, generated Python, stub, package, root message, runtime, and ownership manifest are verified locally.
- No dependency was added post-checkpoint; the existing protobuf dependency is owned by DATA-1.3.

## Deterministic fixture inventory

All binaries are synthetic, generated from vendored types, and paired with deterministic capture manifests. Full hashes live in `backend/tests/fixtures/upstox/market_feed_v3/inventory.json`.

| Binary | Bytes | SHA-256 |
|---|---:|---|
| `all-adopted-zero-values.bin` | 35 | `9b65ac848ca4ab1725fad86a84cc43fa071bab583b637f3ec61d6bc473965848` |
| `all-deferred-fields-populated.bin` | 332 | `3e5b9efb10f90eaf1ddb1e61579696c99de101dc980ab62a82af2a7314ff4c1c` |
| `changed-deferred-fields.bin` | 332 | `f5f9d8bb1fd0898e17671f490e6dbb2961e279b4d057f299c5f5d4ce3463cdac` |
| `mixed-valid-and-unknown-provider-key.bin` | 111 | `eedfe902d1b9fe9404b4a00072dcafa40f5848673d6ff0798e88a58ad2cc1b3a` |
| `multi-feed-map-order-a.bin` | 110 | `4cfeeca0edeffbdad709b4ab30b91e09aeb537407784540ae6de9bc27b84a5b0` |
| `multi-feed-map-order-b.bin` | 110 | `db4e1457dd44c5044819f2522d61b6cf05431ef09963cf5a333f6b63d49ae2c5` |
| `multiple-segment-market-info.bin` | 35 | `94060307784f0974d1644a02586cc03a0e655f70ce7c27b84aa3ffcec54062d8` |
| `nifty-future-live-market-ff-d5.bin` | 101 | `18ed5f76af32e27703641a5d31e2da2d3141f0c81eac672f8237ed4cd136ebfb` |
| `nifty-index-direct-ltpc.bin` | 62 | `a99610a3ef804be69aa0615b4eef069982a75ae844c3e2805e6a90cb4d1d9372` |
| `nifty-index-initial-index-ff.bin` | 66 | `7bf6f2198184b8ce52ba3a541cf5287d8a9292dceebaf3f89780c5382dbb3ec8` |
| `nifty-option-first-level-with-greeks.bin` | 105 | `f628e4efd9c4fd484b72afc1736998b0d2a90cdee4e15e86e8e3b05116b88eca` |
| `nifty-option-live-market-ff-d30.bin` | 802 | `99ccac6ffb0a3cb9946107bfe0811f7df415e82e0a8413d683a8eaf6291cc52a` |
| `nifty-option-live-market-ff-d5.bin` | 201 | `d078d3787ab6e465ba531284a6cf2b8f7b8e33366f3033a1fbed249203f0c41c` |
| `secondary-payload-coexistence.bin` | 76 | `bd8968880c055d90a215a67ebcffd6f1357386a2d59da8d2d372354bab68a0c3` |
| `subject-union-mismatch.bin` | 63 | `60589c2a0a75e448ec949cc9afd32a4fabba34b0d2cd1f55a929f5da2d02f33c` |
| `unknown-market-status.bin` | 23 | `ab49a701d3fcce01aad3e565cd0f97470cefa80f9589b94127348e3eb5edaedc` |
| `unknown-wire-field.bin` | 65 | `23e0abef9e680aa13fc6731b9913422d159b3a25afc288271011a2aab01347c5` |

The corpus also contains a deterministic DATA-1 subject manifest and connection, subscription, reconnect, and invalid-transition lifecycle fixtures. Regeneration and verification reported `verified 36 deterministic fixture artifacts` with no drift.

## Determinism and hash proofs

- Every binary/capture sidecar replay reproduced raw identity, ordered normalized IDs, canonical result JSON, full-result hash, and adopted-semantics hash.
- `PYTHONHASHSEED=1` and `999` produced byte-identical frame and lifecycle CLI output.
- Reversed protobuf map-entry wire order produced different raw bytes but identical ordered adopted semantics.
- Deferred-only Greeks, IV, OHLC, ATP, TBQ, TSQ, and deeper-depth changes changed frame and full-result hashes while preserving adopted values and adopted-semantics hash.
- An adopted LTP change changed the adopted-semantics hash.
- Capture identity/source-order change changed raw and normalized IDs plus full-result hash while preserving adopted-semantics hash.
- Unknown wire fields affect raw/full provenance only.

## CLI evidence

`app.cli.normalize_market_event_fixture` verifies owned schema artifacts, capture hash, capture manifest, and static subject manifest before normalization. It emits canonical JSON only and no raw bytes. Tested exit codes are `0` match, `1` result mismatch, `2` manifest/configuration error, `3` schema/frame hash error, and `4` raw identity conflict.

`app.cli.normalize_market_lifecycle_fixture` deterministically covers connection, subscription, reconnect/new-session, sorted key digest, redacted failure, and invalid transitions. Neither CLI requires database, restore URL, provider token, Redis, or network.

## Acceptance results

- Focused no-infrastructure normalization/fixture/LIVE-RV suite: `166 passed`, zero skipped.
- Complete market-data test directory: `179 passed`, zero skipped.
- Existing LIVE-RV suite: `26 passed`, unchanged public payloads and files.
- Repository resolver integration: `1 passed`, zero skipped, covering all required resolver scenarios.
- Complete backend: `584 passed`, zero skipped.
- PostgreSQL server: `17.10`; `psql`: `17.10`; database: `quantkynd_test`.
- Alembic heads/current: `20260804_03`; check: `No new upgrade operations detected`.
- Proto verification: passed.
- Fixture regeneration/verification: passed, byte-identical.
- `uv lock --check`: passed.
- Frontend `pnpm lint`: passed.
- Frontend `pnpm build`: passed with the pre-existing bundle-size warning only.
- Python compilation and `git diff --check`: passed.

## Security and hygiene

Tracked source and fixtures contain no provider token, authorized WebSocket URL, account/user identifier, complete proprietary capture, raw-frame logging, pickle/eval, runtime schema download, normalization shell execution, new migration, or order route. The 17 deliberate `.bin` files are enumerated above; the largest is 802 bytes. Generated cache/build artifacts are excluded from the change.

## Explicit limitations

DATA-1.3 does not persist raw frames or normalized/lifecycle events; create migration `20260804_04`; wire lifecycle events into LIVE-RV; add live provider subscription behavior; infer or enforce provider sequence; implement quality/freshness policy, latest-state or chain reconstruction, analytics, Redis, retention, replay storage, trades, options surfaces, strategy decisions, paper orders, or live-capital execution. Independent review is still required before acceptance.
