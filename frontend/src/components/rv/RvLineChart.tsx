import { Box, Stack, Typography, useTheme } from '@mui/material'
import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { RVChartPoint } from '../../store/api/rvApi'

type Props = {
  title: string
  subtitle: string
  points: RVChartPoint[]
  mode: 'overview' | 'forecast'
}

const compactDate = (value: string): string => new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(new Date(`${value}T00:00:00`))
const percent = (value: number): string => `${(value * 100).toFixed(1)}%`

const RvLineChart = ({ title, subtitle, points, mode }: Props): React.ReactElement => {
  const theme = useTheme()
  if (points.length === 0) return <Typography color="text.secondary">No chart observations yet.</Typography>

  return (
    <Box>
      <Stack sx={{ mb: 2 }}>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="body2" color="text.secondary">{subtitle}</Typography>
      </Stack>
      <Box sx={{ width: '100%', height: { xs: 300, md: 360 } }}>
        <ResponsiveContainer>
          <ComposedChart data={points} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme.palette.divider} />
            <XAxis dataKey="date" tickFormatter={compactDate} minTickGap={36} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />
            <YAxis yAxisId="rv" tickFormatter={percent} width={50} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />
            {mode === 'overview' && <YAxis yAxisId="price" orientation="right" width={64} tickFormatter={(value: number) => value.toLocaleString('en-IN', { maximumFractionDigits: 0 })} tick={{ fontSize: 11, fill: theme.palette.text.secondary }} axisLine={false} tickLine={false} />}
            <Tooltip
              labelFormatter={(label) => compactDate(String(label))}
              formatter={(value, name) => [name === 'Price' ? Number(value).toLocaleString('en-IN', { maximumFractionDigits: 2 }) : percent(Number(value)), name]}
              contentStyle={{ borderRadius: 6, borderColor: theme.palette.divider, background: theme.palette.background.paper }}
            />
            <Legend iconType="plainline" wrapperStyle={{ fontSize: 12, paddingTop: 12 }} />
            {mode === 'overview' ? (
              <>
                <Line yAxisId="price" type="monotone" dataKey="price" name="Price" stroke={theme.palette.text.secondary} strokeWidth={1.5} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="rv_5d" name="5d RV" stroke={theme.palette.warning.main} strokeWidth={2} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="rv_21d" name="21d RV" stroke={theme.palette.primary.main} strokeWidth={2.25} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="rv_63d" name="63d RV" stroke={theme.palette.success.main} strokeWidth={1.75} dot={false} />
              </>
            ) : (
              <>
                <Line yAxisId="rv" type="monotone" dataKey="forecast_5d" name="EWMA forecast" stroke={theme.palette.primary.main} strokeWidth={2.25} dot={false} />
                <Line yAxisId="rv" type="monotone" dataKey="actual_forward_5d" name="Forward RV" stroke={theme.palette.warning.main} strokeWidth={2} dot={false} />
              </>
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  )
}

export default RvLineChart
