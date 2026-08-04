import { Box, Divider, Grid, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import type { RVBacktestMetrics, RVBacktestSummary } from '../../store/api/rvApi'

type Props = { summary: RVBacktestSummary }

const decimal = (value: number | null): string => value == null ? 'N/A' : value.toFixed(6)
const pct = (value: number | null): string => value == null ? 'N/A' : `${(value * 100).toFixed(2)}%`
const score = (value: number | null): string => value == null ? 'N/A' : value.toFixed(2)

const metricItems = (
  metrics: RVBacktestMetrics,
  formatter: (value: number | null) => string,
): Array<[string, string]> => [
  ['MAE', formatter(metrics.mae)],
  ['RMSE', formatter(metrics.rmse)],
  ['Correlation', score(metrics.correlation)],
  ['Change direction accuracy', pct(metrics.change_direction_accuracy)],
  ['Observations', metrics.n_obs.toLocaleString()],
]

const MetricGroup = ({ title, metrics, formatter }: { title: string; metrics: RVBacktestMetrics; formatter: (value: number | null) => string }): React.ReactElement => (
  <Stack spacing={1}>
    <Typography variant="subtitle2">{title}</Typography>
    <Grid container spacing={1.5}>
      {metricItems(metrics, formatter).map(([label, value]) => (
        <Grid key={`${title}-${label}`} size={{ xs: 6, md: label === 'Observations' ? 4 : 2 }}>
          <Box sx={{ borderLeft: '2px solid', borderColor: 'primary.main', pl: 1.5, py: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
          </Box>
        </Grid>
      ))}
    </Grid>
  </Stack>
)

const RvBacktestTable = ({ summary }: Props): React.ReactElement => (
  <Stack spacing={2}>
    <Box>
      <Typography variant="h6">Backtest quality</Typography>
      <Typography variant="body2" color="text.secondary">{summary.model.toUpperCase()} · {summary.horizon_sessions}-session horizon · {summary.evaluation_start} to {summary.evaluation_end}</Typography>
    </Box>
    <Grid container spacing={1.5}>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}><Typography variant="body2"><strong>Evaluation:</strong> Sequential</Typography></Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}><Typography variant="body2"><strong>Metric target spacing:</strong> {summary.metric_stride} sessions</Typography></Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}><Typography variant="body2"><strong>Overlapping chart points:</strong> {summary.overlapping_chart_targets ? 'Yes' : 'No'}</Typography></Grid>
      <Grid size={{ xs: 12, sm: 6, md: 3 }}><Typography variant="body2"><strong>Overlapping metric targets:</strong> {summary.overlapping_metric_targets ? 'Yes' : 'No'}</Typography></Grid>
    </Grid>
    <MetricGroup title="Annualized variance metrics" metrics={summary.variance_metrics} formatter={decimal} />
    <MetricGroup title="Annualized volatility metrics" metrics={summary.volatility_metrics} formatter={pct} />
    <Divider />
    <Typography variant="subtitle2">Regime breakdown</Typography>
    {summary.regime_metrics.length === 0 ? <Typography color="text.secondary">Not enough regime observations.</Typography> : (
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Regime</TableCell>
            <TableCell align="right">Variance RMSE</TableCell>
            <TableCell align="right">Volatility RMSE</TableCell>
            <TableCell align="right">Observations</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>{summary.regime_metrics.map((row) => (
          <TableRow key={row.regime}>
            <TableCell sx={{ textTransform: 'capitalize' }}>{row.regime}</TableCell>
            <TableCell align="right">{decimal(row.variance_metrics.rmse)}</TableCell>
            <TableCell align="right">{pct(row.volatility_metrics.rmse)}</TableCell>
            <TableCell align="right">{row.volatility_metrics.n_obs}</TableCell>
          </TableRow>
        ))}</TableBody>
      </Table>
    )}
  </Stack>
)

export default RvBacktestTable
