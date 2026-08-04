import { Box, Stack, Typography, useTheme } from '@mui/material'
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { estimateFor, type RVFeatureRow, type RVForecastHistoryPoint } from '../../store/api/rvApi'

type BaseProps = {
  title: string
  subtitle: string
}

type OverviewProps = BaseProps & {
  points: RVFeatureRow[]
  mode: 'overview'
}

type ForecastProps = BaseProps & {
  points: RVForecastHistoryPoint[]
  mode: 'forecast'
  horizonSessions: number
}

type Props = OverviewProps | ForecastProps

type ChartDatum = {
  date: string
  price?: number
  annualized_volatility_5d?: number
  annualized_volatility_21d?: number
  annualized_volatility_63d?: number
  target_start?: string
  target_end?: string
  forecast_annualized_volatility?: number
  actual_annualized_volatility?: number
  provisional?: boolean
  provisionalPrice?: number
  provisionalVolatility?: number
}

type TooltipEntry = {
  name?: string
  value?: number | string
  color?: string
  payload?: ChartDatum
}

type ChartTooltipProps = {
  active?: boolean
  label?: string | number
  payload?: TooltipEntry[]
  mode: Props['mode']
}

const compactDate = (value: string): string => new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(new Date(`${value}T00:00:00`))
const percent = (value: number): string => `${(value * 100).toFixed(1)}%`
const priceText = (value: number): string => value.toLocaleString('en-IN', { maximumFractionDigits: 0 })

const overviewData = (points: RVFeatureRow[]): ChartDatum[] => points.map((point) => {
  const twentyOne = estimateFor(point.estimates, 21)?.annualized_volatility
  return {
    date: point.date,
    price: point.price,
    annualized_volatility_5d: estimateFor(point.estimates, 5)?.annualized_volatility,
    annualized_volatility_21d: twentyOne,
    annualized_volatility_63d: estimateFor(point.estimates, 63)?.annualized_volatility,
    provisional: point.is_provisional,
    provisionalPrice: point.is_provisional ? point.price : undefined,
    provisionalVolatility: point.is_provisional ? twentyOne : undefined,
  }
})

const forecastData = (points: RVForecastHistoryPoint[]): ChartDatum[] => points.map((point) => ({
  date: point.origin_date,
  target_start: point.target_start,
  target_end: point.target_end,
  forecast_annualized_volatility: point.forecast_annualized_volatility,
  actual_annualized_volatility: point.actual_annualized_volatility,
}))

const ChartTooltip = ({ active, label, payload, mode }: ChartTooltipProps): React.ReactElement | null => {
  if (!active || !payload || payload.length === 0) return null
  const datum = payload[0].payload
  const hasForecastDatum = mode === 'forecast'
    && datum?.target_start != null
    && datum.target_end != null
    && datum.forecast_annualized_volatility != null
    && datum.actual_annualized_volatility != null
  return (
    <Box sx={{ p: 1.25, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider', borderRadius: 1, boxShadow: 2, minWidth: 220 }}>
      {hasForecastDatum ? (
        <Stack spacing={0.5}>
          <Typography variant="caption" color="text.secondary">Forecast origin</Typography>
          <Typography variant="body2">{datum.date}</Typography>
          <Typography variant="caption" color="text.secondary">Target start</Typography>
          <Typography variant="body2">{datum.target_start}</Typography>
          <Typography variant="caption" color="text.secondary">Target end</Typography>
          <Typography variant="body2">{datum.target_end}</Typography>
          <Typography variant="caption" color="text.secondary">Forecast annualized volatility</Typography>
          <Typography variant="body2">{percent(datum.forecast_annualized_volatility!)}</Typography>
          <Typography variant="caption" color="text.secondary">Actual annualized volatility</Typography>
          <Typography variant="body2">{percent(datum.actual_annualized_volatility!)}</Typography>
        </Stack>
      ) : (
        <Stack spacing={0.5}>
          <Typography variant="caption" color="text.secondary">Date</Typography>
          <Typography variant="body2">{String(label)}</Typography>
          {datum?.provisional && <Typography variant="caption" color="info.main">Provisional unfinished-session point</Typography>}
          {payload.map((entry) => {
            if (entry.value == null || entry.name == null) return null
            const value = entry.name === 'Price' ? priceText(Number(entry.value)) : percent(Number(entry.value))
            return <Typography key={entry.name} variant="body2" sx={{ color: entry.color }}>{entry.name}: {value}</Typography>
          })}
        </Stack>
      )}
    </Box>
  )
}

const RvLineChart = (props: Props): React.ReactElement => {
  const theme = useTheme()
  const chartPoints = props.mode === 'overview' ? overviewData(props.points) : forecastData(props.points)
  if (chartPoints.length === 0) return <Typography color="text.secondary">No chart observations yet.</Typography>

  return (
    <Box>
      <Stack sx={{ mb: 2 }}>
        <Typography variant="h6">{props.title}</Typography>
        <Typography variant="body2" color="text.secondary">{props.subtitle}</Typography>
      </Stack>
      <Box sx={{ width: '100%', height: { xs: 300, md: 360 } }}>
        <ResponsiveContainer>
          <ComposedChart data={chartPoints} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme.palette.divider} />
            <XAxis dataKey="date" tickFormatter={compactDate} minTickGap={36} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="rv" tickFormatter={percent} width={50} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />
            {props.mode === 'overview' && <YAxis yAxisId="price" orientation="right" width={64} tickFormatter={priceText} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />}
            <Tooltip content={<ChartTooltip mode={props.mode} />} />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
            {props.mode === 'overview' ? (
              <>
                <Line yAxisId="price" type="monotone" dataKey="price" name="Price" stroke={theme.palette.text.secondary} strokeWidth={1.5} dot={false} isAnimationActive={false} />
                <Line yAxisId="rv" type="monotone" dataKey="annualized_volatility_5d" name="5-session annualized volatility" stroke={theme.palette.warning.main} strokeWidth={2} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="annualized_volatility_21d" name="21-session annualized volatility" stroke={theme.palette.primary.main} strokeWidth={2.25} dot={false} isAnimationActive={false} />
                <Line yAxisId="rv" type="monotone" dataKey="annualized_volatility_63d" name="63-session annualized volatility" stroke={theme.palette.success.main} strokeWidth={1.75} dot={false} />
                <Line yAxisId="price" dataKey="provisionalPrice" name="Provisional price" stroke="none" dot={{ r: 5, fill: theme.palette.info.main, stroke: theme.palette.info.contrastText }} isAnimationActive={false} legendType="none" />
                <Line yAxisId="rv" dataKey="provisionalVolatility" name="Provisional 21-session volatility" stroke="none" dot={{ r: 5, fill: theme.palette.info.main, stroke: theme.palette.info.contrastText }} isAnimationActive={false} legendType="none" />
              </>
            ) : (
              <>
                <Line yAxisId="rv" type="monotone" dataKey="forecast_annualized_volatility" name={`${props.horizonSessions}-session forecast annualized volatility`} stroke={theme.palette.primary.main} strokeWidth={2.25} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="actual_annualized_volatility" name={`${props.horizonSessions}-session subsequent realization`} stroke={theme.palette.warning.main} strokeWidth={2} dot={false} />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  )
}

export default RvLineChart
