<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { Baseline, LmEvent, SessionSummary } from '../lib/types'
  let { selected, events, session, baseline, onpick }: { selected: LmEvent | null; events: LmEvent[]; session: SessionSummary | null; baseline: Baseline | null; onpick: (e: LmEvent) => void } = $props()
  let filter = $state<'all' | 'video' | 'audio' | 'interpretation'>('all')
  const listed = $derived(events.filter((e) => e.event_type !== 'blink').filter((e) => filter === 'all' || (filter === 'interpretation' ? e.level === 'interpretation' : e.source === filter)).sort((a, b) => b.severity - a.severity))
  const blinks = $derived(events.filter((e) => e.event_type === 'blink').length)
  const thumb = $derived(selected && session ? api.thumbnail(session.session_id, selected.event_id) : null)
  const f3 = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(3))
</script>

<aside class="panel">
  {#if selected}
    <div class="detail">
      <div class="eyebrow">{selected.level} <span class="src">{selected.source}</span></div>
      <h2>{selected.label}</h2>
      <div class="mono when">{tc(selected.start_us)} to {tc(selected.end_us)} <span class="muted">({Math.round((selected.end_us - selected.start_us) / 1000)} ms)</span></div>
      {#if thumb}<img class="thumb" src={thumb} alt="" onerror={(e) => ((e.currentTarget as HTMLImageElement).style.display = 'none')} />{/if}
      <p class="desc">{selected.description}</p>
      <div class="eyebrow">contributors</div>
      <table class="mono">
        <tbody>
        {#each selected.contributions.slice(0, 8) as c (c.feature)}
          <tr>
            <td class="feat">{c.feature}</td>
            <td class="dev" class:neg={c.peak_deviation < 0}>{c.peak_deviation >= 0 ? '+' : ''}{c.peak_deviation.toFixed(1)} SD</td>
            <td class="muted">{f3(c.peak_value)} vs {f3(c.baseline_center)} {c.unit}</td>
          </tr>
        {/each}
        </tbody>
      </table>
      <div class="eyebrow">confidence</div>
      <div class="meters">
        <Meter label="measurement" value={selected.confidence} />
        <Meter label="input quality" value={selected.quality} />
        <Meter label="baseline" value={selected.baseline_quality} />
      </div>
      <p class="caveat">This event describes measured motion or voice relative to this person's own baseline in this recording. It does not establish any psychological state and says nothing about truthfulness.</p>
    </div>
  {:else}
    <div class="detail empty muted">Select an event to inspect its evidence.</div>
  {/if}

  <div class="list">
    <div class="list-hdr">
      <span class="eyebrow">events <span class="mono">{listed.length}</span></span>
      <span class="muted mono">{blinks} blinks</span>
      <div class="filters">
        {#each ['all', 'video', 'audio', 'interpretation'] as f}
          <button class:on={filter === f} onclick={() => (filter = f as typeof filter)}>{f}</button>
        {/each}
      </div>
    </div>
    <ul>
      {#each listed as e (e.event_id)}
        <li>
          <button class="ev" class:sel={selected?.event_id === e.event_id} class:audio={e.source === 'audio'} onclick={() => onpick(e)}>
            <span class="sev mono">{e.severity.toFixed(1)}</span>
            <span class="lbl">{e.label}</span>
            <span class="t mono muted">{tc(e.start_us).slice(3)}</span>
          </button>
        </li>
      {/each}
    </ul>
  </div>
</aside>

{#snippet Meter({ label, value }: { label: string; value: number })}
  <div class="meter">
    <span class="muted">{label}</span>
    <span class="bar"><i style="width:{Math.round(value * 100)}%"></i></span>
    <span class="mono">{value.toFixed(2)}</span>
  </div>
{/snippet}

<style>
  .panel { grid-area: panel; border-left: 1px solid var(--line); background: var(--panel); display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
  .detail { padding: 14px 16px; border-bottom: 1px solid var(--line); }
  .detail.empty { padding: 28px 16px; }
  .src { margin-left: 8px; color: var(--teal); }
  h2 { font-size: 15px; font-weight: 600; margin: 4px 0 4px; text-wrap: balance; }
  .when { font-size: 12px; }
  .thumb { display: block; width: 100%; max-height: 180px; object-fit: cover; margin: 10px 0; border: 1px solid var(--line); border-radius: var(--radius); background: #000; }
  .desc { color: var(--muted); font-size: 12px; margin: 8px 0 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 11.5px; margin: 6px 0 12px; }
  td { padding: 3px 0; border-bottom: 1px solid var(--line); vertical-align: top; }
  .feat { width: 44%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 0; }
  .dev { color: var(--accent); width: 22%; }
  .dev.neg { color: var(--cool); }
  .meters { display: grid; gap: 4px; margin: 6px 0 12px; }
  .meter { display: grid; grid-template-columns: 96px 1fr 40px; gap: 8px; align-items: center; font-size: 11.5px; }
  .bar { height: 5px; background: var(--line); border-radius: 2px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--ok); }
  .caveat { font-size: 11px; color: var(--muted); border-left: 2px solid var(--accent); padding-left: 8px; margin: 0; }
  .list { min-height: 0; overflow-y: auto; }
  .list-hdr { display: flex; gap: 10px; align-items: center; padding: 10px 16px 6px; flex-wrap: wrap; position: sticky; top: 0; background: var(--panel); }
  .filters { display: flex; gap: 4px; margin-left: auto; }
  .filters button { padding: 1px 7px; font-size: 11px; border-color: var(--line); background: none; color: var(--muted); }
  .filters button.on { color: var(--text); border-color: var(--muted); }
  ul { list-style: none; margin: 0; padding: 0; }
  .ev { display: grid; grid-template-columns: 40px 1fr auto; gap: 8px; width: 100%; text-align: left; background: none; border: 0; border-left: 2px solid transparent; border-bottom: 1px solid var(--line); border-radius: 0; padding: 7px 16px 7px 14px; }
  .ev:hover { background: var(--panel-2); }
  .ev.sel { border-left-color: var(--accent); background: var(--panel-2); }
  .ev.audio.sel { border-left-color: var(--teal); }
  .sev { color: var(--accent); }
  .ev.audio .sev { color: var(--teal); }
  .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .t { font-size: 11px; }
</style>
