import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'
import { API_BASE } from './base'
import type { InstrumentDefinition } from './instrumentsApi'

export type RVRegime = 'low' | 'normal' | 'high' | 'unknown'
export type RVModelName = 'naive' | 'ewma'
export type RVQueryArgs = { instrumentKey: string }

export type RVEstimatorMetadata = {
  estimator_id: 'close_to_close_squared_log_returns_v1'
  input_frequency: '1d_close'
  return_type: 'log'
  annualization_periods: number
  observation_timing: 'end_of_day'
  is_intraday_realized_variance: false
}

export type RVDatasetMetadata = {
  dataset_id: string
  source: 'csv' | 'synthetic' | 'upstox_historical'
  symbol: string
  observations: number
  start_date: string
  end_date: string
  computed_at: string
  synthetic_parameters: null | { seed: number; periods: number; end_date: string; initial_price: number }
}

export type RVHorizonEstimate = {
  horizon_sessions: number
  horizon_variance: number
  annualized_variance: number
  annualized_volatility: number
}

export type RVLiveOverlay = {
  provider: 'upstox'
  instrument_key: string
  price_source: 'final_close' | 'live_ltp'
  is_provisional: boolean
  freshness: 'awaiting_first_tick' | 'fresh' | 'stale' | 'unknown'
  market_status: string | null
  previous_close: number | null
  last_trade_at: string | null
  received_at: string | null
}

export type RVLatest = {
  symbol: string
  as_of: string
  price: number
  estimates: RVHorizonEstimate[]
  variance_ratio_5_21: number | null
  volatility_zscore_21: number | null
  regime: RVRegime
  estimator: RVEstimatorMetadata
  dataset: RVDatasetMetadata
  instrument: InstrumentDefinition
  finalized_as_of: string
  live: RVLiveOverlay
}

export type RVFeatureRow = {
  date: string
  price: number
  estimates: RVHorizonEstimate[]
  variance_ratio_5_21: number | null
  volatility_zscore_21: number | null
  regime: RVRegime
  is_provisional: boolean
}

export type RVForecastHistoryPoint = {
  origin_date: string
  target_start: string
  target_end: string
  price: number
  forecast_annualized_variance: number
  forecast_annualized_volatility: number
  actual_annualized_variance: number
  actual_annualized_volatility: number
}

export type RVBacktestMetrics = { mae: number | null; rmse: number | null; correlation: number | null; change_direction_accuracy: number | null; n_obs: number }
export type RVRegimeMetric = { regime: RVRegime; variance_metrics: RVBacktestMetrics; volatility_metrics: RVBacktestMetrics }

export type RVBacktestSummary = {
  symbol: string
  model: RVModelName
  model_parameters: Record<string, number | string>
  horizon_sessions: number
  evaluation_method: 'sequential_non_overlapping_metrics'
  chart_stride: number
  metric_stride: number
  overlapping_chart_targets: boolean
  overlapping_metric_targets: boolean
  evaluation_start: string
  evaluation_end: string
  estimator: RVEstimatorMetadata
  dataset: RVDatasetMetadata
  variance_metrics: RVBacktestMetrics
  volatility_metrics: RVBacktestMetrics
  regime_metrics: RVRegimeMetric[]
  instrument: InstrumentDefinition
}

export type RVRunSummary = {
  run_id: string
  created_at: string
  completed_at: string | null
  status: 'complete' | 'failed' | 'running'
  symbol: string
  dataset_id: string
  estimator_id: string
  model: RVModelName
  model_parameters: Record<string, number | string>
  horizon_sessions: number
  evaluation_method: string
  failure_reason: string | null
}

export type RVFeatureResponse = { symbol: string; estimator: RVEstimatorMetadata; dataset: RVDatasetMetadata; points: RVFeatureRow[]; instrument: InstrumentDefinition; finalized_as_of: string; live: RVLiveOverlay }
export type RVHistoryResponse = { symbol: string; model: RVModelName; horizon_sessions: number; estimator: RVEstimatorMetadata; dataset: RVDatasetMetadata; points: RVForecastHistoryPoint[]; instrument: InstrumentDefinition }
export type RVRunsResponse = { runs: RVRunSummary[] }

export const estimateFor = (estimates: RVHorizonEstimate[], horizonSessions: number): RVHorizonEstimate | undefined => estimates.find((estimate) => estimate.horizon_sessions === horizonSessions)

const instrumentParams = ({ instrumentKey }: RVQueryArgs): { instrument_key: string } => ({ instrument_key: instrumentKey })

export const rvApi = createApi({
  reducerPath: 'rvApi',
  baseQuery: fetchBaseQuery({ baseUrl: API_BASE }),
  tagTypes: ['RV'],
  endpoints: (builder) => ({
    getLatest: builder.query<RVLatest, RVQueryArgs>({ query: (args) => ({ url: '/rv/latest', params: instrumentParams(args) }), providesTags: (_result, _error, args) => [{ type: 'RV', id: args.instrumentKey }] }),
    getFeatures: builder.query<RVFeatureResponse, RVQueryArgs>({ query: (args) => ({ url: '/rv/features', params: instrumentParams(args) }), providesTags: (_result, _error, args) => [{ type: 'RV', id: args.instrumentKey }] }),
    getBacktest: builder.query<RVBacktestSummary, RVQueryArgs>({ query: (args) => ({ url: '/rv/backtest/latest', params: instrumentParams(args) }), providesTags: (_result, _error, args) => [{ type: 'RV', id: args.instrumentKey }] }),
    getRuns: builder.query<RVRunsResponse, void>({ query: () => '/rv/backtest/runs' }),
    getHistory: builder.query<RVHistoryResponse, RVQueryArgs>({ query: (args) => ({ url: '/rv/history', params: instrumentParams(args) }), providesTags: (_result, _error, args) => [{ type: 'RV', id: args.instrumentKey }] }),
  }),
})

export const { useGetLatestQuery, useGetFeaturesQuery, useGetBacktestQuery, useGetRunsQuery, useGetHistoryQuery } = rvApi
