import { useDeferredValue, useState } from 'react'
import { skipToken } from '@reduxjs/toolkit/query'
import { Autocomplete, Box, TextField, Typography } from '@mui/material'
import { useResolveInstrumentQuery, useSearchInstrumentsQuery, type InstrumentDefinition } from '../../store/api/instrumentsApi'

type Props = { instrumentKey: string; onSelect: (instrument: InstrumentDefinition) => void }

const groupLabel = (instrument: InstrumentDefinition): string => instrument.kind === 'index' ? 'Indices' : `${instrument.exchange} equities`

const InstrumentAutocomplete = ({ instrumentKey, onSelect }: Props): React.ReactElement => {
  const [inputValue, setInputValue] = useState('')
  const deferredQuery = useDeferredValue(inputValue.trim())
  const resolved = useResolveInstrumentQuery({ instrumentKey })
  const search = useSearchInstrumentsQuery(deferredQuery.length >= 2 ? {
    query: deferredQuery,
    exchanges: ['NSE', 'BSE'],
    kinds: ['index', 'equity'],
    limit: 20,
  } : skipToken)
  const selected = resolved.data ?? null
  const options = search.data?.items ?? (selected ? [selected] : [])

  return (
    <Autocomplete
      sx={{ width: { xs: '100%', sm: 420 } }}
      options={options}
      value={selected}
      loading={search.isFetching || resolved.isFetching}
      filterOptions={(items) => items}
      groupBy={groupLabel}
      getOptionLabel={(option) => option.trading_symbol}
      isOptionEqualToValue={(option, value) => option.instrument_key === value.instrument_key}
      noOptionsText={deferredQuery.length < 2 ? 'Type at least two characters' : search.isError ? 'Instrument search unavailable' : 'No matching instruments'}
      onInputChange={(_event, value) => setInputValue(value)}
      onChange={(_event, value) => { if (value) onSelect(value) }}
      renderOption={(props, option) => (
        <Box component="li" {...props} key={option.instrument_key} sx={{ display: 'block !important' }}>
          <Typography variant="body2" sx={{ fontWeight: 700 }}>{option.trading_symbol} · {option.exchange}</Typography>
          <Typography variant="caption" color="text.secondary">{option.name} · {option.kind} · {option.instrument_key}</Typography>
        </Box>
      )}
      renderInput={(params) => <TextField {...params} label="Instrument" placeholder="Search index or equity" />}
    />
  )
}

export default InstrumentAutocomplete
