<script lang="ts">
  // Possibility-of-deception cue index: a weighted share of weak literature cues, never a probability.
  let { index, compact = false, control = null }: { index: { value: number | null; band: string; drivers?: string[]; counters?: string[]; reliability?: number; text?: string } | null; compact?: boolean; control?: number | null } = $props()
  const v = $derived(index?.value ?? null)
  const color = $derived(v == null ? 'var(--faint)' : v < 40 ? 'var(--cool)' : v < 55 ? 'var(--muted)' : v < 70 ? 'var(--accent)' : 'var(--warn)')
</script>

{#if index}
<div class="gauge" class:compact style:--c={color}>
  <div class="head">
    <span class="eyebrow">possibility of deception, cue index</span>
    <span class="mono val">{v == null ? 'n/a' : Math.round(v)}<small>/100</small></span>
    <span class="band">{index.band}</span>
  </div>
  <div class="track">
    <span class="zone low"></span><span class="zone mid"></span><span class="zone some"></span><span class="zone hi"></span>
    {#if v != null}<i class="pin" style:left="{v}%"></i>{/if}
    {#if control != null}<i class="ctl" style:left="{control}%" title="mean of control questions"></i>{/if}
  </div>
  {#if !compact}
    <div class="legend mono"><span>0 cues against</span><span>50 no net evidence</span><span>100 all cues moved</span></div>
    {#if index.drivers?.length}<div class="line"><span class="k">moved with lying</span> {index.drivers.join(', ')}</div>{/if}
    {#if index.counters?.length}<div class="line"><span class="k">moved against</span> {index.counters.join(', ')}</div>{/if}
    <div class="line muted">reliability {index.reliability?.toFixed(2) ?? '-'}{control != null ? `; control questions averaged ${Math.round(control)}` : ''}. Weighted share of weak cues (d mostly under 0.3) against this person's own baseline. Not a probability: all such cues combined reach about 54-60% accuracy in the literature.</div>
  {/if}
</div>
{/if}

<style>
  .gauge { display: flex; flex-direction: column; gap: 5px; }
  .head { display: flex; align-items: baseline; gap: 10px; }
  .val { font-size: 22px; color: var(--c); font-variant-numeric: tabular-nums; }
  .val small { font-size: 11px; color: var(--muted); }
  .band { font-size: 11.5px; color: var(--c); text-transform: uppercase; letter-spacing: 0.06em; }
  .compact .val { font-size: 16px; }
  .track { position: relative; height: 8px; display: flex; border-radius: 2px; overflow: visible; background: var(--panel-2); }
  .zone { height: 100%; opacity: 0.35; }
  .zone.low { width: 40%; background: var(--cool); }
  .zone.mid { width: 15%; background: var(--line-strong); }
  .zone.some { width: 15%; background: var(--accent); }
  .zone.hi { width: 30%; background: var(--warn); }
  .pin { position: absolute; top: -3px; width: 3px; height: 14px; margin-left: -1.5px; background: var(--text); border-radius: 1px; }
  .ctl { position: absolute; top: 9px; width: 0; height: 0; margin-left: -4px; border: 4px solid transparent; border-bottom-color: var(--cool); }
  .legend { display: flex; justify-content: space-between; font-size: 9.5px; color: var(--faint); }
  .line { font-size: 11.5px; line-height: 1.45; }
  .line .k { color: var(--muted); font: 500 10px/1 var(--font-data); letter-spacing: 0.06em; text-transform: uppercase; margin-right: 6px; }
  .line.muted { color: var(--muted); font-size: 11px; max-width: 70ch; }
</style>
