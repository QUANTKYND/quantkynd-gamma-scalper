# Codex Implementation Authorization — DATA-1.3 Deterministic Market-Event Normalization

## Status

DATA-1.3 design is **approved with the decisions frozen in this document**.

Implementation is authorized on:

```text
feature/deterministic-market-event-normalization
```

Do not reopen approved semantics during implementation. Stop and report before deviating materially from this task.

DATA-1.3 remains implementation/review pending until:

- the implementation is committed and pushed;
- the required checkpoint is reviewed;
- the complete acceptance suite passes;
- independent final review approves the branch.

Do not merge into `master`.


## 1. Required baseline

Required exact baseline:

```text
master
b2bb70ad6d8156f060c82c819f7c20335eef1f12
docs(data): accept DATA-1.2 catalogue ingestion
```

Before editing:

```bash
git switch feature/deterministic-market-event-normalization
git branch --show-current
git rev-parse HEAD
git status --short
git merge-base --is-ancestor \
  b2bb70ad6d8156f060c82c819f7c20335eef1f12 \
  HEAD
git log --oneline --decorate -8
```

Required:

- branch is exactly `feature/deterministic-market-event-normalization`;
- `HEAD` is exactly `b2bb70ad6d8156f060c82c819f7c20335eef1f12`;
- ancestry exits `0`;
- worktree is clean;
- no implementation commits already exist;
- no untracked task/design files exist in the repository.

If any condition fails, stop and report. Do not reset, rebase, cherry-pick, or repair without approval.

Record the verified starting SHA in implementation evidence.


## 2. Governing repository rules

Read and follow:

1. `AGENTS.md`
2. `docs/standards/milestone-requirement-standard.md`
3. `docs/conventions.md`
4. `docs/design.md`
5. `docs/data-models.md`
6. `docs/dependencies.md`
7. `docs/testing.md`
8. `docs/security.md`
9. `docs/observability.md`
10. `docs/plan/options-market-infrastructure.md`
11. `docs/plan/acceptance-gates.md`
12. DATA-1.0, DATA-1.1, and DATA-1.2 implementation evidence.

Preserve the dependency direction:

```text
capture / fixture input
        ↓
bounded Upstox V3 decoder
        ↓
Upstox normalization adapter
        ↓
provider-neutral immutable observations
        ↓
future quality and persistence milestones
```

Domain normalization modules must not import:

- Upstox SDK;
- generated Protobuf classes;
- SQLAlchemy;
- Alembic;
- asyncpg;
- FastAPI;
- Redis;
- WebSocket clients.


## 3. Fixed milestone scope

Implement:

- immutable raw market-frame envelopes;
- immutable raw connection/subscription lifecycle inputs;
- deterministic raw-capture identities;
- vendored official Upstox V3 Proto and generated Python types;
- bounded deterministic Protobuf decoding;
- provider-neutral quote observations for:
  - Nifty 50 underlying;
  - accepted Nifty futures;
  - accepted Nifty options;
- exact provider market-segment status observations;
- connection and subscription lifecycle observations;
- persistence-independent subject resolution;
- static fixture subject resolver;
- application adapter around existing DATA-1 repositories;
- deterministic partial frame-normalization results;
- deterministic binary fixtures and manifests;
- an offline read-only normalization CLI;
- documentation and review-pending implementation evidence.

Do not implement:

- event persistence;
- raw-frame persistence;
- Alembic revision `20260804_04`;
- Redis;
- live subscription expansion;
- changes to the existing LIVE-RV stream path;
- sequence-gap or out-of-order policy;
- quality/freshness policy;
- latest-state reconstruction;
- chain reconstruction;
- trade events;
- IV, Greeks, surface analytics;
- strategy, hedging, backtesting, paper/live execution;
- frontend features.

Alembic head must remain:

```text
20260804_03
```


## 4. Approved design decisions

These decisions are final for normalization schema version `1`.

### 4.1 Snapshot decision

Use only the decoded wire enum:

```text
initial_feed -> is_snapshot = true
live_feed    -> is_snapshot = false
market_info  -> market-status normalization
```

Never infer snapshot status from WebSocket message position.

### 4.2 Subject-resolution time

The application supplies:

```text
market_as_of
known_as_of
```

explicitly.

Do not derive either cutoff from:

- `LTPC.ltt`;
- `FeedResponse.currentTs`;
- receipt time;
- normalization time;
- current wall clock.

### 4.3 Raw identity

Raw identity excludes the frame hash.

```text
same capture identity + same immutable content -> exact duplicate
same capture identity + different content      -> identity conflict
same bytes + different capture identity        -> different observation
```

### 4.4 Partial normalization

A structurally valid frame may return valid events plus explicit per-subject failures.

Whole-frame failure is reserved for frame structural errors.

### 4.5 Proto3 scalar presence

Freeze:

```text
presence_semantics = proto3_parent_implied_v1
```

- present parent + scalar zero -> reported zero;
- absent nested parent -> `None`;
- timestamp zero -> unavailable;
- no truthiness fallback.

### 4.6 Quantity semantics

Use unit-neutral names:

```text
bid_size
ask_size
last_size
reported_volume
open_interest
```

Freeze:

```text
quantity_basis = upstox_reported_quantity_v1
```

Do not call these lots, contracts, shares, or underlying units. Do not divide by catalogue lot size.

### 4.7 Open interest

Upstox OI is a `double`.

Accept only values that are:

- finite;
- non-negative;
- mathematically integral;
- no greater than `2**53`;
- within signed int64.

Convert accepted OI to Python `int`.

### 4.8 Deferred Proto fields

Greeks, IV, OHLC, ATP, TBQ, TSQ, and depth after level one:

- remain in exact raw bytes;
- affect frame hash and full provenance hash;
- do not enter normalized DATA-1.3 event fields;
- do not affect DATA-1.3 semantic normalization hash;
- are not semantically validated.

Describe the hash as the **DATA-1.3 adopted-semantics hash**, not complete provider-frame economic meaning.

### 4.9 Secondary payloads

`FeedResponse.type` determines the adopted primary payload.

Do not reject only because the secondary payload also exists:

```text
type=market_info:
    adopt marketInfo
    record non-empty feeds as present secondary payload

type=initial_feed/live_feed:
    adopt feeds
    record non-empty marketInfo as present secondary payload
```

Still fail when the required primary payload is missing or empty.

### 4.10 Proto ownership

Vendor and directly own the official Proto and generated code. Do not use SDK dict conversion as DATA-1.3’s authoritative decoder.

### 4.11 Lifecycle depth

Implement lifecycle contracts, validation, deterministic fixture normalization, and tests only. Do not wire lifecycle events into the existing live streamer.


## 5. Official Upstox Proto ownership

Official source:

```text
https://assets.upstox.com/feed/market-data-feed/v3/MarketDataFeed.proto
```

Verified source properties:

```text
byte count: 2070
SHA-256: ded335a0c7d2054011c2c0e06f276007a3186d1e212268d85d665788e42916c4
package: com.upstox.marketdatafeederv3udapi.rpc.proto
root: FeedResponse
```

Commit:

```text
backend/app/market_data/upstox/proto/MarketDataFeed.proto
backend/app/market_data/upstox/proto/MarketDataFeed_pb2.py
backend/app/market_data/upstox/proto/MarketDataFeed_pb2.pyi
backend/app/market_data/upstox/proto/schema-manifest.json
backend/tools/generate_upstox_market_feed_v3.py
backend/tools/verify_upstox_market_feed_v3_schema.py
```

Runtime dependency:

```toml
protobuf>=7.35,<8
```

Expected locked runtime at implementation start:

```text
protobuf 7.35.1
```

Use stable isolated generation tooling:

```text
grpcio-tools==1.82.1
```

Do not use `1.83.0`; it is not a stable release at this task’s approval date.

The generator must:

1. verify the official Proto SHA before generation;
2. generate into a temporary directory;
3. use deterministic arguments;
4. normalize only necessary generated import paths;
5. compare generated output with committed output;
6. record hashes in the schema manifest;
7. fail if generated files drift;
8. never download the schema at runtime.

Manifest fields:

```text
schema_id
source_url
downloaded_at
proto_byte_count
proto_sha256
package
root_message
protobuf_runtime_range
protobuf_runtime_resolved
generator_package
generator_version
generated_python_sha256
generated_stub_sha256
descriptor_sha256
```


## 6. Complete Proto treatment

### Adopted normalized fields

```text
FeedResponse.type
FeedResponse.currentTs
Feed.requestMode

LTPC.ltp
LTPC.ltt
LTPC.ltq
LTPC.cp

Quote.bidQ
Quote.bidP
Quote.askQ
Quote.askP

MarketFullFeed.vtt
MarketFullFeed.oi

FirstLevelWithGreeks.vtt
FirstLevelWithGreeks.oi

MarketInfo.segmentStatus
```

### Structurally inspected

```text
Feed oneof selection
FullFeed oneof selection
FeedResponse.feeds count
MarketInfo.segmentStatus count
MarketLevel.bidAskQuote count
nested-message presence
secondary-payload presence
```

### Intentionally unadopted

```text
OptionGreeks.delta
OptionGreeks.theta
OptionGreeks.gamma
OptionGreeks.vega
OptionGreeks.rho

MarketOHLC.ohlc

OHLC.interval
OHLC.open
OHLC.high
OHLC.low
OHLC.close
OHLC.vol
OHLC.ts

MarketFullFeed.atp
MarketFullFeed.iv
MarketFullFeed.tbq
MarketFullFeed.tsq

FirstLevelWithGreeks.iv

MarketLevel.bidAskQuote[1:]
```

Do not validate unadopted analytic/candle values. For example, a NaN provider IV must not reject an otherwise valid quote.

Expose:

```text
unadopted_schema_paths
present_unadopted_message_paths
unadopted_depth_level_count
secondary_payload_paths_present
```

`unadopted_schema_paths` is a fixed sorted declaration. It does not claim Proto3 scalar presence.

`present_unadopted_message_paths` includes only nested messages with reliable presence detection.

Unknown wire fields are represented by exact frame bytes/hash only.


## 7. Required package layout

Use:

```text
backend/app/market_data/
├── normalization/
│   ├── __init__.py
│   ├── enums.py
│   ├── errors.py
│   ├── identities.py
│   ├── models.py
│   ├── conversions.py
│   ├── ports.py
│   ├── lifecycle.py
│   ├── results.py
│   └── serialization.py
├── upstox/
│   ├── v3_decoder.py
│   ├── v3_normalizer.py
│   ├── v3_schema.py
│   └── proto/
└── existing LIVE-RV files unchanged

backend/app/services/
└── market_frame_normalization_service.py

backend/app/cli/
└── normalize_market_event_fixture.py

backend/tools/
├── generate_upstox_market_feed_v3.py
└── verify_upstox_market_feed_v3_schema.py
```

A materially different layout requires a checkpoint explanation before continuing.


## 8. Raw frame and raw identity contracts

### `RawMarketFrameV1`

Fields:

```text
provider
provider_schema_id
provider_schema_sha256
connection_session_id
source_order_scope_id
source_order
frame_bytes
frame_content_hash
received_at
available_at
recorded_at
capture_basis
source_file_id
source_record_id
```

Capture basis:

```text
live_received
recorded_with_original_receipt
historical_import
```

Invariants:

- provider is `upstox`;
- scope/session/schema strings are non-empty;
- source order is a non-boolean non-negative integer;
- frame is immutable non-empty bytes;
- frame size <= 16 MiB;
- content hash matches exact bytes;
- all supplied times are aware UTC;
- `recorded_at >= available_at`;
- when receipt exists, `available_at >= received_at`;
- `live_received` requires `available_at == received_at`;
- `historical_import` requires `received_at=None`;
- source file and source record IDs are both present or both absent;
- no secret, URL, socket, SDK object, or account identifier.

### `RawMarketFrameIdentityV1`

Identity material:

```text
entity = raw_market_frame
provider
provider_schema_id
connection_session_id
source_order_scope_id
source_order
```

Do not include frame hash.

Expose:

```text
provider_event_id = None
provider_sequence = None
```

Implement pure batch collision validation:

```text
validate_raw_frame_identity_batch(frames)
```

It must detect:

- exact duplicate;
- conflicting identity;
- independent same-content observations.

Do not add cross-frame mutable state to the pure normalizer.


## 9. Subject-resolution boundary

Define:

```text
MarketSubjectResolver.resolve_many(
    provider,
    provider_contract_keys,
    market_as_of,
    known_as_of
) -> SubjectResolutionBatch
```

`ResolvedMarketSubjectV1` contains:

```text
provider
provider_contract_key
provider_mapping_id
contract_version_id
economic_subject_id
instrument_kind
economic_identity
contract_version
mapping_effective_from
mapping_effective_until
version_effective_from
version_effective_until
resolution_market_as_of
resolution_known_as_of
```

Kinds:

```text
underlying
future
option
```

Implement:

1. `StaticSubjectManifestResolver` for fixture CLI;
2. `CatalogueMarketSubjectResolver` as an application/infrastructure adapter over existing DATA-1 repository ports.

The Upstox decoder and normalizer never import repositories or Postgres.

Validate:

- exact provider/key;
- mapping references version;
- version references economic identity;
- kind matches identity type;
- version and mapping are effective at explicit cutoffs;
- ambiguous/stale state fails explicitly.

No cutoff fallback.


## 10. Event-time contract

Define:

```text
NormalizedMarketEventTimeV1
```

Fields:

```text
provider_timestamp
exchange_timestamp
received_at
available_at
recorded_at
availability_basis
```

Rules:

```text
FeedResponse.currentTs -> provider_timestamp
LTPC.ltt               -> last_trade_at
exchange_timestamp     -> None
```

Availability basis:

```text
received
historical_import
```

Requirements:

- `currentTs` positive and valid for feed frames;
- zero/missing `currentTs` is whole-frame failure;
- `ltt=0` -> `None`;
- provider/local clocks need not be ordered;
- `recorded_at >= available_at`;
- no use of `ltt` or `currentTs` as subject-resolution cutoff;
- no wall-clock calls in pure normalization.


## 11. Provider-neutral quote observations

Implement immutable:

```text
UnderlyingQuoteObservationV1
FuturesQuoteObservationV1
OptionQuoteObservationV1
```

Shared provenance:

```text
identity
raw_event_id
provider
provider_contract_key
provider_mapping_id
contract_version_id
economic_subject_id
subject
event_time
source_order_scope_id
source_order
feed_response_type
request_mode
feed_union
is_snapshot
presence_semantics
numeric_basis
quantity_basis
normalization_schema_version
normalizer_implementation_version
provider_sequence
supersedes_event_id
```

Freeze:

```text
normalization_schema_version = 1
normalizer_implementation_version = upstox-v3-normalizer-1
presence_semantics = proto3_parent_implied_v1
numeric_basis = protobuf_double_roundtrip_decimal_v1
quantity_basis = upstox_reported_quantity_v1
provider_sequence = None
supersedes_event_id = None
```

Market fields:

```text
bid_price: Decimal | None
bid_size: int | None
ask_price: Decimal | None
ask_size: int | None
last_price: Decimal | None
last_size: int | None
last_trade_at: datetime | None
previous_close_price: Decimal | None
reported_volume: int | None
open_interest: int | None
provider_depth_levels_present: int
normalized_depth_levels: int
unadopted_depth_level_count: int
unadopted_schema_paths: tuple[str, ...]
present_unadopted_message_paths: tuple[str, ...]
secondary_payload_paths_present: tuple[str, ...]
```

No carry-forward from prior frames.


## 12. Normalized identity and deterministic order

Reuse:

```text
raw_event_id
event_type
subject_id
normalization_schema_version
```

Stable event types:

```text
underlying_quote_observation
futures_quote_observation
option_quote_observation
market_segment_status_observation
provider_connection_lifecycle_observation
provider_subscription_lifecycle_observation
```

Subject IDs:

- underlying/future/option -> DATA-1 economic identity ID;
- status -> stable provider+segment identity;
- connection lifecycle -> connection session ID;
- subscription lifecycle -> stable provider+session+subscription-scope identity.

Fixed event order:

1. connection lifecycle;
2. subscription lifecycle;
3. market status;
4. underlying quote;
5. futures quote;
6. option quote.

Within type, sort by provider key/segment, subject ID, then event ID.

Duplicate normalized identity in one result is a whole-result failure.


## 13. Response-type and secondary-payload rules

### `market_info`

Required primary payload:

```text
marketInfo.segmentStatus non-empty
```

Behavior:

- normalize status map;
- sort segment keys;
- do not normalize feeds;
- non-empty feeds are recorded in `secondary_payload_paths_present`;
- do not reject solely because feeds coexist.

### `initial_feed`

Required primary payload:

```text
feeds non-empty
```

Behavior:

- normalize quote feeds;
- `is_snapshot=true`;
- non-empty market-info status map is recorded as secondary payload;
- do not normalize secondary market-info payload.

### `live_feed`

Required primary payload:

```text
feeds non-empty
```

Behavior:

- normalize quote feeds;
- `is_snapshot=false`;
- non-empty market-info status map is recorded as secondary payload.

Fail whole frame when:

- response type is unsupported/unknown;
- required primary payload is empty;
- provider timestamp invalid;
- frame structurally invalid.

Do not infer response type from payload content.


## 14. Request-mode and union compatibility

Approved matrix:

| Request mode | Union | Subject |
|---|---|---|
| `ltpc` | direct `LTPC` | underlying/future/option |
| `full_d5` | `indexFF` | underlying index |
| `full_d30` | `indexFF` | underlying index |
| `full_d5` | `marketFF` | future/option |
| `full_d30` | `marketFF` | future/option |
| `option_greeks` | `firstLevelWithGreeks` | option |

Everything else fails that subject with:

```text
request_mode_union_mismatch
subject_kind_mismatch
unsupported_feed_union
```

The external subscription string `full` is not normalized here. Preserve Proto response enum `full_d5`.


## 15. Field mapping

### Direct LTPC

```text
ltp -> last_price
ltt -> last_trade_at
ltq -> last_size
cp  -> previous_close_price
```

No bid/ask, reported volume, or OI.

### `IndexFullFeed`

Adopt only:

```text
ltpc
```

Ignore/defer `marketOHLC`.

Index LTQ must not be discarded merely because it appears; preserve it as Upstox-reported quantity under the neutral basis.

### `MarketFullFeed`

Adopt:

```text
ltpc
marketLevel.bidAskQuote[0]
vtt -> reported_volume
oi  -> open_interest
```

Inspect depth count. Normalize index `0` only.

### `FirstLevelWithGreeks`

Adopt:

```text
ltpc
firstDepth
vtt -> reported_volume
oi  -> open_interest
```

Do not adopt provider Greeks or IV.

Known unadopted fields never affect the adopted-semantics hash.


## 16. Numeric and timestamp conversion

### Prices

Use:

```python
Decimal(str(provider_double))
```

Never:

```python
Decimal(provider_double)
```

Rules:

- reject NaN/Infinity;
- canonicalize negative zero to Decimal zero;
- preserve zero;
- reject negative non-zero;
- no normalized float.

### Sizes and reported volume

Require:

```text
integer
not boolean
0 <= value <= 2**63 - 1
```

### Open interest

Require:

```text
finite
non-negative
mathematically integral
<= 2**53
<= 2**63 - 1
```

Convert to `int`.

### Epoch milliseconds

Use integer arithmetic:

```python
seconds, milliseconds = divmod(value, 1000)
instant = EPOCH_UTC + timedelta(
    seconds=seconds,
    milliseconds=milliseconds,
)
```

Reject booleans, negative values, and overflow. Return aware UTC.

Do not semantically validate unadopted Greeks, IV, OHLC, ATP, TBQ, or TSQ.


## 17. Depth behavior

For `MarketLevel.bidAskQuote`:

- maximum 30 levels;
- record actual count;
- normalize only level `0`;
- empty -> bid/ask `None`;
- preserve zero values;
- do not sort levels;
- do not infer missing side;
- do not reject crossed market;
- do not validate deeper prices/quantities semantically in DATA-1.3;
- `unadopted_depth_level_count = max(count - normalized_count, 0)`.

For `firstDepth`:

- use the present message as one level;
- absent message -> bid/ask unavailable;
- do not create a synthetic depth level.


## 18. Market-status events

Implement:

```text
ProviderMarketSegmentStatusObservationV1
```

Fields:

```text
identity
raw_event_id
provider
segment
provider_status_name
provider_status_numeric
status_is_known
provider_timestamp
received_at
available_at
recorded_at
source_order_scope_id
source_order
normalization_schema_version
normalizer_implementation_version
```

Preserve:

```text
PRE_OPEN_START
PRE_OPEN_END
NORMAL_OPEN
NORMAL_CLOSE
CLOSING_START
CLOSING_END
```

Do not collapse statuses.

Unknown numeric enum value:

```text
provider_status_name = UNKNOWN
provider_status_numeric = raw numeric
status_is_known = false
```

Status observations do not mutate DATA-1 sessions.


## 19. Lifecycle contracts

Implement offline-only immutable raw inputs and normalized events.

Connection states:

```text
connecting
connected
authorized
closing
closed
reconnecting
failed
```

Subscription states:

```text
subscribe_requested
subscribed
mode_change_requested
mode_changed
unsubscribe_requested
unsubscribed
subscription_failed
```

Freeze valid transition tables from the approved design proposal.

Lifecycle fields:

```text
provider
connection_session_id
subscription_scope_id
previous_state
state
source_order_scope_id
source_order
occurred_at
available_at
recorded_at
request_mode
instrument_keys_digest
instrument_key_count
redacted_reason_code
```

Rules:

- sorted unique keys for digest;
- reconnect creates a new connection session;
- no token, URL, traceback, raw exception, or socket object;
- local order is not provider sequence;
- one input emits one lifecycle event;
- implement pure sequence validation;
- do not wire into `streamer.py`.


## 20. Result atomicity and failure taxonomy

### `FrameNormalizationResultV1`

Fields:

```text
raw_frame_identity
frame_content_hash
status
accepted_events
failures
unadopted_schema_paths
present_unadopted_message_paths
secondary_payload_paths_present
decoded_entry_count
accepted_event_count
failed_entry_count
full_result_hash
adopted_semantics_hash
```

Statuses:

```text
complete
partial
failed
```

Whole-frame failures:

```text
frame_too_large
protobuf_decode_failed
unsupported_response_type
missing_provider_timestamp
invalid_provider_timestamp
empty_primary_payload
too_many_feeds
conflicting_raw_identity
duplicate_normalized_identity
```

Subject failures:

```text
unknown_provider_key
ambiguous_provider_mapping
stale_provider_mapping
subject_kind_mismatch
request_mode_union_mismatch
unsupported_feed_union
empty_supported_payload
invalid_timestamp
nonfinite_price
negative_price
invalid_quantity
fractional_open_interest
unsafe_open_interest
depth_limit_exceeded
```

Lifecycle failure:

```text
invalid_lifecycle_transition_input
```

A valid frame with one failed subject remains `partial` and returns deterministic valid events.

Reconcile:

```text
decoded quote entries = accepted quote events + subject failures
decoded status entries = accepted status events + segment failures
```

No silent skip.


## 21. Hash semantics

Define two explicit hashes.

### `full_result_hash`

Includes:

- raw frame identity;
- frame hash;
- capture provenance;
- ordered accepted events;
- failures;
- unadopted declarations;
- secondary payload declarations.

### `adopted_semantics_hash`

Includes only ordered DATA-1.3 adopted meaning:

- subject economic identity;
- adopted event type;
- response/snapshot mode;
- adopted quote/status values;
- quantity/numeric/presence bases;
- deterministic failures that concern adopted semantics.

Excludes:

- raw event ID;
- frame hash;
- connection/source-order identity;
- capture clocks;
- values of deferred fields;
- generated runtime timing.

Changing only Greeks/IV/OHLC/ATP/TBQ/TSQ/deeper-level values:

```text
changes frame hash
changes full_result_hash
does not change adopted_semantics_hash
```

Changing adopted best depth, LTPC, VTT, OI, status, or subject identity changes the adopted-semantics hash.


## 22. Deterministic decoding and serialization

Requirements:

- hash frame bytes before decode;
- frame limit 16 MiB;
- feed limit 5000;
- depth limit 30;
- status segment limit 256;
- sort all Proto maps explicitly;
- never trust generated map insertion order;
- immutable tuple output;
- unique sorted reason codes and path lists;
- no current-time call in pure normalization;
- no environment-dependent values;
- no network/database/random UUID;
- no Python object repr in hashes;
- Decimal and datetime use repository canonical serialization.

Unknown wire fields:

- may change raw/full hashes;
- do not alter adopted output unless a future schema version adopts them.


## 23. Subject-resolution service flow

Implement `MarketFrameNormalizationService`:

```text
1. validate raw envelope
2. hash/verify exact frame bytes
3. bounded decode
4. determine response type
5. collect sorted provider keys
6. resolve keys through MarketSubjectResolver using explicit cutoffs
7. normalize each subject independently
8. detect duplicate normalized identity
9. deterministically order events/failures/paths
10. calculate full and adopted-semantics hashes
11. return immutable result
```

For `market_info`, skip subject resolver.

The service may use async resolver ports. Pure provider mapping and conversion code remains synchronous and deterministic.


## 24. Fixtures

Create:

```text
backend/tests/fixtures/upstox/market_feed_v3/
```

Required binary fixtures:

1. multiple-segment `market_info`;
2. Nifty index `initial_feed/indexFF`;
3. Nifty future `live_feed/marketFF`;
4. Nifty option `live_feed/marketFF` with five levels;
5. option `firstLevelWithGreeks`;
6. direct LTPC;
7. multi-feed map-order A;
8. same semantic multi-feed map-order B;
9. zero values;
10. unknown provider key;
11. kind/union mismatch;
12. unknown market status;
13. secondary payload coexistence;
14. all deferred fields populated;
15. same adopted values with different deferred fields;
16. unknown wire field.

Programmatic hostile cases:

- malformed Protobuf;
- oversized frame;
- too many feeds;
- NaN/Infinity/negative adopted price;
- fractional/unsafe OI;
- more than 30 levels;
- exact raw duplicate;
- conflicting raw identity;
- duplicate normalized identity.

Lifecycle fixtures:

- valid connection sequence;
- invalid connection sequence;
- valid subscription sequence;
- invalid subscription sequence;
- reconnect/new-session sequence.

Each successful fixture has a capture sidecar with:

```text
fixture_schema_version
provider_schema_id
provider_schema_sha256
connection_session_id
source_order_scope_id
source_order
capture_basis
received_at
available_at
recorded_at
resolution_market_as_of
resolution_known_as_of
frame_sha256
expected_event_ids
expected_full_result_sha256
expected_adopted_semantics_sha256
```

Add deterministic regeneration and verification scripts.

Do not commit real provider captures or secrets.


## 25. Offline CLI

Implement:

```bash
cd backend

UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.normalize_market_event_fixture \
  --frame tests/fixtures/upstox/market_feed_v3/nifty-option-live-market-ff-d5.bin \
  --capture-manifest tests/fixtures/upstox/market_feed_v3/nifty-option-live-market-ff-d5.capture.json \
  --subject-manifest tests/fixtures/upstox/market_feed_v3/subjects.json \
  --output json \
  --verify-expected-hash
```

Requirements:

- no `DATABASE_URL`;
- no token;
- no network;
- no mutation;
- schema hash verification;
- canonical JSON output;
- accepted events/failures/path declarations/reconciliation;
- full and adopted-semantics hashes;
- no raw frame logging.

Exit codes:

```text
0 expected result matched
1 normalization/result mismatch
2 manifest/configuration error
3 schema/hash verification error
4 raw identity conflict
```


## 26. Existing LIVE-RV protection

Do not edit behavior in:

```text
backend/app/market_data/upstox/normalization.py
backend/app/market_data/upstox/streamer.py
backend/app/market_data/models.py
```

unless a mechanical import/package adjustment is unavoidable and explicitly reported.

Required regression proof:

- all pre-existing LIVE-RV tests pass unchanged;
- existing dashboard/WebSocket contracts remain byte-for-byte/field-for-field unchanged where fixtures exist;
- no new DATA-1.3 class is returned by the live streamer;
- no live authorization or subscription code imports the new normalizer.


## 27. Tests required before checkpoint

Implement tests for:

### Domain

- raw envelope invariants;
- raw identity duplicate/conflict;
- event identity;
- zero versus missing;
- time semantics;
- unit-neutral quantity fields;
- lifecycle transitions;
- canonical serialization.

### Proto/schema

- exact Proto hash;
- generated-code drift;
- package/root descriptor;
- known messages/field numbers/enums;
- malformed bytes;
- unknown enum;
- unknown wire field.

### Conversion

- Decimal round-trip conversion;
- negative zero;
- NaN/Infinity;
- negative price;
- int64 boundaries;
- integral/fractional/unsafe OI;
- integer-only timestamp conversion;
- provider/local clock skew.

### Adapter

- every supported response/mode/union combination;
- incompatible combinations;
- best-depth only;
- secondary payload coexistence;
- deferred field separation;
- partial subject failures;
- deterministic map ordering.

### Compatibility

- existing LIVE-RV suite unchanged.


## 28. Mandatory implementation checkpoint

Implement and commit only these first phases before proceeding to fixtures/CLI/docs completion:

1. direct Protobuf ownership and schema verifier;
2. provider-neutral normalization contracts;
3. subject-resolution port and static resolver;
4. bounded decoder;
5. quote/status normalizer;
6. focused domain/decoder/adapter tests;
7. LIVE-RV regression proof.

Suggested checkpoint commits:

```text
build(data): own Upstox V3 protobuf schema
feat(data): define market normalization contracts
feat(data): add market subject resolution boundary
feat(data): decode Upstox V3 market frames
feat(data): normalize Upstox V3 market observations
test(data): prove normalization boundary invariants
```

At the checkpoint:

```bash
git status --short
git log --oneline --decorate -10
git diff b2bb70ad6d8156f060c82c819f7c20335eef1f12..HEAD --stat
```

Run:

```bash
cd backend
env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    -u UPSTOX_ACCESS_TOKEN \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run python -m compileall -q app tests

env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    -u UPSTOX_ACCESS_TOKEN \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run pytest -ra \
      tests/market_data/normalization \
      tests/market_data/upstox \
      <existing LIVE-RV test paths>
```

Checkpoint requirements:

- zero focused skips;
- no database/network/token requirement;
- Alembic head unchanged;
- worktree clean;
- commits pushed to the feature branch;
- no implementation-evidence acceptance claim.

Stop and return the checkpoint report for review before completing lifecycle fixtures, offline CLI, full acceptance, and documentation.


## 29. Post-checkpoint completion plan

After checkpoint approval, implement:

1. lifecycle normalization and fixtures;
2. complete deterministic binary fixture corpus;
3. fixture regeneration and golden-hash verification;
4. offline CLI;
5. repository-backed subject resolver adapter;
6. full determinism/hash-seed tests;
7. complete backend regression on PostgreSQL 17;
8. frontend regression;
9. documentation;
10. review-pending implementation evidence.

Do not begin this phase before checkpoint approval.


## 30. Full acceptance requirements

After checkpoint approval and completion:

### Focused no-infrastructure suite

```bash
cd backend

env -u DATABASE_URL \
    -u DATABASE_RESTORE_TEST_URL \
    -u UPSTOX_ACCESS_TOKEN \
    UV_CACHE_DIR=/tmp/uv-cache \
    uv run pytest -ra \
      tests/market_data/normalization \
      tests/market_data/upstox
```

Required:

```text
zero skips
no network
no database
no token
```

### Hash-seed determinism

Run representative CLI fixtures with at least:

```text
PYTHONHASHSEED=1
PYTHONHASHSEED=999
```

Outputs must match for identical bytes/manifests.

### Full backend

Run with repository PostgreSQL 17 environment and existing sentinels:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m compileall -q app tests
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -ra
UV_CACHE_DIR=/tmp/uv-cache uv run alembic heads
UV_CACHE_DIR=/tmp/uv-cache uv run alembic current
UV_CACHE_DIR=/tmp/uv-cache uv run alembic check
```

Required:

```text
Alembic head = 20260804_03
no new upgrade operations
zero DATA-1.3 skips
```

### Frontend

```bash
cd frontend
pnpm lint
pnpm build
```

### Repository

```bash
git diff --check
git status --short
```

Run schema/generated-file verification, lock verification, tracked-artifact scan, and reasonable secret-pattern scan.


## 31. Documentation

After checkpoint approval, update:

```text
docs/design.md
docs/data-models.md
docs/dependencies.md
docs/environment.md
docs/testing.md
docs/security.md
docs/observability.md
docs/plan/options-market-infrastructure.md
docs/plan/roadmap.md
docs/plan/acceptance-gates.md
```

Create:

```text
docs/implementation/DATA-1.3-deterministic-market-event-normalization.md
```

Evidence status:

```text
implementation complete; acceptance evidence recorded; independent review pending
```

Do not mark accepted.

Document:

- official Proto URL/hash/version;
- complete field classification;
- approved design decisions;
- identities and clocks;
- unit-neutral quantities;
- partial normalization;
- deferred-field hash separation;
- secondary-payload coexistence;
- lifecycle offline-only boundary;
- unchanged LIVE-RV;
- unchanged Alembic head;
- exact tests and hashes.


## 32. Dependency ownership

Update:

```text
backend/pyproject.toml
backend/uv.lock
docs/dependencies.md
```

Record:

```text
protobuf owner: DATA-1.3
purpose: direct runtime decode of vendored Upstox V3 schema
range: >=7.35,<8
expected resolved: 7.35.1
license/security review
runtime footprint
removal criteria
```

Generation tool:

```text
grpcio-tools==1.82.1
```

It is isolated development tooling, not a runtime import.

Do not add unrelated serialization, logging, metrics, retry, Redis, or database dependencies.


## 33. Automatic implementation rejection conditions

The checkpoint or final implementation will be rejected if it:

- uses `ltt` as quote event/exchange time;
- labels `currentTs` exchange time;
- fabricates trade events;
- labels local order provider sequence;
- loses zero prices/sizes;
- stores market values as floats;
- gives unproven lot/contract units to quantities;
- normalizes provider Greeks/IV as QuantKYND analytics;
- semantically validates deferred analytics/candle fields;
- queries Postgres inside the decoder/normalizer;
- trusts Proto map order;
- rejects secondary payload coexistence automatically;
- mutates current LIVE-RV behavior;
- adds a migration;
- adds persistence;
- uses network/live Upstox acceptance;
- omits schema/generated-code drift verification;
- lacks deterministic fixture hashes;
- claims acceptance before independent review.


## 34. Required checkpoint response

Return:

- branch;
- verified starting SHA;
- checkpoint ending SHA;
- pushed branch SHA;
- commits;
- exact changed-file list;
- Proto source/hash;
- protobuf and generator versions;
- package layout;
- contract summary;
- raw and normalized identity summary;
- time semantics;
- quantity/OI semantics;
- partial-normalization behavior;
- secondary-payload behavior;
- deferred-field behavior;
- focused test result and skips;
- LIVE-RV regression result;
- Alembic head;
- worktree status;
- any deviation or unresolved issue.

Stop after the checkpoint. Do not proceed to the post-checkpoint completion phase until approval.
