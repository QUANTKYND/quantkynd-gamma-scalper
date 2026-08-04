import { AutoGraphRounded, ScienceRounded } from '@mui/icons-material'
import { Alert, Box, Chip, Grid, Paper, Stack, Typography } from '@mui/material'
import BrokerConnection from '../components/BrokerConnection'
import InstrumentAutocomplete from '../components/instruments/InstrumentAutocomplete'
import ErrorState from '../components/rv/ErrorState'
import LoadingState from '../components/rv/LoadingState'
import RvBacktestTable from '../components/rv/RvBacktestTable'
import RvFeatureTable from '../components/rv/RvFeatureTable'
import RvLineChart from '../components/rv/RvLineChart'
import RvRunHistory from '../components/rv/RvRunHistory'
import RvSummaryCards, { type SummaryCard } from '../components/rv/RvSummaryCards'
import { useGetMarketStateQuery } from '../store/api/marketApi'
import type { InstrumentDefinition } from '../store/api/instrumentsApi'
import { estimateFor, useGetBacktestQuery, useGetFeaturesQuery, useGetHistoryQuery, useGetLatestQuery, useGetRunsQuery } from '../store/api/rvApi'

type Props = { instrumentKey: string; onSelectInstrument: (instrumentKey: string) => void }
const panelSx = { p: { xs: 2, md: 2.5 }, borderColor: 'divider', backgroundImage: 'none', overflow: 'hidden' }
const pct = (value: number | null | undefined): string => value == null ? 'N/A' : `${(value * 100).toFixed(2)}%`
const numberText = (value: number | null | undefined): string => value == null ? 'N/A' : value.toFixed(2)
const titleCase = (value: string): string => value[0].toUpperCase() + value.slice(1).replaceAll('_', ' ')
const dateTime = (value: string | null | undefined): string => value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)) : 'N/A'

const RvDashboard = ({ instrumentKey, onSelectInstrument }: Props): React.ReactElement => {
  const args = { instrumentKey }
  const latestQuery = useGetLatestQuery(args)
  const featuresQuery = useGetFeaturesQuery(args)
  const backtestQuery = useGetBacktestQuery(args)
  const runsQuery = useGetRunsQuery()
  const historyQuery = useGetHistoryQuery(args)
  const marketQuery = useGetMarketStateQuery(args)
  const required = [latestQuery, featuresQuery, backtestQuery, runsQuery, historyQuery]
  const isLoading = required.some((query) => query.isLoading)
  const hasError = required.some((query) => query.isError)
  const retry = (): void => { required.forEach((query) => { void query.refetch() }) }
  const select = (instrument: InstrumentDefinition): void => onSelectInstrument(instrument.instrument_key)

  return (
    <Stack spacing={2.5}>
      <BrokerConnection />
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ justifyContent: 'space-between', alignItems: { xs: 'stretch', md: 'flex-end' } }}>
        <Box>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}><AutoGraphRounded color="primary" /><Typography variant="h4" component="h1">Close-to-Close Volatility Research</Typography></Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>Daily close-to-close squared log returns. A live LTP is only an unfinished session-close proxy, not intraday realized volatility.</Typography>
        </Box>
        <InstrumentAutocomplete instrumentKey={instrumentKey} onSelect={select} />
      </Stack>
      {isLoading && <LoadingState />}
      {hasError && <><Alert severity="error">Connect Upstox to search instruments and load genuine market data. Live requests never fall back to synthetic prices.</Alert><ErrorState onRetry={retry} /></>}
      {!isLoading && !hasError && latestQuery.data && featuresQuery.data && backtestQuery.data && runsQuery.data && historyQuery.data && (
        <DashboardData
          latest={marketQuery.data?.rvLatest ?? latestQuery.data}
          features={marketQuery.data?.rvFeatures ?? featuresQuery.data}
          backtest={backtestQuery.data}
          runs={runsQuery.data.runs}
          history={historyQuery.data.points}
          market={marketQuery.data ?? null}
        />
      )}
    </Stack>
  )
}

type DashboardDataProps = {
  latest: NonNullable<ReturnType<typeof useGetLatestQuery>['data']>
  features: NonNullable<ReturnType<typeof useGetFeaturesQuery>['data']>
  backtest: NonNullable<ReturnType<typeof useGetBacktestQuery>['data']>
  runs: NonNullable<ReturnType<typeof useGetRunsQuery>['data']>['runs']
  history: NonNullable<ReturnType<typeof useGetHistoryQuery>['data']>['points']
  market: ReturnType<typeof useGetMarketStateQuery>['data'] | null
}

const DashboardData = ({ latest, features, backtest, runs, history, market }: DashboardDataProps): React.ReactElement => {
  const oneSession = estimateFor(latest.estimates, 1)
  const fiveSession = estimateFor(latest.estimates, 5)
  const twentyOneSession = estimateFor(latest.estimates, 21)
  const sixtyThreeSession = estimateFor(latest.estimates, 63)
  const statusLabel = latest.live.is_provisional ? latest.live.freshness === 'stale' ? 'Live estimate stale' : 'Live provisional estimate' : 'Finalized close-to-close estimate'
  const cards: SummaryCard[] = [
    { label: '1-session annualized volatility', value: pct(oneSession?.annualized_volatility), sublabel: `As of ${latest.as_of}`, tone: 'neutral' },
    { label: '5-session annualized volatility', value: pct(fiveSession?.annualized_volatility), sublabel: latest.live.is_provisional ? 'Includes unfinished session proxy' : 'Trailing finalized sessions', tone: 'accent' },
    { label: '21-session annualized volatility', value: pct(twentyOneSession?.annualized_volatility), sublabel: 'Close-to-close estimator', tone: 'accent' },
    { label: '63-session annualized volatility', value: pct(sixtyThreeSession?.annualized_volatility), sublabel: 'Finalized history plus labelled overlay', tone: 'neutral' },
    { label: '5D / 21D annualized variance ratio', value: numberText(latest.variance_ratio_5_21), sublabel: latest.variance_ratio_5_21 != null && latest.variance_ratio_5_21 > 1 ? 'Short variance elevated' : 'Short variance contained', tone: latest.variance_ratio_5_21 != null && latest.variance_ratio_5_21 > 1 ? 'warn' : 'good' },
    { label: 'Volatility regime', value: titleCase(latest.regime), sublabel: `21D z-score ${numberText(latest.volatility_zscore_21)}`, tone: latest.regime === 'high' ? 'warn' : latest.regime === 'low' ? 'good' : 'neutral' },
  ]
  const quote = market?.quote
  const status = market?.status
  const absoluteChange = quote?.ltp != null && quote.previous_close != null ? quote.ltp - quote.previous_close : null
  const percentageChange = absoluteChange != null && quote?.previous_close ? absoluteChange / quote.previous_close : null

  return (
    <Stack spacing={2.5}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ justifyContent: 'space-between', alignItems: { xs: 'flex-start', sm: 'center' } }}>
        <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap' }}>
          <Chip icon={<ScienceRounded />} label={`Upstox historical · ${latest.dataset.observations} finalized closes`} size="small" variant="outlined" />
          {latest.live.is_provisional && <Chip label="Live provisional overlay" color={latest.live.freshness === 'stale' ? 'warning' : 'info'} size="small" />}
        </Stack>
        <Typography variant="body2" color={latest.live.freshness === 'stale' ? 'warning.main' : 'text.secondary'}>{statusLabel}</Typography>
      </Stack>

      <Paper variant="outlined" sx={panelSx}>
        <Grid container spacing={2}>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Upstox authentication" value={status?.authentication_state ?? 'unknown'} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Provider transport" value={status?.transport_state ?? 'connecting'} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Subscription" value={status?.subscription_state ?? 'subscribing'} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Feed quality" value={quote?.freshness ?? latest.live.freshness} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Market" value={quote?.market_status ?? status?.market_status ?? 'unknown'} /></Grid>
          <Grid size={{ xs: 6, md: 2 }}><Status label="Last tick" value={dateTime(quote?.last_trade_at)} /></Grid>
        </Grid>
        <Grid container spacing={2} sx={{ mt: 1 }}>
          <Grid size={{ xs: 6, md: 2.4 }}><Status label="LTP" value={quote?.ltp?.toLocaleString('en-IN', { maximumFractionDigits: 2 }) ?? 'Awaiting tick'} /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Status label="Absolute change" value={numberText(absoluteChange)} /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Status label="Percentage change" value={pct(percentageChange)} /></Grid>
          <Grid size={{ xs: 6, md: 2.4 }}><Status label="Previous close" value={quote?.previous_close?.toLocaleString('en-IN', { maximumFractionDigits: 2 }) ?? 'N/A'} /></Grid>
          <Grid size={{ xs: 12, md: 2.4 }}><Status label="Last received" value={dateTime(quote?.received_at)} /></Grid>
        </Grid>
      </Paper>

      {latest.live.is_provisional && <Alert severity={latest.live.freshness === 'stale' ? 'warning' : 'info'}>{latest.live.freshness === 'stale' ? `Live estimate stale. Last received at ${dateTime(latest.live.received_at)}.` : 'Uses current LTP as an unfinished session-close proxy.'}</Alert>}
      {!market && <Alert severity="warning">Historical data loaded. Live feed unavailable.</Alert>}
      <RvSummaryCards cards={cards} />
      <Paper variant="outlined" sx={panelSx}><RvLineChart title="Close-to-close volatility structure" subtitle="Final point is explicitly marked when provisional" points={features.points} mode="overview" /></Paper>
      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><RvLineChart title="Forecast versus subsequent realization" subtitle={`${backtest.horizon_sessions}-session evaluation uses finalized closes only`} points={history} mode="forecast" horizonSessions={backtest.horizon_sessions} /></Paper></Grid>
        <Grid size={{ xs: 12, lg: 4 }}><Paper variant="outlined" sx={{ ...panelSx, height: '100%' }}><Typography variant="h6">Run history</Typography><Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>Persisted finalized research executions</Typography><RvRunHistory runs={runs} /></Paper></Grid>
      </Grid>
      <Paper variant="outlined" sx={panelSx}><RvBacktestTable summary={backtest} /></Paper>
      <Paper variant="outlined" sx={{ ...panelSx, p: 0 }}><Box sx={{ px: { xs: 2, md: 2.5 }, pt: 2.5, pb: 1.5 }}><Typography variant="h6">Feature monitor</Typography><Typography variant="body2" color="text.secondary">Finalized observations plus at most one provisional row</Typography></Box><RvFeatureTable rows={features.points.slice(-20).reverse()} /></Paper>
    </Stack>
  )
}

const Status = ({ label, value }: { label: string; value: string }): React.ReactElement => <Box><Typography variant="caption" color="text.secondary">{label}</Typography><Typography variant="body2" sx={{ fontWeight: 700, textTransform: 'capitalize' }}>{value.replaceAll('_', ' ')}</Typography></Box>

export default RvDashboard
