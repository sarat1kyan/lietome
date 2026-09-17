<script lang="ts">
  import type { LmEvent, SessionDetail } from '../lib/types'
  import CueGauge from './CueGauge.svelte'
  let copied = $state(false)
  async function copySummary() {
    const a = detail.analysis ?? {}
    const lines = [
      `Lightman session ${a.session_id ?? ''} (${a.mode ?? 'prerecorded'})`,
      ...narrative,
      '',
      'Event counts: ' + Object.entries(a.event_counts ?? {}).map(([k, v]) => `${k} ${v}`).join(', '),
      cues?.index?.text ?? '',
      '',
      'Measurements of movement and voice against this person\'s own baseline. Not a lie detector.',
    ]
    try { await navigator.clipboard.writeText(lines.filter((l) => l != null).join('\n')); copied = true; setTimeout(() => (copied = false), 1500) } catch { copied = false }
  }
  let { detail, events }: { detail: SessionDetail; events: LmEvent[] } = $props()
  const narrative = $derived((detail.analysis?.narrative ?? []) as string[])
  const contributors = $derived.by(() => {
    const c = new Map<string, number>()
    for (const e of events) if (e.event_type === 'baseline_deviation') { const f = e.contributions[0]?.feature; if (f) c.set(f, (c.get(f) ?? 0) + 1) }
    const arr = [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10)
    const max = arr[0]?.[1] ?? 1
    return arr.map(([f, n]) => ({ f: f.replace(/^(blendshape|au)\./, ''), n, w: (100 * n) / max, audio: f.startsWith('voice.') }))
  })
  const rate = $derived(detail.analysis?.blink_rate_per_min ?? null)
  const cues = $derived(detail.analysis?.session_cues ?? null)
  const exprCounts = $derived.by(() => {
    const c = new Map<string, number>()
    for (const e of events) if (e.event_type === 'expression_pattern') for (const t of e.tags) if (t !== 'expression' && t !== 'brief') c.set(t, (c.get(t) ?? 0) + 1)
    return [...c.entries()].sort((a, b) => b[1] - a[1])
  })
  const briefCount = $derived(events.filter((e) => e.event_type === 'expression_pattern' && e.tags.includes('brief')).length)
  const stats = $derived.by(() => {
    const a = detail.analysis ?? {}
    const dur = (a.duration_us ?? 0) / 6e7
    const post = Math.max(0.1, dur - (detail.baseline?.window_end_us ?? 0) / 6e7)
    const n = (t: string) => events.filter((e) => e.event_type === t).length
    const pulse = a.pulse?.median_bpm
    return [
      { k: 'episodes / min', v: (n('episode') / post).toFixed(1), c: 'accent' },
      { k: 'deviations / min', v: (n('baseline_deviation') / post).toFixed(0), c: 'accent' },
      { k: 'expression patterns', v: String(n('expression_pattern')), c: 'violet' },
      { k: 'nods / shakes', v: `${events.filter((e) => e.event_type === 'head_gesture' && e.tags.includes('nod')).length} / ${events.filter((e) => e.event_type === 'head_gesture' && e.tags.includes('shake')).length}`, c: 'cool' },
      { k: 'gaze away', v: String(n('gaze_away')), c: 'cool' },
      { k: 'blinks / min', v: rate != null ? rate.toFixed(0) : '-', c: 'cool' },
      { k: 'voice events', v: String(events.filter((e) => e.source === 'audio').length), c: 'teal' },
      { k: 'pulse est. bpm', v: pulse != null ? String(Math.round(pulse)) : 'n/a', c: 'pulse' },
    ]
  })
</script>

<section class="card">
  <div class="stats">
    {#each stats as s (s.k)}<div class="stat {s.c}"><span class="mono v">{s.v}</span><span class="k">{s.k}</span></div>{/each}
  </div>
  <div class="col">
    <div class="eyebrow row-hdr">what happened, in plain words <button class="copy" onclick={copySummary}>{copied ? 'copied' : 'copy summary'}</button></div>
    <ul class="narr">
      {#each narrative as line}<li>{line}</li>{:else}<li class="muted">no narrative in this session (older format)</li>{/each}
    </ul>
  </div>
  <div class="col small">
    <div class="eyebrow">most frequent deviating signals</div>
    <div class="bars">
      {#each contributors as c (c.f)}
        <div class="row"><span class="mono lbl">{c.f}</span><span class="bar"><i class:audio={c.audio} style="width:{c.w}%"></i></span><span class="mono n">{c.n}</span></div>
      {:else}<div class="muted">none</div>{/each}
    </div>
    {#if rate != null}<div class="muted small-note mono">blink rate {rate.toFixed(0)}/min</div>{/if}
  </div>
  <div class="col small">
    <div class="eyebrow">expression patterns (appearance, not feeling)</div>
    {#if exprCounts.length}
      <div class="chips">{#each exprCounts as [name, n] (name)}<span class="chip expr">{name} <b class="mono">{n}</b></span>{/each}</div>
      <div class="muted small-note">{briefCount} brief (under 500 ms): candidates for what the microexpression literature studies, unconfirmed.</div>
    {:else}<div class="muted">none matched a FACS prototype</div>{/if}
    {#if cues?.index}
      <div class="gauge-wrap"><CueGauge index={cues.index} /></div>
    {/if}
    {#if cues}
      <div class="eyebrow cues-hdr">deception-research cues (checklist, not a probability)</div>
      <div class="mono cue-sum">{cues.summary}</div>
      <ul class="cues">
        {#each cues.cues as c (c.key)}
          <li class:on={c.present}><span class="dot"></span><span>{c.name}</span><span class="mono muted">{c.value == null ? 'n/a' : c.value + ' ' + c.unit}</span><span class="mono muted" title={c.source}>d={c.effect_size}</span></li>
        {/each}
      </ul>
      <div class="muted small-note">{cues.caveat}</div>
    {/if}
  </div>
</section>

<style>
  .card { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr); gap: 20px; padding: 12px 16px; border-top: 1px solid var(--line); background: var(--panel); }
  .stats { grid-column: 1 / -1; display: grid; grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 10px; }
  .stat { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-left: 2px solid var(--line-strong); background: var(--panel-2); }
  .stat .v { font-size: 20px; color: var(--text); font-variant-numeric: tabular-nums; }
  .stat .k { font-size: 10.5px; color: var(--muted); letter-spacing: 0.03em; text-transform: uppercase; }
  .stat.accent { border-left-color: var(--accent); } .stat.violet { border-left-color: var(--violet); } .stat.cool { border-left-color: var(--cool); } .stat.teal { border-left-color: var(--teal); } .stat.pulse { border-left-color: var(--pulse); }
  .row-hdr { display: flex; justify-content: space-between; align-items: center; }
  .copy { padding: 1px 8px; font-size: 11px; text-transform: none; letter-spacing: 0; }
  .narr { margin: 6px 0 0; padding-left: 16px; font-size: 13px; line-height: 1.5; max-width: 72ch; }
  .narr li { margin-bottom: 3px; }
  .bars { display: grid; gap: 4px; margin-top: 6px; }
  .row { display: grid; grid-template-columns: 130px 1fr 32px; gap: 8px; align-items: center; font-size: 11.5px; }
  .lbl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { height: 7px; background: var(--line); border-radius: 2px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--accent); }
  .bar i.audio { background: var(--teal); }
  .n { text-align: right; color: var(--muted); }
  .small-note { margin-top: 8px; font-size: 11.5px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
  .chip { border: 1px solid var(--line-strong); padding: 1px 8px; border-radius: 10px; font-size: 11.5px; }
  .chip.expr { border-color: var(--violet); color: var(--violet); }
  .cues-hdr { margin-top: 12px; }
  .gauge-wrap { margin-top: 10px; padding: 10px 12px; background: var(--panel-2); border-left: 2px solid var(--line-strong); }
  .cue-sum { font-size: 11.5px; margin: 4px 0; }
  .cues { list-style: none; margin: 0; padding: 0; font-size: 11.5px; }
  .cues li { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 8px; align-items: center; padding: 2px 0; color: var(--muted); }
  .cues li.on { color: var(--text); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--line-strong); }
  .cues li.on .dot { background: var(--accent); }
</style>
