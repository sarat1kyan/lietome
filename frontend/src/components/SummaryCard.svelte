<script lang="ts">
  import type { LmEvent, SessionDetail } from '../lib/types'
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
</script>

<section class="card">
  <div class="col">
    <div class="eyebrow">what happened, in plain words</div>
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
  .cue-sum { font-size: 11.5px; margin: 4px 0; }
  .cues { list-style: none; margin: 0; padding: 0; font-size: 11.5px; }
  .cues li { display: grid; grid-template-columns: 10px 1fr auto auto; gap: 8px; align-items: center; padding: 2px 0; color: var(--muted); }
  .cues li.on { color: var(--text); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--line-strong); }
  .cues li.on .dot { background: var(--accent); }
</style>
