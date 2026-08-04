# API Contracts

## Conventions

- Canonical HTTP prefix: `/api/v1`.
- Root-level broker-auth aliases are transitional and should be removed after the frontend uses the canonical versioned routes.
- Request and response schemas reject unknown fields unless a documented compatibility case requires otherwise.
- Timestamps are ISO 8601 with timezone.
- Volatility and IV values are decimal annualized values; the frontend formats percentages.
- Variance values are decimal squared-return quantities.
- Prices and monetary amounts declare currency and precision where ambiguity exists.
- Collection procedures use cursor pagination once datasets become large.
- Write procedures accept or generate idempotency keys.
- Errors use a stable problem-details contract with code, message, correlation ID, and field errors.
- WebSocket messages use versioned envelopes and monotonic sequence numbers per stream.

## Current routers

| Router | Procedures of each router |
|---|---|
| System — `/api/v1` | `GET /health` returns service health. `GET /version` returns API version. |
| Authentication — canonical `/api/v1/auth`; transitional `/auth` | `GET /upstox/login` redirects to broker authorization. `GET /upstox/callback` validates state, exchanges the code, stores the token, and redirects to the frontend. `GET /status` returns broker authentication status. `POST /disconnect` removes the saved token and clears connection state. |
| Instruments — `/api/v1/instruments` | `GET /search?query=&exchanges=NSE,BSE&kinds=index,equity&limit=20` returns normalized Upstox index/equity matches. `GET /resolve?instrument_key=` resolves one exact provider key. |
| Market data — `/api/v1/market-data` | `GET /status?instrument_key=` separates authentication, transport, subscription, freshness, selected-segment market state, all segment statuses, bounded operational counters, browser-client count, and active-instrument count. `GET /quotes/{instrument_key}` returns the latest normalized LTPC state or an explicit awaiting state. |
| Market streams — `/api/v1/streams` | `WS /market-state?instrument_key=` returns an initial snapshot and coalesced status, quote, and provisional-RV deltas. |
| Realized-volatility research — `/api/v1/rv` | `GET /latest?instrument_key=` returns finalized or provisional estimates. `GET /features?instrument_key=&limit=` returns finalized features plus at most one provisional row. `GET /backtest/latest?instrument_key=`, `GET /history?instrument_key=&limit=`, and `GET /health?instrument_key=` use the selected finalized snapshot. `GET /backtest/runs` remains global. Omitted keys select `NSE_INDEX|Nifty 50`. |

## Planned routers

The procedures below are the target contract map. A router is added only when its milestone begins and its schemas, authorization, failure behavior, and tests are ready.

| Router | Procedures of each router |
|---|---|
| Instrument catalogue expansion | `GET /underlyings`, futures/options filters, catalogue status, and operator import remain planned after the LIVE-RV-1 search/resolve slice. |
| Sessions — `/api/v1/sessions` | `GET /current` returns current exchange-session state. `GET /calendar` returns sessions and holidays. `GET /{session_date}` returns boundaries and status. |
| Market-data expansion | Underlying/option quote resources, point-in-time chains, quality-event history, and controlled subscription writes remain planned. |
| Stream expansion | `WS /operations` and durable resume remain planned. LIVE-RV-1 sequences are browser-stream local; a gap triggers REST resynchronization. |
| Option analytics — `/api/v1/options` | `POST /price` evaluates a contract under explicit inputs. `POST /implied-volatility` solves IV from a supplied price. `POST /greeks` returns Greeks from explicit inputs. `GET /{contract_id}/analytics` returns latest validated market-derived analytics. |
| IV surfaces — `/api/v1/surfaces` | `GET /latest` returns the latest surface for an underlying. `GET /history` returns selected historical snapshots. `GET /{surface_id}` returns a stored surface. `GET /quality` returns fit and arbitrage diagnostics. `POST /rebuild` is an operator-only deterministic rebuild. |
| Volatility forecasts — `/api/v1/forecasts` | `GET /latest` returns active physical-variance forecasts by horizon. `GET /history` returns origin-aligned forecasts and realizations. `GET /models` lists approved models and versions. `POST /runs` starts an explicit research run, not an implicit live retrain. |
| Opportunities — `/api/v1/opportunities` | `GET /latest` returns eligible and rejected gamma candidates. `GET /{candidate_id}` returns full edge decomposition. `POST /evaluate` evaluates an explicit point-in-time snapshot and strategy configuration. |
| Strategies — `/api/v1/strategies` | `GET /definitions` lists versioned strategy definitions. `GET /definitions/{strategy_id}` returns configuration and hashes. `GET /runs` lists strategy runs. `GET /runs/{run_id}` returns state and artifacts. `POST /runs` starts a simulation or paper run after validation. `POST /runs/{run_id}/stop` requests a controlled stop. |
| Simulations — `/api/v1/simulations` | `POST /hedge-policy-runs` starts deterministic option and hedge simulations. `GET /runs` lists runs. `GET /runs/{run_id}` returns summary and provenance. `GET /runs/{run_id}/events` returns replay events. `GET /runs/{run_id}/attribution` returns P&L decomposition. |
| Backtests — `/api/v1/backtests` | `POST /runs` starts event-driven historical replay. `GET /runs` lists runs. `GET /runs/{run_id}` returns summary. `GET /runs/{run_id}/journal` returns decisions, intents, fills, and marks. `GET /runs/{run_id}/artifacts` lists immutable artifacts. |
| Portfolio — `/api/v1/portfolio` | `GET /positions` returns open and historical positions. `GET /greeks` returns net and bucketed Greeks. `GET /cash` returns the cash ledger summary. `GET /pnl` returns realized, unrealized, and attributed P&L. `GET /marks` returns mark provenance and quality. |
| Intents — `/api/v1/intents` | `GET /` lists strategy intents. `GET /{intent_id}` returns the immutable intent and status events. `POST /{intent_id}/cancel` requests cancellation before routing where permitted. Intents are never edited in place. |
| Paper orders — `/api/v1/paper-orders` | `POST /` submits an approved intent to the paper router. `GET /` lists paper orders. `GET /{order_id}` returns order state and transitions. `POST /{order_id}/cancel` requests cancellation. `POST /{order_id}/replace` requests cancel-replace using a new idempotency key. |
| Risk — `/api/v1/risk` | `GET /status` returns current limits, usage, and lockouts. `GET /decisions` lists risk decisions. `GET /policies` lists versioned policies. `POST /evaluate` evaluates an explicit intent without routing. `POST /kill-switch/engage` engages the switch. `POST /kill-switch/release` requires operator authorization and recorded reason. |
| Reconciliation — `/api/v1/reconciliation` | `GET /latest` returns the latest result. `GET /history` lists results. `POST /run` performs an operator-controlled reconciliation. `GET /{reconciliation_id}` returns differences and resolution state. |
| Operations — `/api/v1/operations` | `GET /health` returns component health. `GET /readiness` verifies required dependencies and safe state. `GET /heartbeats` returns worker heartbeats. `GET /alerts` lists active and recent alerts. `GET /config` returns redacted active configuration and version hashes. |

## Error contract

```json
{
  "type": "https://quantkynd.dev/problems/stale-market-data",
  "title": "Market data is stale",
  "status": 409,
  "code": "stale_market_data",
  "detail": "The newest eligible option quote exceeds the strategy freshness limit.",
  "correlation_id": "opaque-id",
  "field_errors": []
}
```

## WebSocket envelope

```json
{
  "version": 1,
  "stream": "market-state",
  "sequence": 10429,
  "occurred_at": "2026-08-04T09:15:04.150+05:30",
  "event_type": "option_quote_updated",
  "entity_id": "opaque-contract-id",
  "payload": {}
}
```

Clients detect sequence gaps and request a fresh snapshot. WebSocket events are notifications and state deltas; durable history remains in Postgres.

LIVE-RV-1 event types are `market_state_snapshot`, `feed_status_changed`, `market_status_changed`, `quote_updated`, `rv_provisional_updated`, `resync_required`, and `provider_error`. Application close codes are `4401` for missing authentication, `4404` for unknown instrument, `4408` for rejected subscription, and `1011` for provider failure.

LIVE-RV-1.1 returns pre-accept HTTP denial responses with `401` for missing authentication and `404` for an unknown instrument where the ASGI server supports WebSocket denial responses. After acceptance, subscription rejection closes with `4408` and unrecoverable provider failure closes with `1011`. No provider error text appears in an event or close reason. A stream begins with `market_state_snapshot`; `resync_required` tells clients to invalidate selected-instrument REST state after finalized-history rollover.
