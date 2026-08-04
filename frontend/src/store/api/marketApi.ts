import { createApi, fakeBaseQuery } from '@reduxjs/toolkit/query/react'
import { rvApi, type RVFeatureResponse, type RVLatest } from './rvApi'
import { marketStateWebSocketUrl } from './webSocketUrl'

export type MarketSocketState = 'connecting' | 'open' | 'closed' | 'failed'

export type MarketQuote = {
  instrument_key?: string
  status: 'awaiting_first_tick' | 'available'
  freshness: 'awaiting_first_tick' | 'fresh' | 'stale' | 'unknown'
  ltp?: number
  previous_close?: number | null
  last_trade_quantity?: number | null
  last_trade_at?: string
  received_at?: string
  market_status?: string | null
  sequence?: number
}

export type MarketStatus = {
  authentication_state: string
  transport_state: string
  subscription_state: string
  market_status: string | null
  segment_statuses: Record<string, string>
  active_instrument_keys: string[]
  connected_at: string | null
  last_message_at: string | null
  last_error_code: string | null
  last_error_at: string | null
  reconnect_attempt: number
}

export type MarketStateCache = {
  socketState: MarketSocketState
  closeCode: number | null
  closedAt: string | null
  status: MarketStatus | null
  quote: MarketQuote | null
  rvLatest: RVLatest | null
  rvFeatures: RVFeatureResponse | null
}

type EventType = 'market_state_snapshot' | 'feed_status_changed' | 'market_status_changed' | 'quote_updated' | 'rv_provisional_updated' | 'resync_required' | 'provider_error'
type Envelope = { version: 1; stream: 'market-state'; sequence: number; event_type: EventType; entity_id: string; payload: { status?: MarketStatus; quote?: MarketQuote; rv_latest?: RVLatest; rv_features?: RVFeatureResponse } }

const isEnvelope = (value: unknown, instrumentKey: string): value is Envelope => {
  if (typeof value !== 'object' || value == null) return false
  const envelope = value as Partial<Envelope>
  return envelope.version === 1 && envelope.stream === 'market-state' && envelope.entity_id === instrumentKey && typeof envelope.sequence === 'number' && typeof envelope.event_type === 'string' && typeof envelope.payload === 'object'
}

export const marketApi = createApi({
  reducerPath: 'marketApi',
  baseQuery: fakeBaseQuery(),
  endpoints: (builder) => ({
    getMarketState: builder.query<MarketStateCache, { instrumentKey: string }>({
      queryFn: () => ({ data: { socketState: 'connecting', closeCode: null, closedAt: null, status: null, quote: null, rvLatest: null, rvFeatures: null } }),
      async onCacheEntryAdded({ instrumentKey }, { cacheDataLoaded, cacheEntryRemoved, updateCachedData, dispatch }) {
        await cacheDataLoaded
        const socket = new WebSocket(marketStateWebSocketUrl(instrumentKey))
        let previousSequence: number | null = null
        let pending: Envelope | null = null
        let timer: number | null = null
        let cleanedUp = false
        const applyEnvelope = (envelope: Envelope): void => {
          if (cleanedUp) return
          updateCachedData((draft) => {
            if (envelope.payload.status) draft.status = envelope.payload.status
            if (envelope.payload.quote) draft.quote = envelope.payload.quote
            if (envelope.payload.rv_latest) draft.rvLatest = envelope.payload.rv_latest
            if (envelope.payload.rv_features) draft.rvFeatures = envelope.payload.rv_features
          })
        }
        const applyPending = (): void => {
          if (!pending) return
          const newest = pending
          pending = null
          applyEnvelope(newest)
        }
        socket.onopen = (): void => {
          if (cleanedUp) return
          updateCachedData((draft) => { draft.socketState = 'open' })
        }
        socket.onerror = (): void => {
          if (cleanedUp) return
          updateCachedData((draft) => {
            draft.socketState = 'failed'
            if (draft.quote) draft.quote.freshness = 'stale'
            if (draft.rvLatest) draft.rvLatest.live.freshness = 'stale'
            if (draft.rvFeatures) draft.rvFeatures.live.freshness = 'stale'
          })
        }
        socket.onclose = (event): void => {
          if (cleanedUp) return
          updateCachedData((draft) => {
            if (draft.socketState !== 'failed') draft.socketState = 'closed'
            draft.closeCode = event.code
            draft.closedAt = new Date().toISOString()
            if (draft.quote) draft.quote.freshness = 'stale'
            if (draft.rvLatest) draft.rvLatest.live.freshness = 'stale'
            if (draft.rvFeatures) draft.rvFeatures.live.freshness = 'stale'
          })
        }
        socket.onmessage = (event): void => {
          let parsed: unknown
          try { parsed = JSON.parse(String(event.data)) } catch { return }
          if (!isEnvelope(parsed, instrumentKey) || cleanedUp) return
          if (previousSequence != null && parsed.sequence !== previousSequence + 1) {
            dispatch(rvApi.util.invalidateTags([{ type: 'RV', id: instrumentKey }]))
          }
          if (parsed.event_type === 'resync_required') {
            dispatch(rvApi.util.invalidateTags([{ type: 'RV', id: instrumentKey }]))
          }
          previousSequence = parsed.sequence
          if (parsed.event_type === 'quote_updated' || parsed.event_type === 'rv_provisional_updated') {
            pending = parsed
            if (timer == null) timer = window.setTimeout(() => { timer = null; applyPending() }, 250)
          } else {
            applyEnvelope(parsed)
          }
        }
        await cacheEntryRemoved
        cleanedUp = true
        if (timer != null) window.clearTimeout(timer)
        socket.onopen = null
        socket.onerror = null
        socket.onclose = null
        socket.onmessage = null
        if (socket.readyState === WebSocket.CONNECTING || socket.readyState === WebSocket.OPEN) socket.close()
      },
    }),
  }),
})

export const { useGetMarketStateQuery } = marketApi
