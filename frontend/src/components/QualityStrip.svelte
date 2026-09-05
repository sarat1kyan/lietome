<script lang="ts">
  import type { LmEvent, SessionDetail } from '../lib/types'
  let { detail, events }: { detail: SessionDetail; events: LmEvent[] } = $props()
  const q = $derived(detail.manifest?.quality ?? {})
  const a = $derived(detail.analysis ?? {})
  const pct = (v: number | null | undefined) => (v == null ? '-' : Math.round(v * 100) + '%')
  const f2 = (v: number | null | undefined) => (v == null ? '-' : v.toFixed(2))
  const counts = $derived(Object.entries(a.event_counts ?? {}) as [string, number][])
  const prov = $derived((detail.manifest?.provenance ?? []) as { extractor_id: string; runtime: string; model_id: string | null }[])
</script>

<footer class="strip">
  <div class="cell"><span class="eyebrow">face coverage</span><span class="mono">{pct(q.face_coverage)}</span></div>
  <div class="cell"><span class="eyebrow">face quality</span><span class="mono">{f2(q.mean_face_quality)}</span></div>
  <div class="cell"><span class="eyebrow">baseline</span><span class="mono">{f2(q.baseline_quality)}</span></div>
  {#if a.audio}
    <div class="cell"><span class="eyebrow">speech</span><span class="mono">{pct(a.audio.speech_fraction)}{a.audio.snr_db != null ? ` / ${Math.round(a.audio.snr_db)} dB` : ''}</span></div>
  {/if}
  <div class="cell"><span class="eyebrow">events</span><span class="mono">{counts.map(([k, v]) => `${v} ${k.replace(/_/g, ' ')}`).join(', ') || 'none'}</span></div>
  <div class="cell grow"><span class="eyebrow">models</span><span class="mono small">{prov.map((p) => p.model_id ?? p.extractor_id).join(' / ')}</span></div>
  {#if q.notes?.length}<div class="cell notes"><span class="eyebrow">notes</span><span class="small">{q.notes.join(' ')}</span></div>{/if}
</footer>

<style>
  .strip { display: flex; gap: 24px; padding: 8px 16px; border-top: 1px solid var(--line); background: var(--panel); font-size: 12px; flex-wrap: wrap; }
  .cell { display: flex; flex-direction: column; gap: 2px; }
  .grow { flex: 1; min-width: 160px; }
  .small { font-size: 11px; color: var(--muted); }
  .notes { flex-basis: 100%; }
</style>
