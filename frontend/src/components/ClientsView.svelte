<script lang="ts">
  import { api } from '../lib/api'
  import type { ClientRow } from '../lib/types'
  let { onopen }: { onopen: (sessionId: string) => void } = $props()
  let rows = $state<ClientRow[]>([])
  let busy = $state(false)
  let newCode = $state('')
  let erasing = $state<string | null>(null)
  let confirmText = $state('')
  let message = $state('')
  let selected = $state<string | null>(null)
  let trends = $state<{ sessions: any[]; measures: string[] } | null>(null)
  const LABELS: Record<string, string> = { valence: 'valence (mean)', arousal: 'arousal (mean)', engagement: 'oriented to conversation', client_talk_share: 'client talk share', speech_rate: 'syllables per second', negative_patterns_per_min: 'negative patterns per min', blink_rate: 'blinks per min' }
  async function openTrends(code: string) { selected = code; trends = null; trends = await api.trends(code).catch(() => null) }
  function spark(rows: any[], key: string): { d: string; pts: { x: number; y: number; v: number }[]; min: number; max: number } {
    const vals = rows.map((r) => r[key]).filter((v) => v != null) as number[]
    if (vals.length < 1) return { d: '', pts: [], min: 0, max: 0 }
    let min = Math.min(...vals), max = Math.max(...vals)
    if (max - min < 1e-6) { min -= 0.5; max += 0.5 }
    const W = 220, H = 48
    const pts = rows.map((r, i) => ({ v: r[key], i })).filter((p) => p.v != null).map((p) => ({ x: rows.length > 1 ? 6 + (p.i / (rows.length - 1)) * (W - 12) : W / 2, y: H - 6 - ((p.v - min) / (max - min)) * (H - 12), v: p.v as number }))
    return { d: pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '), pts, min, max }
  }
  async function load() { rows = await api.clients().catch(() => []) }
  load()
  async function create() {
    const c = newCode.trim(); if (!/^[A-Za-z0-9_-]{1,32}$/.test(c)) { message = 'Codes use letters, digits, - and _ (up to 32).'; return }
    await api.saveClient(c, {}); newCode = ''; message = ''; await load()
  }
  async function saveLabel(r: ClientRow, label: string) { await api.saveClient(r.code, { label }); await load() }
  async function erase(code: string) {
    busy = true
    try { const res = await api.eraseClient(code); message = `Erased ${code}: ${res.sessions_removed.length} sessions, norms and client entry.` }
    catch (e) { message = String(e) }
    busy = false; erasing = null; confirmText = ''; await load()
  }
</script>

<section class="clients">
  <header>
    <div><span class="eyebrow">clients</span><h1>People you work with</h1><p class="muted">Each client is a code. Sessions, notes, norms and validation results are grouped under it. Labels stay on this machine.</p></div>
    <div class="new"><input id="new-client" placeholder="new code, e.g. C-015" bind:value={newCode} maxlength="32" onkeydown={(e) => e.key === 'Enter' && create()} /><button class="primary" onclick={create}>Add client</button></div>
  </header>
  {#if message}<p class="msg">{message}</p>{/if}
  <div class="wrap">
    <table>
      <thead><tr><th>code</th><th>label</th><th>sessions</th><th>last session</th><th></th></tr></thead>
      <tbody>
        {#each rows as r (r.code)}
          <tr>
            <td class="mono code"><button class="link mono" onclick={() => openTrends(r.code)} title="show trends across sessions">{r.code}</button></td>
            <td><input aria-label={`label for ${r.code}`} value={r.label} placeholder="optional" onchange={(e) => saveLabel(r, (e.currentTarget as HTMLInputElement).value)} /></td>
            <td class="mono">{r.sessions}</td>
            <td>{#if r.last_session}<button class="link mono" onclick={() => onopen(r.last_session!)}>{r.last_session.slice(0, 8)}</button>{:else}<span class="muted">none yet</span>{/if}</td>
            <td class="acts">
              <a class="btn" href={api.exportClientUrl(r.code)} download>Export</a>
              {#if erasing === r.code}
                <input class="confirm" placeholder={`type ${r.code}`} bind:value={confirmText} aria-label="type the code to confirm erasure" />
                <button class="danger" disabled={confirmText !== r.code || busy} onclick={() => erase(r.code)}>Erase everything</button>
                <button onclick={() => { erasing = null; confirmText = '' }}>Cancel</button>
              {:else}
                <button onclick={() => { erasing = r.code; confirmText = '' }}>Erase...</button>
              {/if}
            </td>
          </tr>
        {:else}
          <tr><td colspan="5" class="muted empty">No clients yet. Add one here, or create one when you start a live session.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if selected}
    <section class="trends" aria-label={`trends for ${selected}`}>
      <div class="thead"><span class="eyebrow">trends for {selected}</span><span class="muted">one point per session, oldest left. most useful once there are several sessions recorded in similar conditions.</span><button onclick={() => (selected = null)}>close</button></div>
      {#if trends && trends.sessions.length}
        <div class="grid">
          {#each trends.measures as m (m)}
            {@const sp = spark(trends.sessions, m)}
            <figure>
              <figcaption>{LABELS[m] ?? m}</figcaption>
              {#if sp.pts.length}
                <svg viewBox="0 0 220 48" width="100%" height="48" role="img" aria-label={`${LABELS[m] ?? m} across sessions`}>
                  <path d={sp.d} fill="none" stroke="var(--accent)" stroke-width="1.6" />
                  {#each sp.pts as p, i (i)}<circle cx={p.x} cy={p.y} r={i === sp.pts.length - 1 ? 3.5 : 2.2} fill={i === sp.pts.length - 1 ? 'var(--accent)' : 'var(--muted)'} />{/each}
                </svg>
                <span class="mono vals">last {sp.pts[sp.pts.length - 1].v.toFixed(2)}; range {sp.min.toFixed(2)} to {sp.max.toFixed(2)}</span>
              {:else}<span class="muted vals">no data</span>{/if}
            </figure>
          {/each}
        </div>
      {:else if trends}<p class="muted">No analysed sessions yet.</p>{:else}<p class="muted">Loading...</p>{/if}
    </section>
  {/if}
  <p class="muted foot">Export gives you everything Lightman holds about a client as a zip. Erase deletes their sessions, notes, norms and entry from this machine; it cannot be undone.</p>
</section>

<style>
  .clients { grid-area: stage; overflow-y: auto; padding: 24px 28px; display: flex; flex-direction: column; gap: 14px; background: var(--ground); }
  header { display: flex; justify-content: space-between; gap: 20px; align-items: flex-end; flex-wrap: wrap; }
  h1 { margin: 4px 0; font-size: 22px; font-weight: 600; }
  header p { margin: 0; max-width: 62ch; font-size: 13px; }
  .new { display: flex; gap: 8px; }
  input { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); color: var(--text); padding: 5px 8px; font: 13px var(--font-ui); }
  .wrap { overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 6px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); }
  th { color: var(--muted); font-weight: 400; font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; }
  .code { color: var(--accent); }
  .acts { display: flex; gap: 6px; justify-content: flex-end; align-items: center; flex-wrap: wrap; }
  .btn { border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 4px 10px; color: var(--text); text-decoration: none; font-size: 12px; }
  .danger { border-color: var(--warn); color: var(--warn); }
  .confirm { width: 110px; }
  .link { background: none; border: 0; color: var(--cool); padding: 0; cursor: pointer; }
  .msg { margin: 0; padding: 8px 12px; background: var(--panel-2); border-left: 2px solid var(--accent); font-size: 13px; }
  .empty { padding: 20px 12px; }
  .foot { font-size: 12px; max-width: 80ch; }
  .trends { background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px 14px; }
  .thead { display: flex; gap: 12px; align-items: baseline; font-size: 12px; flex-wrap: wrap; }
  .thead button { margin-left: auto; padding: 1px 8px; font-size: 11px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; margin-top: 10px; }
  figure { margin: 0; display: flex; flex-direction: column; gap: 4px; background: var(--panel-2); padding: 8px 10px; }
  figcaption { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .vals { font-size: 11px; color: var(--muted); }
</style>
