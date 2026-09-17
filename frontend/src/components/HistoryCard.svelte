<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { History } from '../lib/types'
  let { sessionId }: { sessionId: string } = $props()
  let hist = $state<History | null>(null)
  $effect(() => { const id = sessionId; hist = null; api.history(id).then((h) => { if (id === sessionId) hist = h }).catch(() => (hist = null)) })
  const others = $derived((hist?.sessions ?? []).filter((s) => s.session_id !== sessionId))
  const human = (s: string) => s.replace(/^(blendshape|au)\./, '').replace(/^head\./, 'head ').replace(/_deg(_s)?$/, '').replace(/^eye\./, 'eye ')
  const when = (s: string | null) => (s ? s.slice(0, 16).replace('T', ' ') : '')
</script>

{#if hist && others.length}
<section class="hist">
  <div class="hdr"><span class="eyebrow">this subject across sessions</span><span class="muted">{hist.subject_id}: {hist.sessions.length} sessions. baseline centers of this session against the median of the others, in this session's robust SD.</span></div>
  <div class="grid">
    <table class="mono">
      <tbody>
        {#each hist.shifts.slice(0, 8) as r (r.signal)}
          <tr class:hot={Math.abs(r.shift_sd ?? 0) >= 2}><td class="sig">{human(r.signal)}</td><td class="num">{r.shift_sd == null ? '-' : `${r.shift_sd >= 0 ? '+' : ''}${r.shift_sd.toFixed(1)} SD`}</td><td class="muted">{r.current} vs {r.median_others} (n {r.n_others})</td></tr>
        {/each}
      </tbody>
    </table>
    <table class="mono sessions">
      <thead><tr><th>session</th><th>len</th><th>blinks/min</th><th>pulse</th><th>episodes</th><th>index</th></tr></thead>
      <tbody>
        {#each hist.sessions as s (s.session_id)}
          <tr class:cur={s.session_id === sessionId}><td>{when(s.created_utc)}</td><td>{s.duration_us ? tc(s.duration_us).slice(3, 8) : '-'}</td><td>{s.blink_rate_per_min?.toFixed(0) ?? '-'}</td><td>{s.pulse_bpm ? Math.round(s.pulse_bpm) : '-'}</td><td>{s.episodes ?? '-'}</td><td>{s.cue_index != null ? Math.round(s.cue_index) : '-'}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
  <p class="muted note">A stable baseline across sessions means the calibration is repeatable for this person; large shifts point to lighting, camera distance or mood on the day, not to anything in the answers.</p>
</section>
{/if}

<style>
  .hist { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 16px 12px; }
  .hdr { display: flex; gap: 12px; align-items: baseline; font-size: 11.5px; margin-bottom: 6px; flex-wrap: wrap; }
  .grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: 8px 24px; }
  table { border-collapse: collapse; width: 100%; font-size: 11.5px; }
  td, th { padding: 2px 8px 2px 0; text-align: left; white-space: nowrap; }
  th { color: var(--muted); font-weight: normal; font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; }
  .sig { color: var(--text); }
  .num { text-align: right; color: var(--text); }
  tr.hot .sig, tr.hot .num { color: var(--accent); }
  tr.cur td { color: var(--accent); }
  .note { font-size: 11px; margin: 8px 0 0; max-width: 80ch; }
</style>
