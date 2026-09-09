<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { LmEvent, SessionSummary } from '../lib/types'

  let { events, session, onpick }: { events: LmEvent[]; session: SessionSummary | null; onpick: (e: LmEvent) => void } = $props()
  const KINDS = new Set(['episode', 'multi_signal_deviation', 'expression_pattern', 'head_gesture', 'au_novelty', 'pulse_change', 'blink_rate_change'])
  // Spread across the session: at most one moment per 15 s bucket, highest severity first.
  const moments = $derived.by(() => {
    const ranked = events.filter((e) => KINDS.has(e.event_type)).sort((a, b) => b.severity - a.severity)
    const taken = new Set<number>()
    const out: LmEvent[] = []
    for (const e of ranked) {
      const bucket = Math.floor(e.start_us / 15e6)
      if (taken.has(bucket)) continue
      taken.add(bucket); out.push(e)
      if (out.length >= 8) break
    }
    return out.sort((a, b) => a.start_us - b.start_us)
  })
  const kind = (e: LmEvent) => (e.event_type === 'expression_pattern' ? 'expression' : e.event_type === 'au_novelty' ? 'new pairing' : e.event_type === 'head_gesture' ? 'gesture' : e.event_type === 'pulse_change' ? 'pulse' : e.event_type === 'blink_rate_change' ? 'blinks' : 'episode')
  const short = (e: LmEvent) => e.label.replace(/^(brief )?expression pattern: /, '$1').replace(/^new AU pairing: /, '').replace(/^head /, '').replace(/^pulse estimate /, '')
  function hideImg(ev: Event) { (ev.currentTarget as HTMLImageElement).hidden = true }
</script>

{#if moments.length}
<section class="moments" aria-label="key moments">
  <div class="hdr"><span class="eyebrow">key moments</span><span class="muted">largest changes from this person's baseline, spread across the session. click to jump.</span></div>
  <div class="strip">
    {#each moments as e (e.event_id)}
      {@const src = session ? api.thumbnail(session.session_id, e.event_id) : null}
      <button class="m" class:expr={e.event_type === 'expression_pattern' || e.event_type === 'au_novelty'} class:pulse={e.event_type === 'pulse_change'} class:gesture={e.event_type === 'head_gesture'} onclick={() => onpick(e)} title={e.description}>
        <div class="pic">{#if src}<img {src} alt="" loading="lazy" onerror={hideImg} />{/if}<span class="k">{kind(e)}</span></div>
        <div class="lbl">{short(e)}</div>
        <div class="mono meta">{tc(e.start_us).slice(3)} <span class="sev">{e.severity > 20 ? '>20' : e.severity.toFixed(1)}</span></div>
      </button>
    {/each}
  </div>
</section>
{/if}

<style>
  .moments { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 14px 12px; }
  .hdr { display: flex; gap: 12px; align-items: baseline; margin-bottom: 8px; font-size: 11.5px; }
  .strip { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(132px, 1fr); gap: 10px; overflow-x: auto; padding-bottom: 2px; }
  .m { display: flex; flex-direction: column; gap: 4px; padding: 0; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel-2); text-align: left; color: var(--text); cursor: pointer; overflow: hidden; }
  .m:hover { border-color: var(--line-strong); }
  .m:focus-visible { outline: 1px solid var(--accent); }
  .pic { position: relative; aspect-ratio: 4 / 3; background: var(--ground); border-bottom: 2px solid var(--accent); }
  .m.expr .pic { border-bottom-color: var(--violet); }
  .m.pulse .pic { border-bottom-color: var(--pulse); }
  .m.gesture .pic { border-bottom-color: var(--cool); }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .k { position: absolute; left: 6px; top: 5px; font: 500 10px/1 var(--font-data); letter-spacing: 0.04em; text-transform: uppercase; color: var(--text); background: rgba(5, 7, 10, 0.7); padding: 3px 5px; border-radius: 2px; }
  .lbl { font-size: 12px; padding: 2px 8px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta { font-size: 11px; color: var(--muted); padding: 0 8px 7px; display: flex; justify-content: space-between; }
  .sev { color: var(--text); }
</style>
