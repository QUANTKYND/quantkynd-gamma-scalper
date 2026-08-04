# Selectable Upstox instrument with live close-to-close volatility overlay
One semantic rule must remain explicit:

> A live LTP is **not** a completed daily close and does not turn this into intraday realized volatility. During the session, it produces a **provisional close-to-close estimate**. Backtests, forecast evaluations, dataset hashes and persisted research runs must continue using finalized daily closes only.

Upstox provides the pieces we need: searchable instruments, stable `instrument_key` identifiers, V3 historical daily candles and the V3 protobuf WebSocket feed. LTPC mode contains LTP, last-trade time, quantity and previous close, which is sufficient for this milestone. ([Upstox - Online Stock and Share Trading][1])

The current application still has a single immutable `RVService` initialized for one symbol, and the frontend calls five RV endpoints without an instrument argument. This milestone should replace that API-facing singleton with a per-instrument registry while leaving deterministic research-run generation intact. 

### Objective

Implement a read-only live-market-data vertical slice for the **Close-to-Close Volatility Research** page.

The completed page must allow the operator to:

1. Search for an NSE/BSE index or equity.
2. Select it from a MUI autocomplete.
3. Load genuine Upstox historical daily closes for that instrument.
4. Recompute the existing RV features and forecast evaluation for the selected instrument.
5. Subscribe to Upstox Market Data Feed V3 in `ltpc` mode.
6. Display real-time LTP and feed status.
7. During an open session, use LTP as a clearly labelled provisional current-session close proxy.
8. Update the latest RV cards and final chart point without refreshing the page.
9. Keep all backtest metrics based exclusively on finalized daily closes.
10. Never fall back silently to synthetic data when live mode is requested.

This milestone is read-only. It must not introduce order placement, portfolio writes or execution APIs.

---

# 1. Required reading

Before implementation, read in repository order:

```text
AGENTS.md
docs/README.md
docs/conventions.md
docs/design.md
docs/data-models.md
docs/api.md
docs/environment.md
docs/dependencies.md
docs/testing.md
docs/performance.md
docs/observability.md
docs/security.md
docs/plan/options-market-infrastructure.md
docs/plan/acceptance-gates.md
```

Follow these repository rules:

* No direct `useEffect` in application or feature code.
* Fetch HTTP data through RTK Query.
* Keep WebSocket lifecycle inside RTK Query `onCacheEntryAdded` or an approved infrastructure adapter.
* Do not copy query results into component state.
* Do not render every provider tick.
* Add no explanatory code comments or docstrings.
* Keep existing comments unless their surrounding code is removed.
* Update all affected documentation in the same change.

---

# 2. Scope

## In scope

* Upstox instrument search for indices and equities.
* Instrument resolution by `instrument_key`.
* Upstox V3 historical daily candles.
* Upstox Market Data Feed V3 in `ltpc` mode.
* One shared upstream Upstox connection.
* Backend subscription multiplexing.
* Per-instrument finalized RV snapshots.
* Live provisional RV overlay.
* FastAPI WebSocket gateway.
* MUI autocomplete.
* RTK Query HTTP and WebSocket cache integration.
* Feed, subscription, freshness and market-status indicators.
* Tests using fake providers.
* Read-only pre-market smoke-test CLI.
* Documentation and environment updates.

## Out of scope

Do not implement:

* Options or futures selection.
* Option chains.
* Greeks.
* IV calculations.
* Intraday realized variance.
* Intraday RV aggregation.
* Tick persistence.
* Postgres.
* Redis.
* Broker orders.
* Paper orders.
* Portfolio positions.
* Trading signals.
* Automatic research-run persistence from live ticks.
* Synthetic fallback for live requests.

Redis is intentionally deferred. The current application is one backend process with a small active subscription set. Use an interface that can later receive a Redis-backed implementation, but use bounded in-memory latest-state storage for this milestone. This follows the existing performance document, which says correctness must not depend on Redis and recommends adding it when a cross-process need exists. 

---

# 3. User-visible behavior

## Instrument selector

Place a MUI `Autocomplete` near the page heading.

Default:

```text
NIFTY 50
NSE_INDEX|Nifty 50
```

The selector searches:

```text
NSE indices
BSE indices
NSE equities
BSE equities
```

It must not return:

```text
options
futures
currencies
commodities
mutual funds
expired instruments
```

Search begins after two characters.

Suggested grouped presentation:

```text
Indices
  NIFTY 50 · NSE
  NIFTY BANK · NSE
  SENSEX · BSE

NSE equities
  RELIANCE · Reliance Industries Ltd
  TCS · Tata Consultancy Services Ltd

BSE equities
  RELIANCE · Reliance Industries Ltd
```

Each option displays:

* Trading symbol or short name.
* Full name.
* Exchange.
* Instrument kind.
* Instrument key in secondary text or tooltip.

The selected instrument must be represented in the URL:

```text
/realised-volatility?instrument_key=NSE_INDEX%7CNifty%2050
```

Use `useSearchParams` and change it only from the autocomplete event handler.

Do not use local storage as the source of truth.

## Live status area

Show separate statuses:

```text
Upstox authentication    Authenticated / Missing / Error
Provider transport       Connecting / Connected / Reconnecting / Disconnected / Failed
Subscription             Subscribing / Subscribed / Unsubscribed / Rejected
Feed quality             Awaiting tick / Fresh / Stale / Unknown
Market                   Pre-open / Open / Closed / Unknown
Last tick                Timestamp
```

Do not describe authentication alone as “Connected.”

## Price area

Display:

```text
LTP
Absolute change from previous close
Percentage change from previous close
Previous close
Last trade time
```

## RV status

When the latest price is a completed daily close:

```text
Finalized close-to-close estimate
```

When a current-session LTP extends the finalized series:

```text
Live provisional estimate
Uses current LTP as an unfinished session-close proxy
```

When live data becomes stale:

```text
Live estimate stale
Last received at <time>
```

Keep the last known value visible, but visibly stale. Do not silently replace it with a synthetic or finalized value.

---

# 4. Quantitative semantics

Let the finalized close series end on session (t-1):

[
P_0,\ldots,P_{t-1}
]

During session (t), let the latest valid LTP be (L_t).

The provisional price series is:

[
P_0,\ldots,P_{t-1},L_t
]

Use this series only for:

* The latest 1-, 5-, 21- and 63-session estimates.
* The latest variance ratio.
* The latest regime/z-score where sufficient history exists.
* The live final point in the volatility-structure chart.
* The live final row in the feature table.

Do not use it for:

* Forecast model evaluation.
* Forward realized targets.
* Backtest metrics.
* Dataset identity.
* Persisted research artifacts.
* Research-run history.

## Provisional-row rule

Create a provisional row only when:

```text
a valid live quote exists
LTP > 0
last-trade timestamp is valid
the live exchange date is later than the latest finalized close date
```

Do not append two rows for the same exchange session.

If a finalized daily candle already exists for the live quote’s exchange date, use the finalized candle and do not label the row provisional.

## Dataset identity

The historical dataset ID must remain stable while ticks arrive.

It must hash only:

```text
instrument key
ordered finalized timestamps
ordered finalized close prices
frequency
provider/source
```

The live LTP belongs in separate overlay metadata and must not alter the finalized dataset ID.

## Time

* Provider timestamps are converted from epoch milliseconds.
* Persist and emit UTC timestamps.
* Interpret NSE/BSE session dates in `Asia/Kolkata`.
* Preserve:

  * provider timestamp,
  * last-trade timestamp,
  * received timestamp,
  * processed timestamp.

---

# 5. Architecture

Implement this flow:

```text
Upstox Instrument Search API
Upstox Historical Candle V3 API
                ↓
        UpstoxReadOnlyClient
                ↓
     InstrumentRVServiceRegistry
       finalized daily snapshots
                ↑
Upstox MarketDataStreamerV3
                ↓
       MarketDataCoordinator
                ↓
         LiveQuoteStore
                ↓
   Provisional RV Overlay Builder
                ↓
FastAPI REST snapshots + WebSocket deltas
                ↓
RTK Query cache and onCacheEntryAdded
                ↓
Coalesced React rendering
```

## Important boundary

There must be exactly one upstream Upstox market-data streamer per backend process.

Do not open one Upstox connection per browser, component or instrument selector.

Browser connections subscribe through the backend gateway. The backend reference-counts instrument subscriptions and multiplexes the one provider connection.

---

# 6. Dependencies

## Backend runtime

Add direct dependencies for functionality the application owns:

```toml
"httpx>=0.28,<1"
"upstox-python-sdk>=2.23,<3"
```

Codex must verify the latest compatible official 2.x SDK version before locking it.

The official SDK exposes `MarketDataStreamerV3`, including subscription management and reconnect events, while Upstox’s V3 wire feed itself is protobuf encoded. Use the SDK rather than committing generated protobuf Python files. ([GitHub][2])

Do not add:

```text
redis
sqlalchemy
psycopg
celery
grpcio-tools
a second WebSocket client library unless the SDK genuinely requires it
```

## Backend development

Add only if needed by the tests:

```toml
"pytest-asyncio>=0.25,<1"
```

Prefer `httpx.MockTransport` over adding a separate HTTP mocking package.

## Frontend

No new frontend dependency is required.

Use existing:

```text
MUI Autocomplete
RTK Query
React Router
MUI charts / Recharts already present
```

Update `docs/dependencies.md` with:

* Dependency.
* Purpose.
* Owner.
* Active milestone.
* Removal criteria.

---

# 7. Backend package structure

Suggested structure:

```text
backend/app/
├── api/
│   ├── instruments.py
│   ├── market_data.py
│   ├── market_streams.py
│   └── rv.py
│
├── market_data/
│   ├── models.py
│   ├── provider.py
│   ├── coordinator.py
│   ├── quote_store.py
│   ├── subscriptions.py
│   └── upstox/
│       ├── client.py
│       ├── instruments.py
│       ├── history.py
│       ├── streamer.py
│       └── normalization.py
│
├── instruments/
│   ├── models.py
│   └── service.py
│
├── schemas/
│   ├── instruments.py
│   ├── market_data.py
│   └── rv.py
│
└── services/
    ├── rv_service.py
    ├── rv_registry.py
    └── rv_live_overlay.py
```

Avoid large modules. Names, types and small functions must explain the implementation.

---

# 8. Provider interfaces

Define testable read-only protocols.

```python
class InstrumentProvider(Protocol):
    async def search(
        self,
        query: str,
        exchanges: tuple[str, ...],
        kinds: tuple[str, ...],
        limit: int,
    ) -> tuple[InstrumentDefinition, ...]: ...

    async def resolve(
        self,
        instrument_key: str,
    ) -> InstrumentDefinition: ...
```

```python
class HistoricalCloseProvider(Protocol):
    async def daily_closes(
        self,
        instrument_key: str,
        from_date: date,
        to_date: date,
    ) -> HistoricalCloseDataset: ...
```

```python
class LiveMarketProvider(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self, instrument_keys: tuple[str, ...]) -> None: ...
    async def unsubscribe(self, instrument_keys: tuple[str, ...]) -> None: ...
```

The quantitative and API layers must depend on these interfaces rather than importing the Upstox SDK directly.

---

# 9. Instrument search

Use the Upstox instrument-search endpoint server-side.

Provider request:

```text
GET https://api.upstox.com/v2/instruments/search
```

Use:

```text
query=<user text>
exchanges=NSE,BSE
segments=INDEX,EQ
page_number=1
records=<limit>
```

The official search API supports partial, case-insensitive name/symbol matching and exchange/segment filters, with at most 30 records per page. ([Upstox - Online Stock and Share Trading][1])

## Search validation

```text
minimum query length: 2
maximum query length: 50
default limit: 20
maximum limit: 30
allowed exchanges: NSE, BSE
allowed kinds: index, equity
```

Reject unsupported values.

## Instrument resolution

Implement exact resolution by `instrument_key`.

For equity keys:

```text
NSE_EQ|<ISIN>
BSE_EQ|<ISIN>
```

Search by ISIN and select the exact key.

For index keys:

```text
NSE_INDEX|Nifty 50
BSE_INDEX|SENSEX
```

Search by the portion after `|`, restrict to `INDEX`, and select the exact key.

Cache resolved instruments in memory for a bounded period.

No provider response may be trusted until normalized and validated.

---

# 10. Historical daily-close ingestion

Use:

```text
GET /v3/historical-candle/{instrument_key}/days/1/{to_date}/{from_date}
```

V3 supports daily data over long historical ranges and returns timestamp, OHLC, volume and open interest. ([Upstox - Online Stock and Share Trading][3])

## Default range

Fetch approximately three years:

```text
from_date = today - 3 years
to_date = today
```

Keep all valid observations for model warm-up.

The API may return newest-first or inconsistent order. Normalize by:

1. Parse timezone-aware timestamps.
2. Convert to exchange-session date.
3. Parse close as finite positive float.
4. Remove invalid rows.
5. Deduplicate by session date, retaining one deterministic row.
6. Sort ascending.
7. Require enough observations for the existing RV models.
8. Preserve provider provenance.

## Source metadata

Extend the dataset source union:

```text
csv
synthetic
upstox_historical
```

Live pages must report:

```text
source = upstox_historical
```

A failed Upstox request must return a visible API error. It must not fall back to synthetic prices.

## Cache

Create a bounded in-memory finalized-snapshot cache keyed by:

```text
instrument_key
```

Suggested behavior:

```text
maximum entries: 50
normal intraday TTL: 15 minutes
force refresh: explicit service method only
```

All RV REST responses for one instrument must use the same finalized snapshot and dataset ID.

---

# 11. Upstox live-feed wrapper

Use the official SDK’s `MarketDataStreamerV3`.

Initial mode:

```text
ltpc
```

Do not request `full`, `full_d30` or option Greeks for this milestone.

Upstox LTPC contains:

```text
ltp
ltt
ltq
cp
```

The provider sends market status first, a current snapshot second and live updates afterwards. ([Upstox - Online Stock and Share Trading][4])

## Lifecycle

The feed wrapper must support:

```text
idle
auth_missing
connecting
connected
reconnecting
disconnected
failed
stopping
```

Read the token lazily when the first subscription is requested. This allows OAuth to complete after backend startup.

Do not copy the access token into logs, responses, exceptions or frontend state.

## SDK callback boundary

The SDK may invoke callbacks outside the FastAPI event loop.

Bridge callbacks safely:

```text
SDK callback thread
        ↓
event_loop.call_soon_threadsafe(...)
        ↓
MarketDataCoordinator
```

Do not mutate asyncio-owned state directly from an SDK callback thread.

## Reconnection

Enable bounded auto-reconnect.

Suggested defaults:

```text
interval: 5 seconds
maximum attempts: 20
```

On reconnection:

1. Re-establish transport.
2. Re-subscribe all active reference-counted keys.
3. Keep feed state as reconnecting until a fresh provider message arrives.
4. Preserve the last quote but mark it stale.
5. Emit status changes to browser subscribers.

## Authentication failure

When no token exists:

* Historical and search requests return authentication failure.
* WebSocket clients receive a structured status event and close with an authentication-specific code.
* The UI shows the Upstox login control.
* No synthetic substitution occurs.

---

# 12. Subscription manager

Maintain reference counts:

```python
instrument_key -> active_browser_subscriber_count
```

Rules:

* First subscriber to a key triggers provider `subscribe`.
* Additional subscribers only increment the count.
* Disconnect decrements the count.
* Last subscriber triggers provider `unsubscribe`.
* Counts never become negative.
* Reconnect re-subscribes every key with count greater than zero.
* Unknown instruments are rejected before provider subscription.
* Maximum active keys is configurable.

Suggested initial maximum:

```text
50
```

This is well below Upstox’s published LTPC subscription limit. ([Upstox - Online Stock and Share Trading][4])

---

# 13. Live quote store

Create one bounded latest-state entry per instrument.

```python
class LiveQuoteState:
    instrument_key: str
    ltp: float
    previous_close: float | None
    last_trade_quantity: int | None
    last_trade_at: datetime | None
    provider_message_at: datetime
    received_at: datetime
    processed_at: datetime
    market_status: str | None
    sequence: int
```

## Freshness

Suggested default:

```text
stale_after_seconds = 5
```

Freshness status:

```text
awaiting_first_tick
fresh
stale
unknown
```

Do not use local receipt time as the last-trade time.

Expose both.

## Validation

Reject or flag:

* LTP less than or equal to zero.
* Non-finite prices.
* Invalid timestamps.
* Provider payload without requested instrument key.
* Last-trade time unreasonably ahead of provider/receipt time.
* Previous close less than or equal to zero.

Record counters for invalid provider events.

---

# 14. RV service refactor

The current API imports one global `rv_service`. Replace that API-facing pattern with:

```python
class InstrumentRVServiceRegistry:
    async def get(self, instrument_key: str) -> InstrumentRVService: ...
    async def refresh(self, instrument_key: str) -> InstrumentRVService: ...
```

The registry:

1. Resolves the instrument.
2. Fetches finalized daily history.
3. Builds the existing feature frame.
4. Builds the existing backtest.
5. Creates finalized dataset metadata.
6. Caches the immutable finalized service.

Keep the existing pure functions:

```text
build_rv_feature_frame
backtest_rv_forecast
dataset_id_for_prices
```

Generalize only where required.

Do not make the research CLI depend on the live feed.

## Live overlay builder

Add:

```python
class RVLiveOverlayBuilder:
    def latest(
        self,
        finalized_snapshot: RVResearchSnapshot,
        quote: LiveQuoteState | None,
    ) -> RVLatestResponse: ...

    def feature_series(
        self,
        finalized_snapshot: RVResearchSnapshot,
        quote: LiveQuoteState | None,
        limit: int,
    ) -> RVFeatureResponse: ...
```

The builder must:

* Leave the finalized snapshot immutable.
* Copy or concatenate only the minimal temporary series.
* Add no provisional row when the quote does not extend the finalized date.
* Mark the provisional point explicitly.
* Keep the finalized dataset ID unchanged.
* Never update backtest results from a live quote.

---

# 15. Schema changes

## Instrument definition

```python
class InstrumentDefinition(ApiModel):
    instrument_key: str
    exchange: Literal["NSE", "BSE"]
    segment: Literal["NSE_INDEX", "BSE_INDEX", "NSE_EQ", "BSE_EQ"]
    kind: Literal["index", "equity"]
    name: str
    short_name: str | None
    trading_symbol: str
    isin: str | None
    tick_size: float | None
    lot_size: int
```

## Instrument search response

```python
class InstrumentSearchResponse(ApiModel):
    query: str
    provider: Literal["upstox"]
    items: list[InstrumentDefinition]
    received_at: datetime
```

## Market-feed status

```python
class MarketDataStatusResponse(ApiModel):
    provider: Literal["upstox"]
    authentication_state: str
    transport_state: str
    subscription_state: str
    feed_quality: str
    market_status: str | None
    active_instrument_keys: list[str]
    connected_at: datetime | None
    last_message_at: datetime | None
    last_error_code: str | None
    last_error_at: datetime | None
    reconnect_attempt: int
```

## Live overlay metadata

```python
class RVLiveOverlayMetadata(ApiModel):
    provider: Literal["upstox"]
    instrument_key: str
    price_source: Literal["final_close", "live_ltp"]
    is_provisional: bool
    freshness: Literal[
        "awaiting_first_tick",
        "fresh",
        "stale",
        "unknown",
    ]
    market_status: str | None
    previous_close: float | None
    last_trade_at: datetime | None
    received_at: datetime | None
```

## Latest response additions

Add:

```python
instrument: InstrumentDefinition
finalized_as_of: date
live: RVLiveOverlayMetadata
```

Existing `as_of` refers to the estimate currently displayed.

## Feature point addition

Add:

```python
is_provisional: bool
```

Finalized rows always return `false`.

The temporary current-session row returns `true`.

## Dataset metadata

Extend source:

```python
Literal["csv", "synthetic", "upstox_historical"]
```

Do not put LTP into `RVDatasetMetadata`.

---

# 16. REST API

Update `docs/api.md` and implement the following.

| Router                              | Procedures of each router                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Instruments — `/api/v1/instruments` | `GET /search?query=&exchanges=NSE,BSE&kinds=index,equity&limit=20` returns normalized index/equity matches. `GET /resolve?instrument_key=` returns one exact instrument definition.                                                                                                                                                                                                                                                                                                                            |
| Market data — `/api/v1/market-data` | `GET /status` returns authentication, transport, subscription, feed-quality and market-status state. `GET /quotes/{instrument_key}` returns the latest normalized quote or an explicit awaiting-first-tick state.                                                                                                                                                                                                                                                                                              |
| Market streams — `/api/v1/streams`  | `WS /market-state?instrument_key=` sends an initial state snapshot followed by coalesced quote, provisional-RV and feed-status deltas.                                                                                                                                                                                                                                                                                                                                                                         |
| Realized volatility — `/api/v1/rv`  | `GET /latest?instrument_key=` returns finalized or live-provisional latest estimates. `GET /features?instrument_key=&limit=` returns finalized features plus at most one provisional point. `GET /backtest/latest?instrument_key=` returns finalized-close-only evaluation. `GET /history?instrument_key=&limit=` returns finalized-close-only forecast history. `GET /health?instrument_key=` returns module, dataset and live-overlay state. `GET /backtest/runs` remains global persisted research history. |

## Default instrument

When `instrument_key` is omitted:

```text
NSE_INDEX|Nifty 50
```

The response must state the selected instrument explicitly.

This default is configuration, not a synthetic fallback.

## URL encoding

Instrument keys contain `|` and may contain spaces.

Treat them as opaque strings and encode them correctly.

Prefer query parameters for RV routes.

---

# 17. WebSocket API

Endpoint:

```text
WS /api/v1/streams/market-state?instrument_key=<encoded-key>
```

The browser must never connect directly to Upstox.

## Initial behavior

After accepting and validating the client:

1. Resolve the instrument.
2. Subscribe through the coordinator.
3. Send a full initial snapshot.
4. Send subsequent deltas.
5. Unsubscribe in `finally`.

## Envelope

Use the documented versioned envelope:

```json
{
  "version": 1,
  "stream": "market-state",
  "sequence": 10429,
  "occurred_at": "2026-08-04T03:45:04.150Z",
  "event_type": "quote_updated",
  "entity_id": "NSE_INDEX|Nifty 50",
  "payload": {}
}
```

Supported event types:

```text
market_state_snapshot
feed_status_changed
market_status_changed
quote_updated
rv_provisional_updated
resync_required
provider_error
```

## Coalescing

Do not publish every provider tick to the browser.

Suggested publication targets:

```text
quote updates: at most every 250 ms
provisional RV recomputation: at most every 1000 ms
status transitions: immediately
```

When several ticks arrive inside one window, publish the newest accepted state.

## Sequence handling

* Sequence numbers are monotonic for each browser stream.
* The frontend tracks the previous sequence.
* A gap triggers REST invalidation/refetch.
* After refetch, the stream continues from fresh state.
* Do not attempt to reconstruct durable tick history from WebSocket deltas.

## Close behavior

Use documented application close codes, for example:

```text
4401 authentication required
4404 instrument not found
4408 subscription rejected
1011 provider failure
```

Do not include sensitive provider messages in the close reason.

---

# 18. FastAPI lifecycle

Use FastAPI lifespan management.

On startup:

* Create the coordinator.
* Create HTTP provider clients.
* Do not require the Upstox token.
* Do not connect to the live feed until a subscription exists.
* Optionally pre-warm the default instrument’s finalized daily snapshot.

On shutdown:

* Stop accepting subscriptions.
* Disconnect the provider streamer.
* Cancel broadcaster tasks.
* Close HTTP clients.
* Leave no non-daemon provider thread running.

Do not use module-import side effects to create a live network connection.

---

# 19. Frontend RTK Query changes

## Instrument API slice

Add:

```text
frontend/src/store/api/instrumentsApi.ts
```

Queries:

```typescript
searchInstruments({
  query,
  exchanges: ['NSE', 'BSE'],
  kinds: ['index', 'equity'],
  limit: 20,
})

resolveInstrument({
  instrumentKey,
})
```

Use `skipToken` when the search string has fewer than two characters.

## RV API query arguments

Change these from `void` to:

```typescript
type RVQueryArgs = {
  instrumentKey: string
}
```

Apply to:

```text
getLatest
getFeatures
getBacktest
getHistory
```

`getRuns` remains argument-free.

RTK Query must include the selected instrument key in its cache key automatically through the argument.

## Market stream cache

Add a query endpoint that owns the browser WebSocket:

```typescript
getMarketState: builder.query<
  MarketStateCache,
  { instrumentKey: string }
>
```

Use:

```typescript
queryFn
onCacheEntryAdded
updateCachedData
cacheEntryRemoved
dispatch
```

Inside `onCacheEntryAdded`:

1. Wait for initial cache setup.
2. Open the backend WebSocket.
3. Validate envelopes.
4. Track sequence numbers.
5. Coalesce quote updates.
6. Apply only the newest state during each render interval.
7. Invalidate the instrument’s RV tags on a sequence gap.
8. Close the socket and timers when the cache entry is removed.

This is the approved replacement for page-level `useEffect`.

No component may open or close a socket.

## WebSocket URL helper

Add a shared infrastructure helper that correctly handles:

```text
http -> ws
https -> wss
relative API_BASE in development
encoded instrument_key
```

Do not build the URL ad hoc in the page component.

---

# 20. Autocomplete component

Add:

```text
frontend/src/components/instruments/InstrumentAutocomplete.tsx
```

Requirements:

* MUI `Autocomplete`.
* Server-filtered results.
* `filterOptions={(options) => options}`.
* `isOptionEqualToValue` compares `instrument_key`.
* Group by instrument kind/exchange.
* Search text stored as user-input state.
* Use `useDeferredValue` for the search query.
* Loading indicator during search.
* Clear empty and error states.
* Selected value comes from the resolved/current instrument query.
* `onChange` updates URL search parameters.
* No `useEffect`.
* No duplicated selected-instrument Redux slice.
* No explanatory code comments.

Suggested width:

```text
360–480 px desktop
100% mobile
```

---

# 21. Dashboard integration

Refactor the page into an instrument-keyed body:

```tsx
<RvDashboardBody
  key={instrumentKey}
  instrumentKey={instrumentKey}
/>
```

This uses the approved `key` convention to reset any identity-specific local UI state.

## Page data

For the selected key, request:

```text
latest
features
backtest
history
market state stream
```

Runs remain global.

## Display precedence

For latest summary values:

```text
fresh provisional WebSocket RV
        ↓
latest REST response
```

For chart history:

```text
finalized REST points
        +
at most one provisional stream point
```

Never duplicate the current session.

## Chart behavior

The final provisional point must be visually distinguishable.

Use one or more of:

* Separate series.
* Distinct marker.
* Dashed segment.
* “Provisional” tooltip label.

Do not animate the entire chart on every update.

Do not recreate thousands of point objects per tick.

## Feature table

Add a status column:

```text
Final
Provisional
```

Only one row may be provisional.

## Dataset badge

Examples:

```text
Upstox historical · 718 finalized closes
```

During session:

```text
Upstox historical · 718 finalized closes
Live provisional overlay
```

Never show the synthetic-data badge on this live workspace.

---

# 22. Feed-status UX

## Authentication missing

Show:

```text
Connect Upstox to search instruments and load market data.
```

Keep the existing login action.

## Historical REST succeeds, stream fails

Show finalized RV history and backtest.

Add a warning:

```text
Historical data loaded. Live feed unavailable.
```

Do not label current values live.

## Market closed

Show:

```text
Market closed
Latest provider snapshot at <time>
```

The page still displays finalized history.

## Awaiting first tick

Show:

```text
Feed connected · awaiting first market snapshot
```

## Stale feed

Show a warning state after the configured threshold.

Do not hide the timestamp.

## Switching instruments

When the user selects a new instrument:

1. URL changes.
2. Old RTK Query stream cache entry is released.
3. Backend reference count decrements.
4. New REST data loads.
5. New live subscription begins.
6. Old instrument ticks cannot update the new dashboard.

---

# 23. Configuration

Add settings and `.env.example` entries.

```text
UPSTOX_API_BASE_URL=https://api.upstox.com
UPSTOX_DEFAULT_INSTRUMENT_KEY=NSE_INDEX|Nifty 50
UPSTOX_HISTORY_LOOKBACK_YEARS=3
UPSTOX_MARKET_DATA_MODE=ltpc
UPSTOX_STREAM_RECONNECT_INTERVAL_SECONDS=5
UPSTOX_STREAM_MAX_RECONNECT_ATTEMPTS=20
UPSTOX_MAX_ACTIVE_INSTRUMENTS=50
MARKET_DATA_STALE_AFTER_SECONDS=5
MARKET_DATA_UI_PUBLISH_INTERVAL_MS=250
RV_LIVE_RECOMPUTE_INTERVAL_MS=1000
RV_FINALIZED_SNAPSHOT_CACHE_SECONDS=900
```

Validate:

* Mode must be `ltpc`.
* Counts and durations must be positive.
* Publish interval must not exceed RV recomputation interval unless deliberately documented.
* Default instrument key must be non-empty.
* Active-instrument limit must remain beneath provider limits.

Update:

```text
docs/environment.md
docs/dependencies.md
docs/design.md
docs/data-models.md
docs/api.md
docs/performance.md
docs/observability.md
docs/security.md
docs/plan/options-market-infrastructure.md
README.md
```

---

# 24. Observability

Use structured logs with fields such as:

```text
event
provider
instrument_key
correlation_id
transport_state
subscription_state
feed_quality
provider_timestamp
received_at
processing_lag_ms
active_subscription_count
reconnect_attempt
error_code
```

Never log:

```text
access_token
authorized WebSocket URL
OAuth code
client secret
raw token-store content
```

Required counters:

```text
instrument_search_requests_total
historical_candle_requests_total
historical_candle_failures_total
market_feed_connections_total
market_feed_reconnects_total
market_feed_messages_total
market_feed_invalid_messages_total
market_feed_subscription_changes_total
market_feed_browser_clients
market_feed_active_instruments
market_feed_dropped_or_coalesced_updates_total
rv_live_recomputations_total
```

Required gauges/read models:

```text
last_provider_message_at
last_valid_quote_at by instrument
processing_lag_ms
active subscription count
feed freshness
```

A metrics backend is not required yet. Structured counters and status endpoints are sufficient.

---

# 25. Error handling

Introduce or reuse a stable problem-details response.

Required cases:

| Condition                        |                                               HTTP result |
| -------------------------------- | --------------------------------------------------------: |
| Missing Upstox token             |                                                     `401` |
| Invalid instrument query         |                                                     `422` |
| Unknown instrument key           |                                                     `404` |
| Provider authentication rejected |                                                     `401` |
| Provider rate limited            |                  `429` or mapped `503` with provider code |
| Historical provider unavailable  |                                                     `503` |
| Insufficient finalized closes    |                                                     `422` |
| Live quote not yet available     | `200` with explicit awaiting state for quote/status reads |
| Subscription capacity reached    |                              WebSocket rejection / `4408` |
| Internal normalization failure   |                  `502` or `503`, never synthetic fallback |

Do not expose raw Upstox response bodies to the browser.

---

# 26. Backend tests

All tests must use provider fakes or mock transports. No test should require an Upstox token or internet access.

## Instrument tests

* Search rejects fewer than two characters.
* Search rejects more than fifty characters.
* Only index/equity results survive normalization.
* NSE and BSE filtering works.
* Exact instrument resolution works.
* Duplicate provider rows deduplicate by instrument key.
* Invalid provider rows are rejected.
* Provider failure maps to the stable error contract.
* Access tokens never appear in responses or logs.

## Historical tests

* V3 candle arrays parse correctly.
* Newest-first input becomes ascending.
* Duplicate dates are deterministic.
* Invalid, zero, negative and infinite closes are removed.
* Timestamps convert to the correct India session date.
* Dataset ID is stable for identical finalized data.
* Dataset ID changes when a finalized close changes.
* Dataset ID does not change when an LTP changes.
* Insufficient history fails explicitly.
* No synthetic fallback occurs.

## Live-feed normalization tests

Fixtures for:

```text
market_info
LTPC snapshot
LTPC live update
missing previous close
invalid LTP
invalid timestamp
unrequested instrument key
```

Verify:

* LTP and previous close map correctly.
* Last-trade and receipt times remain distinct.
* Market status is preserved.
* Invalid messages increment rejection state and do not replace a valid quote.

## Subscription tests

* First browser subscriber triggers one upstream subscription.
* Second browser subscriber does not duplicate it.
* First disconnect does not unsubscribe while another remains.
* Last disconnect unsubscribes once.
* Reconnect resubscribes all active keys.
* Unknown keys never reach the provider.
* Counts never become negative.
* Capacity limit is enforced.

## Provisional RV tests

* No quote returns finalized latest estimates.
* Quote on a later session appends one provisional point.
* Multiple ticks on the same session replace the same provisional point.
* Quote on the finalized session does not append.
* Backtest metrics remain identical across live ticks.
* Forecast history remains identical across live ticks.
* Dataset ID remains identical across live ticks.
* Future live ticks cannot alter earlier finalized rows.
* Stale quote remains labelled stale.
* Invalid quote cannot become a provisional close.

## API tests

* Default instrument is NIFTY 50.
* Every selected-instrument RV endpoint returns the same instrument key.
* Every selected-instrument endpoint returns the same finalized dataset ID.
* Latest can be provisional.
* Feature response contains at most one provisional row.
* Backtest contains no provisional data.
* Run-history endpoint remains global.
* Missing token returns explicit authentication error.
* Search and resolve contracts reject extra fields.
* Market status endpoint differentiates authentication and transport.

## WebSocket tests

With a fake coordinator:

* Initial snapshot arrives first.
* Quote deltas use the versioned envelope.
* Sequence is monotonic.
* Feed-status transition is immediate.
* Quote updates are coalesced.
* Disconnect releases the subscription.
* Authentication failure closes correctly.
* Unknown instrument closes correctly.
* A sequence-gap test causes client-side invalidation logic to be testable at the TypeScript boundary where practical.

---

# 27. Frontend verification

A new frontend test framework is not required for this urgent milestone.

Mandatory:

```bash
npm run lint
npm run build
```

Static verification must confirm:

```bash
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

No new direct `useEffect` imports may exist in feature/application code.

Verify there is:

* No frontend Upstox token.
* No direct browser connection to Upstox.
* No copied RTK Query result in local state.
* No component-level socket lifecycle.
* No synthetic fallback label.
* No old unparameterized RV query usage.
* No chart update on every raw provider event.

---

# 28. Read-only smoke-test CLI

Add:

```text
backend/app/cli/verify_upstox_market_data.py
```

Invocation:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.verify_upstox_market_data \
  --instrument-key "NSE_INDEX|Nifty 50" \
  --listen-seconds 30
```

The command must:

1. Confirm a saved access token exists.
2. Resolve the instrument.
3. Fetch finalized daily candles.
4. Report observation count and date range.
5. Calculate finalized RV latest values.
6. Connect to Market Data Feed V3.
7. Subscribe in LTPC mode.
8. Print redacted status transitions.
9. Print the first valid normalized quote.
10. Print market status.
11. Disconnect cleanly.
12. Exit non-zero on failure.

Do not print:

```text
access token
authorized redirect URI
raw OAuth profile
raw SDK configuration
```

This CLI lets us validate the provider integration before market open. Upstox documents that the first feed message contains market status and the second contains a current snapshot, so a closed-market test can still prove connection and decoding before live ticks begin. ([Upstox - Online Stock and Share Trading][4])

---

# 29. Pre-market operating checklist

After implementation:

```bash
git pull
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Start the backend:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run uvicorn app.main:app --reload
```

Authenticate through the existing Upstox OAuth flow.

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache \
uv run python -m app.cli.verify_upstox_market_data \
  --instrument-key "NSE_INDEX|Nifty 50" \
  --listen-seconds 30
```

Verify REST:

```bash
curl --get \
  --data-urlencode "query=NIFTY" \
  --data-urlencode "exchanges=NSE,BSE" \
  --data-urlencode "kinds=index,equity" \
  --data-urlencode "limit=20" \
  http://localhost:8000/api/v1/instruments/search
```

```bash
curl --get \
  --data-urlencode "instrument_key=NSE_INDEX|Nifty 50" \
  http://localhost:8000/api/v1/rv/latest
```

Start frontend:

```bash
cd ../frontend
npm run lint
npm run build
npm run dev
```

Before open, verify:

```text
NIFTY 50 selected
real Upstox historical closes visible
no synthetic badge
market status visible
stream connected or awaiting snapshot
previous close visible
last provider snapshot visible
```

After open, verify:

```text
LTP changes without page reload
last-trade timestamp advances
feed freshness becomes Fresh
price change versus previous close updates
summary cards change at most once per second
last feature/chart point is marked Provisional
backtest metrics do not change tick by tick
```

Then select a stock such as Reliance and verify:

```text
the URL changes
historical data changes
old subscription is released
new subscription is established
old NIFTY ticks cannot update Reliance UI
new live quote appears
```

---

# 30. Acceptance criteria

Implementation status: complete. Local automated and static verification passed on 2026-08-04. The authenticated provider smoke test and closed/open-market observation remain operator validation steps and are not represented as implementation blockers in this checklist.

## Instrument selection

* [x] MUI autocomplete exists.
* [x] It searches NSE/BSE indices and equities only.
* [x] It starts searching after two characters.
* [x] Selection is represented by `instrument_key`.
* [x] Selection is stored in the URL.
* [x] Reload preserves the selected instrument.
* [x] Default selection is NIFTY 50.
* [x] Duplicate or ambiguous display names remain distinguishable by exchange.

## Historical data

* [x] Selected-instrument daily closes come from Upstox V3.
* [x] Finalized prices are positive, ordered and deduplicated.
* [x] RV calculations reuse the corrected RV-1 estimator.
* [x] Backtests use finalized closes only.
* [x] Dataset identity is stable.
* [x] Provider errors never trigger a synthetic fallback.
* [x] The UI displays the source as Upstox historical.

## Live feed

* [x] One upstream provider connection exists per backend process.
* [x] Provider mode is LTPC.
* [x] Subscription reference counting works.
* [x] Market status is visible.
* [x] LTP, previous close and last-trade time are visible.
* [x] Feed freshness is visible.
* [x] Reconnection is bounded.
* [x] Last state becomes stale during reconnect.
* [x] Tokens and authorized URLs never leave the backend.

## Provisional RV

* [x] Current-session LTP creates at most one provisional row.
* [x] Latest RV cards update from the provisional series.
* [x] Final chart point updates from the provisional series.
* [x] Provisional data is visually labelled.
* [x] Backtest metrics remain finalized-only.
* [x] Forecast history remains finalized-only.
* [x] Dataset hash does not change on ticks.
* [x] Stale live data is not presented as fresh.
* [x] No claim of intraday realized volatility is introduced.

## Frontend architecture

* [x] No direct `useEffect` in app or feature code.
* [x] HTTP fetching uses RTK Query.
* [x] WebSocket lifecycle uses `onCacheEntryAdded`.
* [x] Instrument changes happen in event handlers.
* [x] Identity reset uses `key`.
* [x] Query data is not copied into local component state.
* [x] Raw event frequency is not rendered.
* [x] Chart updates are bounded.
* [x] Frontend lint passes.
* [x] Frontend build passes.

## Backend architecture

* [x] Provider implementations sit behind protocols.
* [x] FastAPI lifespan owns the coordinator.
* [x] Module imports do not establish network connections.
* [x] SDK callback threads do not mutate asyncio state directly.
* [x] Shutdown disconnects cleanly.
* [x] Tests require no internet.
* [x] All backend tests pass.
* [x] `git diff --check` passes.

---

# 31. Non-negotiable safety constraints

Codex must not:

* Add order placement APIs.
* Instantiate an order client.
* Expose an Upstox access token.
* Connect the browser directly to Upstox.
* Treat LTP as a finalized close.
* Recompute forecast accuracy against unfinished data.
* Include provisional prices in dataset hashes.
* Persist raw market events as research history.
* Silently fall back to synthetic data.
* Open an upstream provider connection per browser.
* Add Redis merely because it appears in the long-term architecture.
* Add direct `useEffect`.
* Add explanatory code comments.
* Claim that the page now measures intraday realized volatility.

---

# 32. Codex completion report

Codex must report:

1. Active milestone name.
2. Commit SHA reviewed before changes.
3. Files added.
4. Files modified.
5. Files removed.
6. Dependencies added and why.
7. REST procedures added or changed.
8. WebSocket contract implemented.
9. Instrument-search normalization rules.
10. Historical-candle normalization rules.
11. Provider lifecycle and reconnection design.
12. Subscription reference-count behavior.
13. Provisional RV semantics.
14. Confirmation that backtests ignore live LTP.
15. Confirmation that dataset hashes ignore live LTP.
16. Backend test count and result.
17. Frontend lint result.
18. Frontend build result.
19. Smoke-test CLI result.
20. Closed-market behavior observed.
21. Known limitations.
22. Confirmation that no order path exists.
23. Confirmation that intraday realized variance remains unimplemented.

The milestone name should be recorded as:

```text
LIVE-RV-1 — Selectable Upstox instrument and provisional live close-to-close volatility
```

The immediate finish line is not merely “the LTP appears.” It is:

> The operator can select a real index or equity, see finalized Upstox daily history, observe a validated live quote, understand whether the feed is fresh, and see a clearly provisional close-to-close estimate update without contaminating the finalized research evaluation.

[1]: https://upstox.com/developer/api-documentation/instrument-search/ "Search Instruments API | Upstox Developer API"
[2]: https://github.com/upstox/upstox-python?utm_source=chatgpt.com "Upstox Python SDK for API v2"
[3]: https://upstox.com/developer/api-documentation/v3/get-historical-candle-data "Historical Candle Data V3 API | Upstox Developer API"
[4]: https://upstox.com/developer/api-documentation/v3/get-market-data-feed/ "Market Data Feed V3 API | Upstox Developer API"
