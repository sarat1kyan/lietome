<script lang="ts">
  import { api, tc } from '../lib/api'
  import { app } from '../lib/settings.svelte'
  import type { ClientRow, SessionSummary } from '../lib/types'
  let { sessions, onlive, onupload, onopen, onclients }: { sessions: SessionSummary[]; onlive: () => void; onupload: () => void; onopen: (s: SessionSummary) => void; onclients: () => void } = $props()
  let clients = $state<ClientRow[]>([])
  api.clients().then((c) => (clients = c)).catch(() => {})
  const recent = $derived(sessions.slice(0, 6))
  const when = (s: string | null) => (s ? s.slice(0, 16).replace('T', ' ') : '')
  const missing = $derived(((app.system?.models ?? []) as any[]).filter((m) => !m.cached))
</script>

<section class="home">
  <header>
    <span class="eyebrow">{app.settings?.profile === 'research' ? 'research profile' : 'practice profile'}{app.settings?.practitioner ? ` / ${app.settings.practitioner}` : ''}</span>
    <h1>What would you like to do?</h1>
  </header>
  <div class="actions">
    <button class="action primary-action" onclick={onlive}>
      <span class="t">Start a live session</span>
      <span class="d">Camera and microphone in this browser. Calibration takes 40 seconds, then measurements run live.</span>
    </button>
    <button class="action" onclick={onupload}>
      <span class="t">Analyse a recording</span>
      <span class="d">A video file from a session, an interview or a call. Analysed on this machine.</span>
    </button>
    <button class="action" onclick={onclients}>
      <span class="t">Clients</span>
      <span class="d">{clients.length ? `${clients.length} ${clients.length === 1 ? 'client' : 'clients'}; trends across sessions, export and erasure.` : 'Codes for the people you work with; trends across their sessions.'}</span>
    </button>
  </div>
  {#if missing.length}
    <p class="warn">Some models are not downloaded yet ({missing.map((m) => m.id).join(', ')}). They download on first use, or run <code class="mono">lightman setup</code>.</p>
  {/if}
  <div class="recent">
    <div class="rh"><span class="eyebrow">recent sessions</span></div>
    {#if recent.length}
      <ul>
        {#each recent as s (s.session_id)}
          <li><button onclick={() => onopen(s)}>
            <span class="code mono">{s.subject_id ?? '-'}</span>
            <span class="what">{s.mode === 'live' ? 'live session' : s.media_name ?? 'recording'}</span>
            <span class="len mono">{s.duration_us ? tc(s.duration_us).slice(3, 8) : '-'}</span>
            <span class="when mono">{when(s.created_utc)}</span>
          </button></li>
        {/each}
      </ul>
    {:else}
      <p class="muted">No sessions yet. Start a live session or analyse a recording.</p>
    {/if}
  </div>
  <p class="foot muted">Lightman describes observable behaviour against a person's own baseline. It does not diagnose, read emotions or detect lies.</p>
</section>

<style>
  .home { grid-area: stage; overflow-y: auto; padding: 36px 40px; display: flex; flex-direction: column; gap: 24px; background: var(--ground); }
  h1 { margin: 6px 0 0; font-size: 26px; font-weight: 600; letter-spacing: -0.01em; }
  .actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; max-width: 980px; }
  .action { display: flex; flex-direction: column; gap: 6px; text-align: left; padding: 18px 18px 20px; background: var(--panel); border: 1px solid var(--line); border-radius: 8px; cursor: pointer; color: var(--text); }
  .action:hover { border-color: var(--line-strong); background: var(--panel-2); }
  .action:focus-visible { outline: 1px solid var(--accent); }
  .primary-action { border-color: var(--accent); }
  .t { font-size: 16px; font-weight: 600; }
  .d { font-size: 13px; color: var(--muted); line-height: 1.45; }
  .recent { max-width: 980px; }
  ul { list-style: none; margin: 8px 0 0; padding: 0; border: 1px solid var(--line); border-radius: 6px; overflow: hidden; }
  li button { width: 100%; display: grid; grid-template-columns: 110px minmax(0, 1fr) 70px 140px; gap: 12px; padding: 10px 14px; background: var(--panel); border: 0; border-bottom: 1px solid var(--line); text-align: left; color: var(--text); cursor: pointer; font-size: 13px; }
  li:last-child button { border-bottom: 0; }
  li button:hover { background: var(--panel-2); }
  .code { color: var(--accent); }
  .what { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .len, .when { color: var(--muted); }
  .warn { max-width: 980px; margin: 0; padding: 10px 12px; border-left: 2px solid var(--accent); background: var(--panel); font-size: 13px; }
  .foot { font-size: 12px; max-width: 80ch; margin: 0; }
  @media (max-width: 700px) { .home { padding: 20px 16px; } li button { grid-template-columns: 90px minmax(0, 1fr) 60px; } .when { display: none; } }
</style>
