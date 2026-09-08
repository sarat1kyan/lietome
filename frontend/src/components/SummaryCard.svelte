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
</section>

<style>
  .card { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr); gap: 20px; padding: 12px 16px; border-top: 1px solid var(--line); background: var(--panel); }
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
</style>
