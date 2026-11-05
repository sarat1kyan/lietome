import type { ClientRow, Note, Settings, CompareResult, FeatureSeries, FrameSnapshot, History, LmEvent, PulseSeries, Range, SessionDetail, SessionSummary } from './types'

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
  async validation(subject: string): Promise<any> {
    if (demo()) return { n_items: 0 }
    return getJson(`./api/subjects/${encodeURIComponent(subject)}/validation`)
  },
  async system(): Promise<any> {
    if (demo()) return null
    return getJson('./api/system')
  },
  async analyze(file: File, client: string, consent: unknown, au = true): Promise<string> {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('client', client)
    fd.append('consent', JSON.stringify(consent))
    fd.append('au', String(au))
    const r = await fetch('./api/analyze', { method: 'POST', body: fd })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `upload failed: ${r.status}`)
    return (await r.json()).job_id
  },
  async job(id: string): Promise<{ state: string; session_id?: string; error?: string }> {
    return getJson(`./api/jobs/${id}`)
  },
  async settings(): Promise<Settings> {
    if (demo()) return { profile: 'practice', require_consent: true, onboarded: true, practitioner: '' }
    return getJson('./api/settings')
  },
  async saveSettings(s: Partial<Settings>): Promise<Settings> {
    const r = await fetch('./api/settings', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(s) })
    if (!r.ok) throw new Error(`settings: ${r.status}`)
    return r.json()
  },
  async clients(): Promise<ClientRow[]> {
    if (demo()) return []
    return getJson('./api/clients')
  },
  async saveClient(code: string, body: { label?: string; note?: string }): Promise<void> {
    const r = await fetch(`./api/clients/${encodeURIComponent(code)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? `client: ${r.status}`)
  },
  exportClientUrl(code: string): string { return `./api/clients/${encodeURIComponent(code)}/export` },
  async eraseClient(code: string): Promise<{ sessions_removed: string[] }> {
    const r = await fetch(`./api/clients/${encodeURIComponent(code)}?confirm=${encodeURIComponent(code)}`, { method: 'DELETE' })
    if (!r.ok) throw new Error(`erase: ${r.status}`)
    return r.json()
  },
  async practice(id: string): Promise<any> {
    if (demo()) return { status: 'unavailable' }
    return getJson(`./api/sessions/${id}/practice`)
  },
  async trends(code: string): Promise<{ sessions: any[]; measures: string[] }> {
    if (demo()) return { sessions: [], measures: [] }
    return getJson(`./api/clients/${encodeURIComponent(code)}/trends`)
  },
  async notes(id: string): Promise<Note[]> {
    if (demo()) return []
    return (await getJson<{ notes: Note[] }>(`./api/sessions/${id}/notes`)).notes
  },
  async addNote(id: string, text: string, tUs: number | null): Promise<Note> {
    const r = await fetch(`./api/sessions/${id}/notes`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, t_us: tUs }) })
    if (!r.ok) throw new Error(`note: ${r.status}`)
    return r.json()
  },
  async editNote(id: string, noteId: string, text: string, tUs: number | null): Promise<Note> {
    const r = await fetch(`./api/sessions/${id}/notes/${noteId}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text, t_us: tUs }) })
    if (!r.ok) throw new Error(`note: ${r.status}`)
    return r.json()
  },
  async deleteNote(id: string, noteId: string): Promise<void> {
    await fetch(`./api/sessions/${id}/notes/${noteId}`, { method: 'DELETE' })
  },
  async uploadRecording(id: string, blob: Blob, offsetUs: number): Promise<void> {
    const fd = new FormData()
    fd.append('file', blob, blob.type.includes('mp4') ? 'recording.mp4' : 'recording.webm')
    fd.append('offset_us', String(offsetUs))
    const r = await fetch(`./api/sessions/${id}/media`, { method: 'POST', body: fd })
    if (!r.ok) throw new Error(`upload failed: ${r.status}`)
  },
  async transcript(id: string): Promise<any> {
    if (demo()) return { status: 'none' }
    return getJson(`./api/sessions/${id}/transcript`)
  },
  async mediaInfo(id: string): Promise<{ file: string; offset_us: number } | null> {
    if (demo()) return null
    try { return await getJson(`./api/sessions/${id}/media-info`) } catch { return null }
  },
  async history(id: string): Promise<History> {
    if (demo()) return { subject_id: 'demo', sessions: [], shifts: [] }
    return getJson(`./api/sessions/${id}/history`)
  },
  async compare(id: string, a: Range, b: Range): Promise<CompareResult> {
    const q = new URLSearchParams({ a0: String(Math.round(a[0])), a1: String(Math.round(a[1])), b0: String(Math.round(b[0])), b1: String(Math.round(b[1])) })
    return getJson(`./api/sessions/${id}/compare?${q}`)
  },
  async pulse(id: string): Promise<PulseSeries> {
    if (demo()) return { t_us: [], bpm: [], snr_db: [] }
    return getJson(`./api/sessions/${id}/pulse`)
  },
  async frame(id: string, tUs: number): Promise<FrameSnapshot> {
    if (demo()) return { t_us: null, values: {}, baseline: {}, state: null }
    return getJson(`./api/sessions/${id}/frame?t_us=${Math.max(0, Math.round(tUs))}`)
  },
  async protocol(id: string): Promise<any> {
    const d = demo()
    return d ? { questions: [], markers: [] } : getJson(`./api/sessions/${id}/protocol`)
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
