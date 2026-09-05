import type { FeatureSeries, LmEvent, SessionDetail, SessionSummary } from './types'

// Demo mode: a build can inline a session (window.__LIGHTMAN_DEMO__) so the UI runs with no server.
declare global {
  interface Window { __LIGHTMAN_DEMO__?: DemoBundle }
}
export interface DemoBundle {
  sessions: SessionSummary[]
  detail: Record<string, SessionDetail>
  events: Record<string, { events: LmEvent[] }>
  features: Record<string, Record<string, FeatureSeries>>
  thumbnails?: Record<string, Record<string, string>>
}

const demo = (): DemoBundle | undefined => window.__LIGHTMAN_DEMO__

async function getJson<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`)
  return (await r.json()) as T
}

export const api = {
  isDemo: () => Boolean(demo()),
  async sessions(): Promise<SessionSummary[]> {
    const d = demo()
    return d ? d.sessions : getJson('./api/sessions')
  },
  async session(id: string): Promise<SessionDetail> {
    const d = demo()
    return d ? d.detail[id] : getJson(`./api/sessions/${id}`)
  },
  async events(id: string): Promise<LmEvent[]> {
    const d = demo()
    return d ? d.events[id].events : (await getJson<{ events: LmEvent[] }>(`./api/sessions/${id}/events`)).events
  },
  async features(id: string, table: 'video' | 'audio', signals: string[], maxPoints = 2000): Promise<FeatureSeries> {
    const d = demo()
    if (d) return d.features[id][table]
    const q = new URLSearchParams({ table, signals: signals.join(','), max_points: String(maxPoints) })
    return getJson(`./api/sessions/${id}/features?${q}`)
  },
  thumbnail(id: string, eventId: string): string | null {
    const d = demo()
    if (d) return d.thumbnails?.[id]?.[eventId] ?? null
    return `./api/sessions/${id}/thumbnails/${eventId}`
  },
  mediaUrl(id: string, hasMedia: boolean): string | null {
    return !demo() && hasMedia ? `./api/sessions/${id}/media` : null
  },
}

export function tc(us: number): string {
  const ms = Math.floor(us / 1000)
  const h = Math.floor(ms / 3600000)
  const m = Math.floor((ms % 3600000) / 60000)
  const s = Math.floor((ms % 60000) / 1000)
  const mm = ms % 1000
  const pad = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${pad(h)}:${pad(m)}:${pad(s)}.${pad(mm, 3)}`
}
