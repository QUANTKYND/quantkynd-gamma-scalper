import { CheckCircleRounded, ScheduleRounded } from '@mui/icons-material'
import { Chip, Divider, List, ListItem, ListItemIcon, ListItemText, Typography } from '@mui/material'
import type { RVRunSummary } from '../../store/api/rvApi'

type Props = { runs: RVRunSummary[] }

const RvRunHistory = ({ runs }: Props): React.ReactElement => {
  if (runs.length === 0) return <Typography color="text.secondary">No persisted RV research runs yet. Execute the RV research command to create one.</Typography>
  return (
    <List disablePadding>
      {runs.map((run, index) => <ListItem key={run.run_id} divider={index < runs.length - 1} disableGutters sx={{ alignItems: 'flex-start', py: 1.5 }}>
        <ListItemIcon sx={{ minWidth: 36, mt: 0.5, color: run.status === 'complete' ? 'success.main' : 'text.secondary' }}>{run.status === 'complete' ? <CheckCircleRounded fontSize="small" /> : <ScheduleRounded fontSize="small" />}</ListItemIcon>
        <ListItemText primary={`${run.model.toUpperCase()} · ${run.horizon_sessions} sessions`} secondary={new Date(run.created_at).toLocaleString()} slotProps={{ primary: { variant: 'body2', sx: { fontWeight: 700 } }, secondary: { variant: 'caption' } }} />
        <Chip label={run.status} size="small" variant="outlined" color={run.status === 'complete' ? 'success' : 'default'} />
      </ListItem>)}
      <Divider sx={{ display: 'none' }} />
    </List>
  )
}

export default RvRunHistory
