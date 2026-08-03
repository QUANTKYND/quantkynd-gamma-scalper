import { Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'
import type { RVFeatureRow } from '../../store/api/rvApi'

type Props = { rows: RVFeatureRow[] }
const pct = (value: number): string => `${(value * 100).toFixed(2)}%`
const chipColor = (regime: string): 'success' | 'warning' | 'default' => regime === 'low' ? 'success' : regime === 'high' ? 'warning' : 'default'

const RvFeatureTable = ({ rows }: Props): React.ReactElement => {
  if (rows.length === 0) return <Typography color="text.secondary">No feature rows yet.</Typography>
  return (
    <TableContainer sx={{ maxHeight: 480 }}>
      <Table stickyHeader size="small" aria-label="Latest realized volatility features">
        <TableHead><TableRow>
          {['Date', 'Price', '1d RV', '5d RV', '21d RV', '63d RV', '5 / 21', 'Z-score', 'Regime'].map((label) => <TableCell key={label} align={label === 'Date' || label === 'Regime' ? 'left' : 'right'}>{label}</TableCell>)}
        </TableRow></TableHead>
        <TableBody>
          {rows.map((row) => <TableRow hover key={row.date}>
            <TableCell sx={{ whiteSpace: 'nowrap' }}>{row.date}</TableCell>
            <TableCell align="right">{row.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</TableCell>
            <TableCell align="right">{pct(row.rv_1d)}</TableCell>
            <TableCell align="right">{pct(row.rv_5d)}</TableCell>
            <TableCell align="right">{pct(row.rv_21d)}</TableCell>
            <TableCell align="right">{pct(row.rv_63d)}</TableCell>
            <TableCell align="right">{row.rv_ratio_5_21.toFixed(2)}</TableCell>
            <TableCell align="right">{row.rv_zscore_21.toFixed(2)}</TableCell>
            <TableCell><Chip size="small" variant="outlined" color={chipColor(row.regime)} label={row.regime} sx={{ textTransform: 'capitalize' }} /></TableCell>
          </TableRow>)}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

export default RvFeatureTable
