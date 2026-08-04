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
  estimateFor,
  useGetBacktestQuery,
  useGetFeaturesQuery,
  useGetHistoryQuery,
  useGetLatestQuery,
  useGetRunsQuery,
} from '../store/api/rvApi'

const panelSx = { p: { xs: 2, md: 2.5 }, borderColor: 'divider', backgroundImage: 'none', overflow: 'hidden' }
const pct = (value: number | null | undefined): string => value == null ? 'N/A' : `${(value * 100).toFixed(2)}%`
const numberText = (value: number | null | undefined): string => value == null ? 'N/A' : value.toFixed(2)
const titleCase = (value: string): string => value[0].toUpperCase() + value.slice(1)

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
  const oneSession = estimateFor(latest.estimates, 1)
  const fiveSession = estimateFor(latest.estimates, 5)
  const twentyOneSession = estimateFor(latest.estimates, 21)
  const sixtyThreeSession = estimateFor(latest.estimates, 63)
  const cards: SummaryCard[] = [
    { label: '1-session annualized volatility', value: pct(oneSession?.annualized_volatility), sublabel: `As of ${latest.as_of}`, tone: 'neutral' },
    { label: '5-session annualized volatility', value: pct(fiveSession?.annualized_volatility), sublabel: `${backtest.horizon_sessions}-session forecast horizon`, tone: 'accent' },
    { label: '21-session annualized volatility', value: pct(twentyOneSession?.annualized_volatility), sublabel: 'Close-to-close estimator', tone: 'accent' },
    { label: '63-session annualized volatility', value: pct(sixtyThreeSession?.annualized_volatility), sublabel: 'Daily close fallback', tone: 'neutral' },
    { label: '5D / 21D annualized variance ratio', value: numberText(latest.variance_ratio_5_21), sublabel: latest.variance_ratio_5_21 != null && latest.variance_ratio_5_21 > 1 ? 'Short variance elevated' : 'Short variance contained', tone: latest.variance_ratio_5_21 != null && latest.variance_ratio_5_21 > 1 ? 'warn' : 'good' },
    { label: 'Volatility regime', value: titleCase(latest.regime), sublabel: `21D z-score ${numberText(latest.volatility_zscore_21)}`, tone: latest.regime === 'high' ? 'warn' : latest.regime === 'low' ? 'good' : 'neutral' },
  ]

  return (
    <Stack spacing={2.5}>
      <BrokerConnection />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'flex-end' } }}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><AutoGraphRounded color="primary" /><Typography variant="h4" component="h1">Close-to-Close Volatility Research</Typography></Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>Calculated from daily close-to-close squared log returns. This is not an intraday realized-volatility estimator.</Typography>
        </Box>
        <Chip icon={<ScienceRounded />} label={`${latest.dataset.source} data · ${latest.dataset.observations} closes`} size="small" variant="outlined" sx={{ textTransform: 'capitalize' }} />
      </Stack>

      <RvSummaryCards cards={cards} />

      <Paper variant="outlined" sx={panelSx}>
        <RvLineChart title="Close-to-close volatility structure" subtitle="Annualized volatility from daily squared log returns against the underlying price" points={featuresQuery.data.points} mode="overview" />
      </Paper>

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><RvLineChart title="Forecast versus subsequent realization" subtitle={`${backtest.horizon_sessions}-session forecast annualized volatility compared with subsequent realized annualized volatility`} points={historyQuery.data.points} mode="forecast" horizonSessions={backtest.horizon_sessions} /></Paper></Grid>
        <Grid size={{ xs: 12, lg: 4 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><Typography variant="h6">Run history</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Persisted research executions</Typography><RvRunHistory runs={runsQuery.data.runs} /></Paper></Grid>
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
