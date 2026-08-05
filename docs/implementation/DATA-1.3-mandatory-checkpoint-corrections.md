# Codex Task — DATA-1.3 Mandatory Checkpoint Corrections

## Status

The mandatory DATA-1.3 checkpoint at:

```text
feature/deterministic-market-event-normalization
f74d9c7d09c7480c8d2481603837c6560d72e846
```

has been reviewed.

The checkpoint is **not approved for post-checkpoint implementation yet**.

Continue on the same feature branch. Correct the issues in this task, commit and push them, rerun the focused checkpoint suite, return the correction evidence, and stop again for review.

Do not begin:

- lifecycle fixture completion;
- the offline CLI;
- the repository-backed resolver completion beyond what is required to prove this checkpoint contract;
- the complete binary fixture corpus;
- full documentation completion;
- final acceptance evidence;
- merge work.

Keep milestone status:

```text
implementation in progress; mandatory checkpoint corrections pending
```

Do not mark DATA-1.3 accepted.

---

## 1. Baseline

Reviewed checkpoint SHA:

```text
f74d9c7d09c7480c8d2481603837c6560d72e846
```

Before editing:

```bash
git switch feature/deterministic-market-event-normalization
git pull --ff-only
git branch --show-current
git rev-parse HEAD
git status --short
git merge-base --is-ancestor \
  b2bb70ad6d8156f060c82c819f7c20335eef1f12 \
  HEAD
```

Required:

- branch is exactly `feature/deterministic-market-event-normalization`;
- `HEAD` is exactly the reviewed checkpoint SHA;
- required ancestor check exits `0`;
- worktree is clean.

Record the correction starting SHA. Do not reset, rebase, or merge.

---

# 2. Make resolved provider provenance self-validating

## Current problem

`ResolvedMarketSubjectV1` carries:

```text
provider_mapping_id
provider_contract_key
contract_version_id
mapping interval fields
```

but it does not carry the actual immutable `ProviderContractMapping`.

Consequently, a resolver can supply an arbitrary:

- mapping ID;
- provider;
- provider key;
- version binding;
- mapping interval;
- knowledge-time state.

The domain contract currently validates the contract version but cannot prove that the provider mapping actually references that version and key.

## Required correction

Add the immutable DATA-1 mapping value to the resolved subject:

```text
provider_mapping: ProviderContractMapping
```

The resolved subject must derive or validate:

```text
provider_mapping_id == provider_mapping.mapping_id
provider == provider_mapping.provider
provider_contract_key == provider_mapping.provider_contract_key
contract_version_id == provider_mapping.contract_version_id
```

It must also prove:

```text
provider_mapping.effective_at(
    resolution_market_as_of,
    resolution_known_as_of
)
```

Remove duplicated mapping interval fields unless there is a documented need to retain them. If retained, require exact equality with the mapping value.

For the contract version:

- require `contract_version_id == contract_version.version_id`;
- require economic identity and version subject IDs to match;
- require `contract_version.effective_at(market_as_of, known_as_of)`;
- if duplicated version interval fields remain, require exact equality with the actual version.

Validate all required provider/key/ID strings as non-empty.

The static resolver fixtures must construct a real deterministic `ProviderContractMapping`, not an arbitrary string mapping ID.

Add tests proving rejection of:

- wrong provider;
- wrong provider key;
- wrong mapping ID;
- mapping bound to another version;
- stale mapping by market time;
- mapping not yet known;
- mapping already superseded at `known_as_of`;
- duplicated interval metadata disagreeing with the mapping/version;
- wrong economic identity or subject kind.

---

# 3. Strengthen quote and status domain invariants

## Quote contracts

`QuoteObservationV1` and its subclasses must validate their complete provenance.

Require:

```text
event.provider == subject.provider
event.provider_contract_key == subject.provider_contract_key
event.provider_mapping_id == subject.provider_mapping.mapping_id
event.contract_version_id == subject.contract_version.version_id
event.economic_subject_id == subject.economic_subject_id
```

Require exact event type and class/kind compatibility:

```text
UnderlyingQuoteObservationV1
    subject kind = underlying
    event_type = underlying_quote_observation

FuturesQuoteObservationV1
    subject kind = future
    event_type = futures_quote_observation

OptionQuoteObservationV1
    subject kind = option
    event_type = option_quote_observation
```

Require:

```text
feed_response_type=initial_feed -> is_snapshot=True
feed_response_type=live_feed    -> is_snapshot=False
```

Quote events must reject `market_info`.

Require runtime invariants:

```text
source_order is a non-boolean non-negative integer
source_order_scope_id is non-empty
provider_sequence is exactly None
supersedes_event_id is exactly None
provider and provider key/IDs are non-empty
```

Do not rely on Python type annotations alone.

## Status contracts

`ProviderMarketSegmentStatusObservationV1` must validate:

- identity subject ID equals the deterministic provider+segment status subject;
- identity event type is exact;
- source order is non-negative and scope is non-empty;
- `available_at >= received_at` when receipt exists;
- `recorded_at >= available_at`;
- known numeric values have the correct official name and `status_is_known=True`;
- unknown numeric values use `provider_status_name="UNKNOWN"` and `status_is_known=False`;
- provider, segment, and normalizer/version fields are valid.

Add direct-construction hostile tests. Do not test only the happy normalizer path.

---

# 4. Correct capture-basis time invariants

## Raw frame

`RawCaptureBasis.RECORDED_WITH_ORIGINAL_RECEIPT` must require:

```text
received_at is not None
available_at == received_at
```

This mode claims original receipt metadata; it cannot exist without a receipt time.

Keep:

```text
LIVE_RECEIVED
    received_at required
    available_at == received_at

HISTORICAL_IMPORT
    received_at must be None
```

Decide and freeze whether historical import requires deterministic `source_file_id` plus `source_record_id`.

Recommended checkpoint rule:

```text
historical_import requires both source_file_id and source_record_id
```

because a replayed file observation must have an explicit stable source identity. If this differs from the approved design, stop and report before implementing it.

## Normalized event time

Require:

```text
availability_basis=received
    received_at is required
    available_at == received_at

availability_basis=historical_import
    received_at must be None
```

Add tests for every capture/availability basis, including direct invalid construction.

---

# 5. Fix frame-result reconciliation

## Current problem

The service currently returns:

```text
decoded_entry_count = 1
```

for structural frame failures, including malformed Protobuf where no feed/status entry was decoded.

For duplicate normalized identity, it also returns `1` even when multiple feed entries were decoded.

`FrameNormalizationResultV1` currently forces:

```text
decoded_entry_count =
accepted_event_count + number_of_failure_objects
```

That cannot correctly model a frame-level failure affecting zero or multiple decoded entries.

## Required model

Separate frame failures from entry failures.

A suitable contract is:

```text
frame_failure: NormalizationFailureV1 | None
entry_failures: tuple[NormalizationFailureV1, ...]

decoded_entry_count
accepted_entry_count
failed_entry_count
```

Or another equally explicit model.

Required semantics:

### Protobuf/structural failure before entry decoding

```text
decoded_entry_count = 0
accepted_entry_count = 0
failed_entry_count = 0
frame_failure is present
```

### Valid frame with subject failures

```text
decoded_entry_count =
accepted_entry_count + failed_entry_count

frame_failure is None
```

### Duplicate normalized identity after N feed entries decode

The result must preserve:

```text
decoded_entry_count = N
```

and represent the structural whole-result failure without falsely claiming one decoded entry.

### Status frames

Reconcile against decoded segment entries.

Stable counts must not depend on how many diagnostic reason objects are attached to one failed entry.

Update hashes and canonical serialization so frame failure and entry failures are explicit and deterministic.

Add tests for:

- malformed Protobuf;
- missing provider timestamp;
- empty primary payload;
- too many feeds;
- two-feed duplicate normalized identity;
- partial two-feed normalization;
- complete market-info frame;
- structural market-info failure.

---

# 6. Remove O(n²) subject lookup

## Current problem

For each decoded provider key, normalization calls:

```text
failure_for(key)
subject_for(key)
```

and both methods linearly scan tuples.

With up to 5,000 feeds, this becomes O(n²), contrary to the approved bounded complexity.

## Required correction

`SubjectResolutionBatch` must create immutable indexed lookup structures once, or expose deterministic mappings built in `__post_init__`.

Requirements:

- O(1) lookup per provider key after construction;
- preserve immutable public behavior;
- resolved and failed keys remain unique and sorted;
- no key may be both resolved and failed;
- validate that the resolver result contains no undeclared extra key when the service compares it with the request;
- every requested key must reconcile to exactly one resolved subject or one failure;
- deterministic ordering remains tuple-based for serialization.

The service must validate the resolver response against the exact sorted requested-key set.

Add a test with 5,000 requested keys and an instrumented resolver/batch proving bounded lookup behavior. Do not use a fragile wall-clock benchmark as the only proof.

---

# 7. Enforce request-mode-specific depth limits

The official Upstox documentation defines:

```text
full      -> 5 market-depth levels
full_d30  -> 30 market-depth levels
```

The Proto response enum uses:

```text
full_d5
full_d30
```

Current code allows up to 30 levels for both modes.

Required:

```text
full_d5  -> provider depth count <= 5
full_d30 -> provider depth count <= 30
```

Use a stable subject failure such as:

```text
request_mode_depth_mismatch
```

for 6–30 levels received under `full_d5`.

Keep:

```text
depth_limit_exceeded
```

for more than 30 levels.

Add tests:

- full_d5 with 0, 1, and 5 levels succeeds;
- full_d5 with 6 levels fails;
- full_d30 with 30 levels succeeds;
- full_d30 with 31 levels fails;
- deeper unadopted values are not semantically validated when count is within the mode limit.

---

# 8. Correct status-segment limit failure

Current code uses:

```text
empty_primary_payload
```

when status-segment count exceeds the configured limit.

Introduce and use:

```text
too_many_status_segments
```

The reason must remain distinct from an actually empty primary payload.

Add boundary tests for 256 and 257 segments.

---

# 9. Make canonical serialization explicitly deterministic

The generic payload converter currently treats:

```text
tuple
list
set
frozenset
```

the same and iterates sets directly.

Set iteration depends on hash order.

Required:

- tuples/lists preserve their declared order;
- sets/frozensets are either rejected from canonical normalization payloads or converted through a deterministic canonical sort;
- no hash-seed-dependent container traversal is allowed.

Add a subprocess test with at least:

```text
PYTHONHASHSEED=1
PYTHONHASHSEED=999
```

covering the canonical helper directly.

The post-checkpoint CLI determinism tests are still required later; this correction secures the shared serializer now.

---

# 10. Harden schema/generation verification

The schema verifier must also validate the frozen manifest ownership values:

```text
schema_id
source_url
downloaded_at format
protobuf_runtime_range
protobuf_runtime_resolved
generator_package
generator_version
```

The generator must fail clearly when the active generation tool is not:

```text
grpcio-tools==1.82.1
```

or when the runtime is outside:

```text
protobuf>=7.35,<8
```

It is acceptable for generated byte drift to remain the final reproducibility check, but ownership/version drift must not silently pass.

Add tests for manifest ownership-field drift.

---

# 11. Failure contract

Add an explicit scope enum:

```text
frame
subject
segment
connection_lifecycle
subscription_lifecycle
```

`NormalizationFailureV1` must carry:

```text
scope
reason_code
provider_contract_key | None
segment | None
field_paths
safe_detail_code | None
```

For this checkpoint:

- frame failures use `scope=frame`;
- quote-entry failures use `scope=subject`;
- market-status entry failures use `scope=segment`.

Require sorted unique field paths.

Do not include:

- raw payload;
- exception repr;
- token;
- URL;
- traceback;
- uncontrolled provider text.

This correction avoids inferring failure scope from which optional field happens to be populated.

---

# 12. Tests and verification

Run from `backend`:

```bash
env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    -u UPSTOX_ACCESS_TOKEN \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run python -m compileall -q app tests
```

```bash
env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    -u UPSTOX_ACCESS_TOKEN \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run pytest -ra \
      tests/market_data/normalization \
      tests/market_data/upstox \
      <all existing LIVE-RV test paths>
```

Also run:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python tools/verify_upstox_market_feed_v3_schema.py

UV_CACHE_DIR=/tmp/uv-cache \
uv run --with grpcio-tools==1.82.1 \
python tools/generate_upstox_market_feed_v3.py

UV_CACHE_DIR=/tmp/uv-cache uv lock --check
UV_CACHE_DIR=/tmp/uv-cache uv run alembic heads
git diff --check
git status --short
```

Required:

- focused tests pass;
- zero focused skips;
- LIVE-RV tests unchanged;
- Alembic head remains `20260804_03`;
- no database, token, Redis, or network required;
- worktree clean after commits.

---

# 13. Suggested correction commits

1. `fix(data): validate resolved market provenance`
2. `fix(data): enforce normalization event invariants`
3. `fix(data): correct market frame result reconciliation`
4. `perf(data): index subject resolution batches`
5. `fix(data): enforce Upstox depth mode limits`
6. `fix(data): harden deterministic schema serialization`
7. `test(data): prove corrected normalization checkpoint`

Keep commits reviewable. Do not squash the existing checkpoint history.

---

# 14. Required response

Return:

- branch;
- correction starting SHA;
- corrected checkpoint SHA;
- pushed branch SHA;
- commits;
- exact changed-file list;
- mapping/version provenance validation summary;
- quote/status invariant summary;
- capture-basis time rules;
- new result-reconciliation model with examples;
- 5,000-key lookup proof;
- full_d5/full_d30 depth results;
- schema/generation verification results;
- canonical hash-seed result;
- focused test count and skips;
- LIVE-RV test result;
- Alembic head;
- worktree status;
- any deviation from this task.

Push the corrected branch and stop for checkpoint re-review. Do not proceed to post-checkpoint completion.
