import { API_BASE } from './base'

export const marketStateWebSocketUrl = (instrumentKey: string): string => {
  const base = new URL(API_BASE, window.location.origin)
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:'
  base.pathname = `${base.pathname.replace(/\/$/, '')}/streams/market-state`
  base.search = new URLSearchParams({ instrument_key: instrumentKey }).toString()
  return base.toString()
}
