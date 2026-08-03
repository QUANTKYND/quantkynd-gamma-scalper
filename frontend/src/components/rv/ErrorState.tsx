import { RefreshRounded } from '@mui/icons-material'
import { Alert, AlertTitle, Button } from '@mui/material'

type ErrorStateProps = { onRetry: () => void }

const ErrorState = ({ onRetry }: ErrorStateProps): React.ReactElement => (
  <Alert
    severity="error"
    action={<Button color="inherit" size="small" startIcon={<RefreshRounded />} onClick={onRetry}>Retry</Button>}
  >
    <AlertTitle>RV data is unavailable</AlertTitle>
    Check that the backend is running and try again.
  </Alert>
)

export default ErrorState
