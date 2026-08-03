import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { API_BASE } from './base'

export type RVRegime = 'low' | 'normal' | 'high' | string

export type RVLatest = {
  symbol: string
  as_of: string
  price: number
  rv_1d: number
  rv_5d: number
  rv_21d: number
  rv_63d: number
  rv_ratio_5_21: number
  rv_zscore_21: number
  regime: RVRegime
  source: 'csv' | 'synthetic'
}

export type RVChartPoint = {
  date: string
  price?: number
  rv_1d?: number
  rv_5d?: number
  rv_21d?: number
  rv_63d?: number
  forecast_5d?: number
  actual_forward_5d?: number
}

export type RVFeatureRow = Required<Pick<RVChartPoint, 'date' | 'price' | 'rv_1d' | 'rv_5d' | 'rv_21d' | 'rv_63d'>> & {
  rv_ratio_5_21: number
  rv_zscore_21: number
  regime: RVRegime
}

export type RVBacktestSummary = {
  symbol: string
  model: string
  horizon_days: number
  train_start: string
  train_end: string
  test_start: string
  test_end: string
  metrics: {
    mae: number
    rmse: number
    correlation: number
    directional_accuracy: number
  }
  regime_metrics: Array<{
    regime: string
    mae: number
    rmse: number
    count: number
  }>
}

export type RVRunSummary = {
  run_id: string
  created_at: string
  symbol: string
  model: string
  horizon_days: number
  status: 'complete' | 'failed' | 'running'
}

export type RVFeatureResponse = { symbol: string; points: RVFeatureRow[] }
export type RVHistoryResponse = { symbol: string; points: RVChartPoint[] }
export type RVRunsResponse = { runs: RVRunSummary[] }

export const rvApi = createApi({
  reducerPath: 'rvApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE }),
  tagTypes: ['RV'],
  endpoints: (builder) => ({
    getLatest: builder.query<RVLatest, void>({
      query: () => '/rv/latest',
      providesTags: ['RV'],
    }),
    getFeatures: builder.query<RVFeatureResponse, void>({
      query: () => '/rv/features',
      providesTags: ['RV'],
    }),
    getBacktest: builder.query<RVBacktestSummary, void>({
      query: () => '/rv/backtest/latest',
      providesTags: ['RV'],
    }),
    getRuns: builder.query<RVRunsResponse, void>({
      query: () => '/rv/backtest/runs',
      providesTags: ['RV'],
    }),
    getHistory: builder.query<RVHistoryResponse, void>({
      query: () => '/rv/history',
      providesTags: ['RV'],
    }),
  }),
})

export const {
  useGetLatestQuery,
  useGetFeaturesQuery,
  useGetBacktestQuery,
  useGetRunsQuery,
  useGetHistoryQuery,
} = rvApi
