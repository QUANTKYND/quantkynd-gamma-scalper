import { useSearchParams } from 'react-router'
import RvDashboard from '../RvDashboard'

const DEFAULT_INSTRUMENT_KEY = 'NSE_INDEX|Nifty 50'

const RealisedVolatility = (): React.ReactElement => {
  const [searchParams, setSearchParams] = useSearchParams()
  const instrumentKey = searchParams.get('instrument_key') || DEFAULT_INSTRUMENT_KEY
  const selectInstrument = (selectedKey: string): void => {
    const next = new URLSearchParams(searchParams)
    next.set('instrument_key', selectedKey)
    setSearchParams(next)
  }
  return <RvDashboard key={instrumentKey} instrumentKey={instrumentKey} onSelectInstrument={selectInstrument} />
}

export default RealisedVolatility
