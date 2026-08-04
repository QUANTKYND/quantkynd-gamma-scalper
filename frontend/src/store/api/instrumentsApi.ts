import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { API_BASE } from './base'

export type InstrumentDefinition = {
  instrument_key: string
  exchange: 'NSE' | 'BSE'
  segment: 'NSE_INDEX' | 'BSE_INDEX' | 'NSE_EQ' | 'BSE_EQ'
  kind: 'index' | 'equity'
  name: string
  short_name: string | null
  trading_symbol: string
  isin: string | null
  tick_size: number | null
  lot_size: number
}

type SearchResponse = { query: string; provider: 'upstox'; items: InstrumentDefinition[]; received_at: string }
type SearchArgs = { query: string; exchanges: ('NSE' | 'BSE')[]; kinds: ('index' | 'equity')[]; limit: number }

export const instrumentsApi = createApi({
  reducerPath: 'instrumentsApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE }),
  endpoints: (builder) => ({
    searchInstruments: builder.query<SearchResponse, SearchArgs>({
      query: ({ query, exchanges, kinds, limit }) => ({ url: '/instruments/search', params: { query, exchanges: exchanges.join(','), kinds: kinds.join(','), limit } }),
    }),
    resolveInstrument: builder.query<InstrumentDefinition, { instrumentKey: string }>({
      query: ({ instrumentKey }) => ({ url: '/instruments/resolve', params: { instrument_key: instrumentKey } }),
    }),
  }),
})

export const { useSearchInstrumentsQuery, useResolveInstrumentQuery } = instrumentsApi
