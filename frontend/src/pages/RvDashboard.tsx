import { AutoGraphRounded, ScienceRounded } from '@mui/icons-material'
import { Box, Chip, Grid, Paper, Stack, Typography } from '@mui/material'
import BrokerConnection from '../components/BrokerConnection'
import ErrorState from '../components/rv/ErrorState'
import LoadingState from '../components/rv/LoadingState'
import RvBacktestTable from '../components/rv/RvBacktestTable'
import RvFeatureTable from '../components/rv/RvFeatureTable'
import RvLineChart from '../components/rv/RvLineChart'
import RvRunHistory from '../components/rv/RvRunHistory'
import RvSummaryCards, { type SummaryCard } from '../components/rv/RvSummaryCards'
import {
  useGetBacktestQuery,
  useGetFeaturesQuery,
  useGetHistoryQuery,
  useGetLatestQuery,
  useGetRunsQuery,
} from '../store/api/rvApi'

const panelSx = { p: { xs: 2, md: 2.5 }, borderColor: 'divider', backgroundImage: 'none', overflow: 'hidden' }

const RvDashboard = (): React.ReactElement => {
  const latestQuery = useGetLatestQuery()
  const featuresQuery = useGetFeaturesQuery()
  const backtestQuery = useGetBacktestQuery()
  const runsQuery = useGetRunsQuery()
  const historyQuery = useGetHistoryQuery()
  const results = [latestQuery, featuresQuery, backtestQuery, runsQuery, historyQuery]
  const isLoading = results.some((query) => query.isLoading)
  const hasError = results.some((query) => query.isError)
  const retry = (): void => { results.forEach((query) => { void query.refetch() }) }

  if (isLoading) return <LoadingState />
  if (hasError || !latestQuery.data || !featuresQuery.data || !backtestQuery.data || !runsQuery.data || !historyQuery.data) return <ErrorState onRetry={retry} />

  const latest = latestQuery.data
  const backtest = backtestQuery.data
  const cards: SummaryCard[] = [
    { label: '21-day RV', value: `${(latest.rv_21d * 100).toFixed(2)}%`, sublabel: `As of ${latest.as_of}`, tone: 'accent' },
    { label: 'Regime', value: latest.regime[0].toUpperCase() + latest.regime.slice(1), sublabel: `Z-score ${latest.rv_zscore_21.toFixed(2)}`, tone: latest.regime === 'high' ? 'warn' : 'good' },
    { label: 'Forecast RMSE', value: `${(backtest.metrics.rmse * 100).toFixed(2)}%`, sublabel: `${backtest.model.toUpperCase()} · ${backtest.horizon_days}d`, tone: 'neutral' },
    { label: '5d / 21d ratio', value: latest.rv_ratio_5_21.toFixed(2), sublabel: latest.rv_ratio_5_21 > 1 ? 'Short vol elevated' : 'Short vol contained', tone: latest.rv_ratio_5_21 > 1 ? 'warn' : 'good' },
  ]

  return (
    <Stack spacing={2.5}>
      <BrokerConnection />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'flex-end' } }}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><AutoGraphRounded color="primary" /><Typography variant="h4" component="h1">Realized volatility</Typography></Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>Monitor volatility structure and audit forward forecast quality for {latest.symbol}.</Typography>
        </Box>
        <Chip icon={<ScienceRounded />} label={`${latest.source} data`} size="small" variant="outlined" sx={{ textTransform: 'capitalize' }} />
      </Stack>

      <RvSummaryCards cards={cards} />

      <Paper variant="outlined" sx={panelSx}>
        <RvLineChart title="Volatility term structure" subtitle="Annualized realized volatility against the underlying price" points={featuresQuery.data.points} mode="overview" />
      </Paper>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><RvLineChart title="Forecast versus realized" subtitle="Five-day EWMA forecast compared with subsequent realized volatility" points={historyQuery.data.points} mode="forecast" /></Paper></Grid>
        <Grid size={{ xs: 12, lg: 4 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><Typography variant="h6">Run history</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Latest research executions</Typography><RvRunHistory runs={runsQuery.data.runs} /></Paper></Grid>
      </Grid>

      <Paper variant="outlined" sx={panelSx}><RvBacktestTable summary={backtest} /></Paper>

      <Paper variant="outlined" sx={{ ...panelSx, p: 0 }}>
        <Box sx={{ px: { xs: 2, md: 2.5 }, pt: 2.5, pb: 1.5 }}><Typography variant="h6">Feature monitor</Typography><Typography variant="body2" color="text.secondary">Most recent 20 time-safe observations</Typography></Box>
        <RvFeatureTable rows={featuresQuery.data.points.slice(-20).reverse()} />
      </Paper>
    </Stack>
  )
}

export default RvDashboard
