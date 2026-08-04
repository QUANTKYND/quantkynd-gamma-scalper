import { createApi, fakeBaseQuery } from '@reduxjs/toolkit/query/react'
import { rvApi, type RVFeatureResponse, type RVLatest } from './rvApi'
import { marketStateWebSocketUrl } from './webSocketUrl'

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
  active_instrument_keys: string[]
  connected_at: string | null
  last_message_at: string | null
  last_error_code: string | null
  last_error_at: string | null
  reconnect_attempt: number
}

export type MarketStateCache = { status: MarketStatus | null; quote: MarketQuote | null; rvLatest: RVLatest | null; rvFeatures: RVFeatureResponse | null }
type Envelope = { version: 1; stream: 'market-state'; sequence: number; entity_id: string; payload: { status?: MarketStatus; quote?: MarketQuote; rv_latest?: RVLatest; rv_features?: RVFeatureResponse } }

const isEnvelope = (value: unknown, instrumentKey: string): value is Envelope => {
  if (typeof value !== 'object' || value == null) return false
  const envelope = value as Partial<Envelope>
  return envelope.version === 1 && envelope.stream === 'market-state' && envelope.entity_id === instrumentKey && typeof envelope.sequence === 'number' && typeof envelope.payload === 'object'
}

export const marketApi = createApi({
  reducerPath: 'marketApi',
  baseQuery: fakeBaseQuery(),
  endpoints: (builder) => ({
    getMarketState: builder.query<MarketStateCache, { instrumentKey: string }>({
      queryFn: () => ({ data: { status: null, quote: null, rvLatest: null, rvFeatures: null } }),
      async onCacheEntryAdded({ instrumentKey }, { cacheDataLoaded, cacheEntryRemoved, updateCachedData, dispatch }) {
        await cacheDataLoaded
        const socket = new WebSocket(marketStateWebSocketUrl(instrumentKey))
        let previousSequence: number | null = null
        let pending: Envelope | null = null
        let timer: number | null = null
        const applyPending = (): void => {
          if (!pending) return
          const newest = pending
          pending = null
          updateCachedData((draft) => {
            if (newest.payload.status) draft.status = newest.payload.status
            if (newest.payload.quote) draft.quote = newest.payload.quote
            if (newest.payload.rv_latest) draft.rvLatest = newest.payload.rv_latest
            if (newest.payload.rv_features) draft.rvFeatures = newest.payload.rv_features
          })
        }
        socket.onmessage = (event): void => {
          let parsed: unknown
          try { parsed = JSON.parse(String(event.data)) } catch { return }
          if (!isEnvelope(parsed, instrumentKey)) return
          if (previousSequence != null && parsed.sequence !== previousSequence + 1) {
            dispatch(rvApi.util.invalidateTags([{ type: 'RV', id: instrumentKey }]))
          }
          previousSequence = parsed.sequence
          pending = parsed
          if (timer == null) timer = window.setTimeout(() => { timer = null; applyPending() }, 250)
        }
        await cacheEntryRemoved
        if (timer != null) window.clearTimeout(timer)
        socket.close()
      },
    }),
  }),
})

export const { useGetMarketStateQuery } = marketApi
