import { Box, Divider, Grid, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material'
import type { RVBacktestSummary } from '../../store/api/rvApi'

type Props = { summary: RVBacktestSummary }

const RvBacktestTable = ({ summary }: Props): React.ReactElement => {
  const metrics = [
    ['MAE', `${(summary.metrics.mae * 100).toFixed(2)}%`],
    ['RMSE', `${(summary.metrics.rmse * 100).toFixed(2)}%`],
    ['Correlation', summary.metrics.correlation.toFixed(2)],
    ['Directional accuracy', `${(summary.metrics.directional_accuracy * 100).toFixed(1)}%`],
  ]
  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6">Backtest quality</Typography>
        <Typography variant="body2" color="text.secondary">{summary.model.toUpperCase()} · {summary.horizon_days}-day horizon · test {summary.test_start} to {summary.test_end}</Typography>
      </Box>
      <Grid container spacing={1.5}>
        {metrics.map(([label, value]) => <Grid key={label} size={{ xs: 6, md: 3 }}>
          <Box sx={{ borderLeft: '2px solid', borderColor: 'primary.main', pl: 1.5, py: 0.5 }}>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
            <Typography variant="subtitle1" sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</Typography>
          </Box>
        </Grid>)}
      </Grid>
      <Divider />
      <Typography variant="subtitle2">Regime breakdown</Typography>
      {summary.regime_metrics.length === 0 ? <Typography color="text.secondary">Not enough regime observations.</Typography> : (
        <Table size="small"><TableHead><TableRow><TableCell>Regime</TableCell><TableCell align="right">MAE</TableCell><TableCell align="right">RMSE</TableCell><TableCell align="right">Observations</TableCell></TableRow></TableHead>
          <TableBody>{summary.regime_metrics.map((row) => <TableRow key={row.regime}><TableCell sx={{ textTransform: 'capitalize' }}>{row.regime}</TableCell><TableCell align="right">{(row.mae * 100).toFixed(2)}%</TableCell><TableCell align="right">{(row.rmse * 100).toFixed(2)}%</TableCell><TableCell align="right">{row.count}</TableCell></TableRow>)}</TableBody>
        </Table>
      )}
    </Stack>
  )
}

export default RvBacktestTable
