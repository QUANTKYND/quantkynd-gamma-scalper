import { Box, Skeleton, Stack } from '@mui/material'

const LoadingState = (): React.ReactElement => (
  <Stack spacing={2} aria-label="Loading close-to-close volatility data">
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
      {[0, 1, 2, 3, 4, 5].map((item) => <Skeleton key={item} variant="rounded" height={116} sx={{ flex: 1 }} />)}
    </Stack>
    <Box><Skeleton variant="rounded" height={380} /></Box>
    <Skeleton variant="rounded" height={240} />
  </Stack>
)

export default LoadingState
