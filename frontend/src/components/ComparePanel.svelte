<script lang="ts">
  import { api, tc } from '../lib/api'
  import type { CompareResult, Range } from '../lib/types'

  let { sessionId, a, b, protocol, onclear, onpreset }: {
    sessionId: string; a: Range | null; b: Range | null; protocol: any
    onclear: () => void; onpreset: (a: Range, b: Range) => void
  } = $props()
  let result = $state<CompareResult | null>(null)
  let busy = $state(false)
  let err = $state<string | null>(null)
  let inflight = 0

  $effect(() => {
    const id = sessionId, ra = a, rb = b
    if (!ra || !rb) { result = null; return }
    const seq = ++inflight
    busy = true; err = null
    api.compare(id, ra, rb).then((r) => { if (seq === inflight) { result = r; busy = false } }).catch((e) => { if (seq === inflight) { err = String(e); busy = false } })
  })

  const questions = $derived((protocol?.questions ?? []) as { id: string; text: string; category: string; start_us: number; end_us: number }[])
  const rows = $derived((result?.signals ?? []).filter((r) => r.shift_sd != null).slice(0, 12))
  const voice = $derived((result?.voice ?? []).filter((r) => r.shift_sd != null))
  const human = (s: string) => s.replace(/^(blendshape|au)\./, '').replace(/_deg(_s)?$/, '').replace(/^head\./, 'head ').replace(/^gaze\./, 'gaze ').replace(/^asym\./, 'asym ').replace(/^eye\./, 'eye ').replace(/^voice\./, 'voice ')
  const dur = (r: Range) => ((r[1] - r[0]) / 1e6).toFixed(1) + ' s'
  const evRows = $derived(Object.entries(result?.events ?? {}).filter(([k]) => k !== 'blink'))
  let qa = $state(''), qb = $state('')
  function applyPreset() {
    const A = questions.find((q) => q.id === qa), B = questions.find((q) => q.id === qb)
    if (A && B) onpreset([A.start_us, A.end_us], [B.start_us, B.end_us])
  }
</script>

<section class="cmp">
  <div class="hdr">
    <span class="eyebrow">compare two spans</span>
    <span class="muted">drag on the timeline: first drag sets A, second sets B. Shift in this person's robust SD; positive = B higher.</span>
    {#if questions.length >= 2}
      <span class="preset">
        <select bind:value={qa}><option value="">question A</option>{#each questions as q (q.id)}<option value={q.id}>{q.id} {q.category}</option>{/each}</select>
        <span class="muted">vs</span>
        <select bind:value={qb}><option value="">question B</option>{#each questions as q (q.id)}<option value={q.id}>{q.id} {q.category}</option>{/each}</select>
        <button onclick={applyPreset} disabled={!qa || !qb}>compare</button>
      </span>
    {/if}
    <button class="clear" onclick={onclear}>clear</button>
  </div>
  <div class="spans">
    <span class="span a"><b>A</b> {a ? `${tc(a[0]).slice(3)} to ${tc(a[1]).slice(3)} (${dur(a)})` : 'drag to set'}</span>
    <span class="span b"><b>B</b> {b ? `${tc(b[0]).slice(3)} to ${tc(b[1]).slice(3)} (${dur(b)})` : a ? 'drag to set' : ''}</span>
    {#if result?.speaking_fraction}<span class="muted mono">speaking {Math.round((result.speaking_fraction.a ?? 0) * 100)}% vs {Math.round((result.speaking_fraction.b ?? 0) * 100)}%</span>{/if}
    {#if result?.pulse_bpm && (result.pulse_bpm.a || result.pulse_bpm.b)}<span class="muted mono">pulse est. {result.pulse_bpm.a ?? '-'} vs {result.pulse_bpm.b ?? '-'} bpm</span>{/if}
    {#if busy}<span class="muted">computing</span>{/if}
    {#if err}<span class="warn">{err}</span>{/if}
  </div>
  {#if result && a && b}
    <div class="grid">
      <div>
        <div class="eyebrow small">face and head: median shift, B minus A</div>
        <table class="mono">
          <tbody>
            {#each rows as r (r.signal)}
              <tr class:hot={Math.abs(r.shift_sd ?? 0) >= 2}>
                <td class="sig">{human(r.signal)}</td>
                <td class="bar"><span class="track"><i class:neg={(r.shift_sd ?? 0) < 0} style:width="{Math.min(50, Math.abs(r.shift_sd ?? 0) * 8)}%" style:left="{(r.shift_sd ?? 0) < 0 ? 50 - Math.min(50, Math.abs(r.shift_sd ?? 0) * 8) : 50}%"></i></span></td>
                <td class="num">{(r.shift_sd ?? 0) >= 0 ? '+' : ''}{r.shift_sd?.toFixed(1)} SD</td>
                <td class="muted">{r.median_a} to {r.median_b}</td>
              </tr>
            {:else}<tr><td class="muted">not enough frames in one of the spans</td></tr>{/each}
          </tbody>
        </table>
      </div>
      <div>
        <div class="eyebrow small">events per minute</div>
        <table class="mono">
          <tbody>
            {#each evRows as [k, v] (k)}
              <tr><td class="sig">{k.replace(/_/g, ' ')}</td><td class="num">{v.a_per_min}</td><td class="num b">{v.b_per_min}</td><td class="muted">{v.a} / {v.b}</td></tr>
            {:else}<tr><td class="muted">no events in either span</td></tr>{/each}
          </tbody>
        </table>
        {#if voice.length}
          <div class="eyebrow small">voice</div>
          <table class="mono">
            <tbody>
              {#each voice as r (r.signal)}
                <tr class:hot={Math.abs(r.shift_sd ?? 0) >= 2}><td class="sig">{human(r.signal)}</td><td class="num">{(r.shift_sd ?? 0) >= 0 ? '+' : ''}{r.shift_sd?.toFixed(1)} SD</td><td class="muted">{r.median_a} to {r.median_b} {r.unit ?? ''}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
        <p class="caveat">Two spans of one person, same camera. A shift says the medians differ; it does not say why. Speaking vs silent spans differ in every mouth signal by construction.</p>
      </div>
    </div>
  {/if}
</section>

<style>
  .cmp { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 14px 12px; }
  .hdr { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; font-size: 11.5px; }
  .preset { display: flex; gap: 6px; align-items: center; }
  .preset select { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 2px 6px; font-size: 11px; max-width: 150px; }
  .clear { margin-left: auto; padding: 1px 8px; font-size: 11px; }
  .spans { display: flex; gap: 16px; margin: 8px 0 6px; font-size: 12px; align-items: baseline; flex-wrap: wrap; }
  .span b { font-family: var(--font-data); font-weight: 600; padding: 0 6px; border-radius: 2px; margin-right: 6px; }
  .span.a b { background: var(--accent-soft); color: var(--accent); }
  .span.b b { background: rgba(127, 180, 232, 0.16); color: var(--cool); }
  .grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 8px 24px; }
  .small { font-size: 10px; margin: 6px 0 4px; }
  table { border-collapse: collapse; width: 100%; font-size: 11.5px; }
  td { padding: 2px 6px 2px 0; white-space: nowrap; }
  .sig { color: var(--text); max-width: 150px; overflow: hidden; text-overflow: ellipsis; }
  .bar { width: 38%; }
  .track { position: relative; display: block; height: 7px; background: var(--panel-2); border-radius: 2px; }
  .track::after { content: ''; position: absolute; left: 50%; top: -2px; bottom: -2px; width: 1px; background: var(--line-strong); }
  .track i { position: absolute; top: 0; height: 100%; background: var(--cool); border-radius: 2px; }
  .track i.neg { background: var(--accent); }
  .num { text-align: right; color: var(--text); }
  .num.b { color: var(--cool); }
  tr.hot .sig, tr.hot .num { color: var(--accent); }
  .caveat { font-size: 11px; color: var(--muted); margin: 8px 0 0; max-width: 60ch; }
  .warn { color: var(--warn); }
</style>
