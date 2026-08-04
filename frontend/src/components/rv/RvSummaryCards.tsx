import { ArrowDownwardRounded, ArrowUpwardRounded, InsightsRounded, SpeedRounded } from '@mui/icons-material'
import { Box, Card, CardContent, Chip, Grid, Stack, Typography } from '@mui/material'
import type { ReactNode } from 'react'

export type SummaryCard = {
  label: string
  value: string | number
  sublabel?: string
  tone?: 'neutral' | 'accent' | 'good' | 'warn'
}

type Props = { cards: SummaryCard[] }

const icons: ReactNode[] = [<InsightsRounded />, <SpeedRounded />, <ArrowDownwardRounded />, <ArrowUpwardRounded />]
const toneColor = { neutral: 'text.secondary', accent: 'primary.main', good: 'success.main', warn: 'warning.main' } as const

const RvSummaryCards = ({ cards }: Props): React.ReactElement => (
  <Grid container spacing={2}>
    {cards.map((card, index) => (
      <Grid key={card.label} size={{ xs: 12, sm: 6, lg: 2 }}>
        <Card variant="outlined" sx={{ height: '100%', bgcolor: 'background.default' }}>
          <CardContent sx={{ p: 2.25, '&:last-child': { pb: 2.25 } }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: 'flex-start', justifyContent: 'space-between' }}>
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 700 }}>{card.label}</Typography>
                <Typography variant="h5" sx={{ mt: 0.75, color: 'text.primary', fontVariantNumeric: 'tabular-nums' }}>{card.value}</Typography>
              </Box>
              <Box sx={{ color: toneColor[card.tone ?? 'neutral'], display: 'flex' }}>{icons[index % icons.length]}</Box>
            </Stack>
            {card.sublabel && <Chip label={card.sublabel} size="small" variant="outlined" sx={{ mt: 1.5, height: 22, maxWidth: '100%' }} />}
          </CardContent>
        </Card>
      </Grid>
    ))}
  </Grid>
)

export default RvSummaryCards
