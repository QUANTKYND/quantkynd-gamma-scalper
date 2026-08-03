import { AccountBalanceRounded, LinkOffRounded, LoginRounded, RefreshRounded } from '@mui/icons-material'
import { Alert, Box, Button, Chip, IconButton, Paper, Stack, Tooltip, Typography } from '@mui/material'
import { useEffect } from 'react'
import { useSearchParams } from 'react-router'
import { getUpstoxLoginUrl, useDisconnectAuthMutation, useGetAuthStatusQuery } from '../../store/api/authApi'

const panelSx = { p: { xs: 2, md: 2.5 }, borderColor: 'divider', backgroundImage: 'none' }

const BrokerConnection = (): React.ReactElement => {
  const [searchParams] = useSearchParams()
  const authResult = searchParams.get('auth')
  const authReason = searchParams.get('reason')

  const statusQuery = useGetAuthStatusQuery()
  const { refetch: refetchStatus } = statusQuery
  const [disconnectAuth, disconnectMutation] = useDisconnectAuthMutation()

  useEffect(() => {
    if (authResult) {
      void refetchStatus()
    }
  }, [authResult, refetchStatus])

  const status = statusQuery.isError ? 'error' : statusQuery.data?.status ?? 'disconnected'
  const connected = status === 'connected'
  const broker = statusQuery.data?.broker ?? 'upstox'
  const chipColor = connected ? 'success' : status === 'error' ? 'error' : 'default'
  const chipLabel = connected ? 'connected' : status === 'error' ? 'error' : 'disconnected'

  const connect = (): void => {
    window.location.href = getUpstoxLoginUrl()
  }

  const disconnect = (): void => {
    void disconnectAuth()
  }

  return (
    <Stack spacing={1.25}>
      {authResult === 'success' && <Alert severity="success">Connected to Upstox</Alert>}
      {authResult === 'error' && <Alert severity="error">Upstox connection failed{authReason ? `: ${authReason.replaceAll('_', ' ')}` : ''}</Alert>}
      {disconnectMutation.isError && <Alert severity="error">Could not disconnect Upstox</Alert>}

      <Paper variant="outlined" sx={panelSx}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ alignItems: { xs: 'stretch', sm: 'center' }, justifyContent: 'space-between' }}>
          <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center', minWidth: 0 }}>
            <Box sx={{ width: 36, height: 36, display: 'grid', placeItems: 'center', borderRadius: 1, bgcolor: 'primary.main', color: 'primary.contrastText', flex: '0 0 auto' }}>
              <AccountBalanceRounded fontSize="small" />
            </Box>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.2 }}>Broker connection</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ textTransform: 'capitalize' }}>{broker}</Typography>
            </Box>
          </Stack>

          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', justifyContent: { xs: 'space-between', sm: 'flex-end' }, flexWrap: 'wrap' }}>
            <Chip label={chipLabel} color={chipColor} size="small" variant={connected ? 'filled' : 'outlined'} sx={{ textTransform: 'capitalize' }} />
            <Tooltip title="Refresh broker status">
              <IconButton aria-label="Refresh broker status" size="small" onClick={() => { void refetchStatus() }} disabled={statusQuery.isFetching}>
                <RefreshRounded fontSize="small" />
              </IconButton>
            </Tooltip>
            {connected ? (
              <Button variant="outlined" color="error" startIcon={<LinkOffRounded />} onClick={disconnect} disabled={disconnectMutation.isLoading}>Disconnect</Button>
            ) : (
              <Button variant="contained" startIcon={<LoginRounded />} onClick={connect}>Connect to Upstox</Button>
            )}
          </Stack>
        </Stack>
      </Paper>
    </Stack>
  )
}

export default BrokerConnection
