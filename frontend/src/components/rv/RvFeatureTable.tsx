import { Chip, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Typography } from '@mui/material'
import { estimateFor, type RVFeatureRow } from '../../store/api/rvApi'

type Props = { rows: RVFeatureRow[] }
const pct = (value: number | undefined): string => value == null ? 'N/A' : `${(value * 100).toFixed(2)}%`
const numberText = (value: number | null): string => value == null ? 'N/A' : value.toFixed(2)
const chipColor = (regime: string): 'success' | 'warning' | 'default' => regime === 'low' ? 'success' : regime === 'high' ? 'warning' : 'default'

const RvFeatureTable = ({ rows }: Props): React.ReactElement => {
  if (rows.length === 0) return <Typography color="text.secondary">No feature rows yet.</Typography>
  return (
    <TableContainer sx={{ maxHeight: 480 }}>
      <Table stickyHeader size="small" aria-label="Latest close-to-close volatility features">
        <TableHead><TableRow>
          {['Date', 'Price', '1D Ann. Vol.', '5D Ann. Vol.', '21D Ann. Vol.', '63D Ann. Vol.', '5D / 21D Variance Ratio', '21D Vol. Z-score', 'Regime'].map((label) => <TableCell key={label} align={label === 'Date' || label === 'Regime' ? 'left' : 'right'}>{label}</TableCell>)}
        </TableRow></TableHead>
        <TableBody>
          {rows.map((row) => {
            const oneSession = estimateFor(row.estimates, 1)
            const fiveSession = estimateFor(row.estimates, 5)
            const twentyOneSession = estimateFor(row.estimates, 21)
            const sixtyThreeSession = estimateFor(row.estimates, 63)
            return (
              <TableRow hover key={row.date}>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{row.date}</TableCell>
                <TableCell align="right">{row.price.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</TableCell>
                <TableCell align="right">{pct(oneSession?.annualized_volatility)}</TableCell>
                <TableCell align="right">{pct(fiveSession?.annualized_volatility)}</TableCell>
                <TableCell align="right">{pct(twentyOneSession?.annualized_volatility)}</TableCell>
                <TableCell align="right">{pct(sixtyThreeSession?.annualized_volatility)}</TableCell>
                <TableCell align="right">{numberText(row.variance_ratio_5_21)}</TableCell>
                <TableCell align="right">{numberText(row.volatility_zscore_21)}</TableCell>
                <TableCell><Chip size="small" variant="outlined" color={chipColor(row.regime)} label={row.regime} sx={{ textTransform: 'capitalize' }} /></TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </TableContainer>
  )
}

export default RvFeatureTable
