# Codex Task — LIVE-RV-1.1 Hardening

## Milestone

**LIVE-RV-1.1 — Live market-data correctness and lifecycle hardening**

## Objective

Harden the completed LIVE-RV-1 implementation before moving to STRAT-1 and SIM-1.

This milestone addresses four correctness and operational gaps:

1. Per-instrument quote sequence allocation.
2. Concurrent first-subscription safety.
3. Backend and frontend WebSocket lifecycle correctness.
4. Enforced prohibition of direct `useEffect` imports.

The existing live market-data architecture must remain read-only. Do not introduce order placement, paper execution, portfolio state, Redis, Postgres, option analytics, or intraday realized volatility.

---

## Required reading

Read these files before making changes:

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

Then inspect the current LIVE-RV-1 implementation, especially:

```text
backend/app/market_data/coordinator.py
backend/app/market_data/upstox/normalization.py
backend/app/api/market_streams.py
backend/app/services/rv_registry.py
frontend/src/store/api/marketApi.ts
frontend/src/pages/RvDashboard.tsx
frontend/eslint.config.js
backend/tests/test_live_rv.py
```

Follow all repository conventions:

- No direct `useEffect` in application or feature code.
- HTTP fetching uses RTK Query.
- WebSocket lifecycle belongs in RTK Query `onCacheEntryAdded` or approved infrastructure code.
- Do not copy query results into component state.
- New code carries no explanatory comments.
- Existing comments remain unless the surrounding code is removed.
- Update affected documentation in the same change.
- Do not expose tokens, authorized WebSocket URLs, OAuth codes, provider secrets, or raw provider errors.

---

# 1. Fix per-instrument quote sequence allocation

## Problem

The current coordinator increments one provider-level sequence per incoming payload. The normalizer then derives quote sequences using an offset inside that payload.

That can produce duplicate or non-monotonic application sequences for an instrument when provider payloads contain multiple instruments.

Example:

```text
Payload 1:
  Instrument A -> 1
  Instrument B -> 2

Payload 2:
  Instrument A -> 2
  Instrument B -> 3
```

Instrument A receives sequence `2` twice.

## Required design

Application sequence numbers must be assigned by the coordinator after normalization, not by the provider normalizer.

Use a per-instrument sequence registry:

```python
instrument_key -> monotonically increasing integer
```

Suggested responsibility split:

```text
Provider normalizer
  validates payloads
  returns normalized quote candidates
  assigns no application sequence

Coordinator
  accepts normalized quote candidates
  increments sequence per instrument
  creates LiveQuoteState
  stores and broadcasts accepted state
```

Suggested private state:

```python
self._quote_sequences: dict[str, int]
```

Suggested allocation:

```python
next_sequence = self._quote_sequences.get(instrument_key, 0) + 1
self._quote_sequences[instrument_key] = next_sequence
```

The sequence must increase only when a quote is accepted for that instrument.

Invalid provider payloads must not consume an accepted-quote sequence.

## Required tests

Add tests proving:

- Two successive multi-instrument payloads produce strictly increasing sequences for every instrument.
- Reordered instruments inside a later payload do not affect monotonicity.
- An invalid quote does not replace valid state.
- An invalid quote does not advance the accepted sequence.
- Sequences are independent across instrument keys.
- Quote-store stale or duplicate rejection logic still behaves correctly.

---

# 2. Fix concurrent first-subscription safety

## Problem

The current first subscriber can register itself locally, release the coordinator lock, and await the upstream provider subscription.

A second subscriber can arrive during that wait and return as though the instrument were already subscribed.

If the first upstream subscription then fails, rollback can remove the shared listener state and leave the second browser with an orphan queue.

## Required design

Maintain an explicit subscription entry per instrument.

Suggested internal model:

```python
class SubscriptionState:
    instrument_key: str
    phase: Literal["subscribing", "subscribed", "rejected"]
    listeners: set[asyncio.Queue]
    readiness: asyncio.Future[None]
```

Equivalent dataclass or internal structure is acceptable.

Required behavior:

### First subscriber

1. Acquire lock.
2. Create entry with phase `subscribing`.
3. Register listener.
4. Release lock.
5. Start exactly one upstream subscribe call.
6. Resolve or fail the shared readiness future.

### Additional subscriber while subscribing

1. Acquire lock.
2. Register listener on the same entry.
3. Capture the same readiness future.
4. Release lock.
5. Await readiness.
6. Return only after upstream subscription succeeds.
7. Raise the same stable subscription failure if it fails.

### Success

```text
phase = subscribed
resolve readiness future
all waiting callers complete successfully
```

### Failure

```text
phase = rejected
fail readiness future
all waiting callers receive the same stable failure
no caller returns as subscribed
no listener remains orphaned
entry becomes eligible for clean retry
```

### Retry

A later subscriber after failure must be able to create a fresh `subscribing` entry and trigger a new upstream call.

### Unsubscribe

- Disconnect removes only that caller’s listener.
- Upstream unsubscribe occurs only when the final listener is removed from a successfully subscribed entry.
- Counts or listener sizes never become negative.
- A rejected or failed entry must not trigger a duplicate upstream unsubscribe.

## Required tests

Add concurrent async tests for:

- Two concurrent subscribers with successful upstream subscription.
- Two concurrent subscribers with failed upstream subscription.
- Both callers receive failure when the shared upstream subscription fails.
- Exactly one upstream subscribe call occurs.
- No orphan queues remain after failure.
- A later retry succeeds.
- Disconnecting one of two active listeners does not unsubscribe upstream.
- Disconnecting the final listener unsubscribes exactly once.
- Listener counts never become negative.
- Capacity limits remain correct during concurrent subscription attempts.

Use deterministic fake providers and synchronization primitives. Do not use sleeps as the primary concurrency-control mechanism in tests.

---

# 3. Correct backend WebSocket handshake and lifecycle

## Problem

The current endpoint performs expensive historical snapshot loading and upstream subscription work before `websocket.accept()`.

Closing before acceptance does not reliably deliver the intended application close codes to the browser. It can instead become an HTTP denial response, and the connection handshake may remain pending while historical and provider work runs.

## Required flow

Separate cheap pre-accept validation from post-accept provider setup.

Recommended flow:

```text
Parse instrument key
        ↓
Check authentication availability
        ↓
Validate or cheaply resolve instrument identity
        ↓
Return HTTP denial for pre-accept failures when supported
        ↓
Accept WebSocket
        ↓
Register backend subscription
        ↓
Load or obtain initial finalized snapshot
        ↓
Send initial market-state snapshot
        ↓
Stream deltas
        ↓
Release subscription in finally
```

Do not fetch several years of historical candles before accepting the WebSocket.

## Failure behavior

Use stable semantics:

| Condition | Behavior |
|---|---|
| Missing authentication before acceptance | HTTP denial response with `401` where supported |
| Unknown instrument before acceptance | HTTP denial response with `404` where supported |
| Subscription rejected after acceptance | Close with application code `4408` |
| Provider failure after acceptance | Close with `1011` |
| Client disconnect | Release listener and reference count in `finally` |
| Internal normalization failure | Send stable provider-error event where safe, then close if stream cannot continue |

Do not include raw provider error text in responses or close reasons.

## Initial event ordering

The first accepted stream event must be:

```text
market_state_snapshot
```

Subsequent events may be:

```text
feed_status_changed
market_status_changed
quote_updated
rv_provisional_updated
resync_required
provider_error
```

Status events generated during setup must be incorporated into the initial snapshot or queued after it. They must not precede the initial snapshot.

## Coalescing

Preserve bounded rendering behavior:

```text
quote updates: at most every 250 ms
provisional RV recomputation: at most every 1000 ms
status transitions: immediate
```

Do not send unchanged status events every timeout interval.

Track the last emitted freshness and transport state.

Emit a status event only when state changes.

A slower explicit heartbeat may be added only if documented and tested.

## Required backend WebSocket tests

Add tests proving:

- Authentication denial occurs before an accepted application stream.
- Unknown instrument denial behaves correctly.
- Accepted streams send `market_state_snapshot` first.
- Subscription rejection after acceptance closes with `4408`.
- Provider failure after acceptance closes with `1011`.
- Disconnect cleanup removes the listener.
- Disconnect cleanup decrements the upstream reference count.
- Quote messages are coalesced.
- Status transitions are immediate.
- Unchanged status is not emitted every second.
- Stream sequence numbers are monotonic.
- Initial snapshot contains the requested instrument key.
- No token or provider URL appears in any event or close reason.

---

# 4. Correct frontend WebSocket lifecycle visibility

## Problem

The RTK Query cache currently initializes with empty market data but does not expose explicit browser-socket state through `onopen`, `onerror`, and `onclose`.

A failed handshake can appear as an indefinitely connecting feed.

A closed socket is not distinguishable from an empty-but-still-connecting cache entry.

## Required cache model

Extend the market-state cache:

```typescript
type MarketSocketState =
  | "connecting"
  | "open"
  | "closed"
  | "failed"

type MarketStateCache = {
  socketState: MarketSocketState
  closeCode: number | null
  closedAt: string | null
  status: MarketDataStatus | null
  quote: MarketQuote | null
  rvLatest: RVLatestResponse | null
  rvFeatures: RVFeatureResponse | null
}
```

Use equivalent names only if they remain explicit.

## Required `onCacheEntryAdded` behavior

### Initial state

```text
socketState = connecting
closeCode = null
closedAt = null
```

### `socket.onopen`

```text
socketState = open
```

### `socket.onerror`

```text
socketState = failed
```

Do not copy raw browser or provider error strings into user-visible state.

### `socket.onclose`

```text
socketState = closed
closeCode = event.code
closedAt = current UTC timestamp
```

Preserve the last valid quote and RV overlay, but allow the UI to mark them stale or unavailable.

### `socket.onmessage`

- Validate the versioned envelope.
- Reject unsupported versions.
- Track stream sequence.
- On sequence gap, invalidate the selected instrument’s finalized REST tags.
- Apply coalesced quote state.
- Apply bounded provisional RV updates.
- Never update a dashboard for a different instrument key.

### Cache cleanup

When `cacheEntryRemoved` resolves:

- Clear all timers.
- Remove event handlers where appropriate.
- Close the socket if it is still open or connecting.
- Do not dispatch state updates after cleanup.

## Required dashboard behavior

When historical REST data is valid but the socket is closed or failed, show:

```text
Historical data loaded. Live feed unavailable.
```

Continue showing finalized RV data.

When connecting:

```text
Connecting to live feed
```

When accepted but awaiting first quote:

```text
Feed connected · awaiting first market snapshot
```

When fresh:

```text
Live feed fresh
```

When stale or reconnecting:

```text
Live estimate stale
Last received at <timestamp>
```

Do not hide the last valid value.

Do not label a finalized REST value as live.

## Frontend verification

Add tests if the existing setup supports them without introducing a large new framework.

At minimum, static and build verification must prove:

- `socketState` is represented in the cache.
- `onopen`, `onerror`, and `onclose` update cache state.
- Historical-only warning is reachable.
- Instrument switching releases the old cache entry.
- Old instrument events cannot update the new selected instrument.
- The page does not open a socket directly.
- The component does not use `useEffect`.

---

# 5. Enforce the `useEffect` ban in ESLint

## Requirement

The convention must be enforced by lint, not only documented or checked with grep.

Add a restricted-import rule for application and feature code.

Suggested rule:

```javascript
"no-restricted-imports": [
  "error",
  {
    paths: [
      {
        name: "react",
        importNames: ["useEffect"],
        message:
          "Direct useEffect is banned. Use render derivation, RTK Query, event handlers, key resets, or useMountEffect.",
      },
    ],
  },
]
```

The exact ESLint flat-config shape may differ. Keep the behavior equivalent.

## Approved exception

Only the infrastructure module implementing the approved custom hook may import `useEffect`.

Expected path should match the repository’s actual hook location, for example:

```text
frontend/src/hooks/useMountEffect.ts
```

Use a targeted override for that file.

Do not weaken the restriction for entire directories.

## Required verification

This must fail lint:

```typescript
import { useEffect } from "react"
```

This must remain valid:

```typescript
import { useMountEffect } from "@/hooks/useMountEffect"
```

Also run:

```bash
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

The command must produce no direct application or feature imports.

---

# 6. Segment-specific market status

## Requirement

Preserve provider market status by segment instead of collapsing all segments into one global state.

Suggested model:

```python
segment_statuses: dict[str, str]
```

Derive the displayed market status from the selected instrument’s segment:

```text
NSE_INDEX
BSE_INDEX
NSE_EQ
BSE_EQ
```

Do not report an NSE equity as open because an unrelated segment is open.

## Required tests

- Mixed provider segment statuses preserve all segment values.
- Selected NSE equity derives from the NSE equity segment.
- Selected BSE index derives from the BSE index segment.
- Unknown segment returns `unknown`.
- A status update for another segment does not change the selected instrument’s displayed state.

This item may be implemented in LIVE-RV-1.1 because it is localized and prevents misleading operator state.

---

# 7. Use exchange-local date for historical refresh

## Requirement

Replace host-local `date.today()` for NSE/BSE historical range construction with an explicit India exchange date:

```python
datetime.now(ZoneInfo("Asia/Kolkata")).date()
```

Equivalent injected clock design is preferred for testability.

Do not depend on the deployment host timezone.

## Required tests

- A UTC timestamp near midnight maps to the correct India date.
- Historical `to_date` uses the injected exchange-local date.
- Tests remain deterministic through an injected clock or explicit date.

---

# 8. Finalized-history rollover handling

Implement a minimal, safe rollover policy.

The current live overlay must not remain indefinitely attached to an obsolete finalized snapshot across a session boundary.

Acceptable minimal implementation:

1. Track the finalized snapshot’s latest session date and dataset ID.
2. On exchange-date change or explicit finalized-refresh event:
   - invalidate the selected instrument’s RV REST tags,
   - refresh the registry snapshot,
   - emit `resync_required`,
   - rebuild the live overlay from the refreshed finalized snapshot.
3. Do not append a provisional row if the newly finalized candle already covers the live quote’s session date.

A full scheduler is not required.

The behavior must be testable with an injected clock or explicit rollover trigger.

## Required tests

- Exchange-date change causes a refresh or resync.
- A newly finalized candle removes the provisional duplicate.
- Dataset ID changes only when finalized history changes.
- Backtest remains finalized-only.
- Live quote remains separate from the finalized dataset hash.

---

# 9. Documentation updates

Update the following where affected:

```text
docs/design.md
docs/api.md
docs/data-models.md
docs/performance.md
docs/observability.md
docs/testing.md
docs/security.md
docs/plan/options-market-infrastructure.md
README.md
```

Document:

- Per-instrument accepted-quote sequences.
- Subscription state machine.
- WebSocket denial and close semantics.
- Frontend socket lifecycle states.
- Segment-specific market status.
- Exchange-local date handling.
- Finalized-history rollover behavior.
- ESLint enforcement of the direct `useEffect` ban.

Keep `docs/api.md` API tables in the existing two-column format:

| Router | Procedures of each router |
|---|---|

Do not add implementation prose as code comments.

---

# 10. Acceptance criteria

Implementation status: complete. Backend tests, frontend lint, frontend production build, ESLint prohibition probe, tracked-cache scan, and `git diff --check` passed on 2026-08-04.

## Quote sequencing

- [x] Normalization assigns no application sequence.
- [x] Coordinator assigns sequence per accepted instrument quote.
- [x] Each instrument’s sequence is strictly increasing.
- [x] Invalid quotes do not advance accepted sequence.
- [x] Multi-instrument payloads are covered by tests.

## Concurrent subscriptions

- [x] One upstream subscribe call occurs for simultaneous first subscribers.
- [x] All simultaneous subscribers await the same readiness result.
- [x] No caller returns before upstream success.
- [x] All callers fail consistently on upstream rejection.
- [x] No orphan queue remains.
- [x] Retry after failure works.
- [x] Final disconnect unsubscribes exactly once.
- [x] Counts never become negative.

## Backend WebSocket

- [x] Cheap validation occurs before expensive work.
- [x] Authentication denial behavior is explicit.
- [x] Unknown-instrument denial behavior is explicit.
- [x] Accepted stream sends `market_state_snapshot` first.
- [x] Post-accept subscription rejection closes with `4408`.
- [x] Provider failure closes with `1011`.
- [x] Cleanup always releases the subscription.
- [x] Quote updates remain coalesced.
- [x] Unchanged status is not emitted repeatedly.
- [x] No secrets appear in events or close reasons.

## Frontend WebSocket

- [x] Cache exposes `connecting`, `open`, `closed`, and `failed`.
- [x] `onopen`, `onerror`, and `onclose` update cache state.
- [x] Historical-only warning is visible when live stream fails.
- [x] Last valid state remains visible but stale.
- [x] Sequence gaps invalidate selected-instrument REST state.
- [x] Cache cleanup closes sockets and timers.
- [x] Old instrument streams cannot update a new instrument page.

## Conventions

- [x] ESLint rejects direct `useEffect` imports.
- [x] Only `useMountEffect` infrastructure may import `useEffect`.
- [x] No new explanatory code comments exist.
- [x] HTTP fetching remains in RTK Query.
- [x] Socket lifecycle remains in `onCacheEntryAdded`.

## Market status and time

- [x] Market status is preserved by segment.
- [x] Displayed status derives from the selected instrument’s segment.
- [x] Subscription status derives from the selected instrument when one is requested.
- [x] Historical refresh uses `Asia/Kolkata`.
- [x] Date logic is testable and deterministic.

## Finalized rollover

- [x] Session rollover triggers refresh or resync.
- [x] Concurrent rollover readers reuse the registry's per-instrument refresh.
- [x] A finalized current-session candle removes provisional duplication.
- [x] Dataset ID changes only with finalized data.
- [x] Backtest remains finalized-only.
- [x] LTP remains excluded from dataset hashing.

## Verification

- [x] All backend tests pass.
- [x] Frontend lint passes.
- [x] Frontend production build passes.
- [x] `git diff --check` passes.
- [x] No tracked Python cache files exist.
- [x] No direct `useEffect` exists outside `useMountEffect`.
- [x] No order-placement code is introduced.
- [x] Intraday realized variance remains unimplemented.

## Closure corrections

- [x] A rejected or pending subscription does not alter another instrument's selected status.
- [x] Generic provider errors retain browser and upstream subscriptions during automatic reconnect.
- [x] Reconnect exhaustion emits terminal `provider_error` and closes with `1011`.
- [x] Fresh quotes clear reconnect-forced staleness.
- [x] Frontend socket failure remains distinguishable from normal closure.

---

# 11. Commands Codex must run

From the repository root:

```bash
cd backend
UV_CACHE_DIR=/tmp/uv-cache uv sync --group dev
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

Then:

```bash
cd ../frontend
npm run lint
npm run build
```

Run the direct-import check:

```bash
grep -R "useEffect" frontend/src \
  --exclude="useMountEffect.ts"
```

Run repository checks:

```bash
cd ..
git diff --check
git ls-files | grep -E '(__pycache__|\.pyc$)' && exit 1 || true
```

No authenticated provider smoke test is required for automated completion of this hardening milestone, but Codex must not claim operational provider validation unless it was actually run with valid credentials.

---

# 12. Completion report

Codex must provide:

1. Active milestone name.
2. Starting commit SHA.
3. Ending commit SHA if committed.
4. Files added.
5. Files modified.
6. Files removed.
7. Sequence-allocation design.
8. Concurrent-subscription state machine.
9. WebSocket handshake and denial design.
10. Browser-socket lifecycle model.
11. Status-coalescing behavior.
12. Segment-specific market-status design.
13. Exchange-local date implementation.
14. Finalized-rollover behavior.
15. ESLint enforcement details.
16. Backend test count and result.
17. Frontend lint result.
18. Frontend build result.
19. `git diff --check` result.
20. Direct `useEffect` scan result.
21. Known limitations.
22. Confirmation that no order path was added.
23. Confirmation that intraday realized variance remains unimplemented.
24. Confirmation that authenticated provider smoke testing remains an operator validation step unless actually executed.

Use this final status only when all acceptance criteria pass:

```text
LIVE-RV-1.1: COMPLETE
Authenticated provider smoke test: OPERATOR VALIDATION PENDING
Open-market observation: OPERATOR VALIDATION PENDING
Ready for STRAT-1: YES
```
