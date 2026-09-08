<script lang="ts">
  import { api } from '../lib/api'
  import type { FrameSnapshot } from '../lib/types'
  import { auName, patternScores, PATTERN_ENTER } from '../lib/facs'

  let { sessionId, playhead }: { sessionId: string; playhead: number } = $props()
  let snap = $state<FrameSnapshot | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null
  let inflight = 0

  // Debounced fetch of the nearest analyzed frame; the newest request wins.
  $effect(() => {
    const id = sessionId, t = playhead
    if (timer) clearTimeout(timer)
    timer = setTimeout(async () => {
      const seq = ++inflight
      try { const s = await api.frame(id, t); if (seq === inflight) snap = s } catch { /* keep last */ }
    }, 90)
  })

  const values = $derived<Record<string, number>>(Object.fromEntries(Object.entries(snap?.values ?? {}).filter(([, v]) => v != null) as [string, number][]))
  const z = (k: string): number | null => {
    const b = snap?.baseline[k]; const v = values[k]
    return b && b.center != null && b.scale != null && b.scale > 0 && v != null ? (v - b.center) / b.scale : null
  }
  const aus = $derived(Object.entries(values).filter(([k, v]) => k.startsWith('au.AU') && !/AU[LR]/.test(k) && v >= 0.15).sort((a, b) => b[1] - a[1]).slice(0, 8))
  const pats = $derived(patternScores(values).filter((p) => p.score >= 0.2).slice(0, 3))
  const fmt = (v: number | undefined, d = 1) => (v == null ? '-' : v.toFixed(d))
  const fz = (v: number | null) => (v == null ? '' : `${v >= 0 ? '+' : ''}${v.toFixed(1)} SD`)
  const head = $derived({ yaw: values['head.yaw_deg'], pitch: values['head.pitch_deg'], roll: values['head.roll_deg'], speed: values['head.speed_deg_s'] })
  const gazeText = $derived.by(() => {
    const h = values['gaze.horizontal'], v = values['gaze.vertical']
    if (h == null || v == null) return '-'
    const parts: string[] = []
    if (Math.abs(h) >= 0.15) parts.push(h > 0 ? 'right' : 'left')
    if (Math.abs(v) >= 0.15) parts.push(v > 0 ? 'up' : 'down')
    return parts.length ? parts.join(' and ') : 'toward camera'
  })
</script>

<section class="frame-panel" aria-label="frame readout">
  <header>
    <span class="eyebrow">at playhead</span>
    {#if snap?.state}<span class="chip" class:speaking={snap.state === 'speaking'}>{snap.state}</span>{/if}
    <span class="mono dim">quality {fmt(values['quality'], 2)}</span>
  </header>
  {#if !snap?.t_us && snap}
    <p class="dim">no per-frame table for this session.</p>
  {:else}
    <div class="grid">
      <div class="col">
        <div class="eyebrow small">action units, occurrence probability</div>
        {#each aus as [k, v] (k)}
          {@const zz = z(k)}
          <div class="row" class:hot={zz != null && Math.abs(zz) >= 4}>
            <span class="mono code">{k.slice(3)}</span>
            <span class="name">{auName(k)}</span>
            <span class="bar"><i style:width="{Math.round(v * 100)}%"></i></span>
            <span class="mono val">{v.toFixed(2)}</span>
            <span class="mono dim zval">{fz(zz)}</span>
          </div>
        {:else}
          <p class="dim">no AU above 0.15</p>
        {/each}
      </div>
      <div class="col">
        <div class="eyebrow small">pattern (FACS appearance)</div>
        {#each pats as p (p.name)}
          <div class="row" class:on={p.score >= PATTERN_ENTER}>
            <span class="name wide">{p.name}</span>
            <span class="bar violet"><i style:width="{Math.round(p.score * 100)}%"></i></span>
            <span class="mono val">{p.score.toFixed(2)}</span>
          </div>
        {:else}
          <p class="dim">neutral</p>
        {/each}
        <div class="eyebrow small">head and eyes</div>
        <dl>
          <dt>yaw / pitch / roll</dt><dd class="mono">{fmt(head.yaw)} / {fmt(head.pitch)} / {fmt(head.roll)} deg <span class="dim">{fz(z('head.yaw_deg'))}</span></dd>
          <dt>head speed</dt><dd class="mono">{fmt(head.speed, 0)} deg/s <span class="dim">{fz(z('head.speed_deg_s'))}</span></dd>
          <dt>gaze</dt><dd>{gazeText} <span class="mono dim">{fmt(values['gaze.horizontal'], 2)}, {fmt(values['gaze.vertical'], 2)}</span></dd>
          <dt>eye opening</dt><dd class="mono">{fmt(values['eye.aspect_ratio_mean'], 3)} <span class="dim">{fz(z('eye.aspect_ratio_mean'))}</span></dd>
        </dl>
      </div>
    </div>
  {/if}
</section>

<style>
  .frame-panel { border-top: 1px solid var(--line); padding: 10px 14px 12px; background: var(--panel); }
  header { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
  .chip { font: 500 11px/1 var(--font-data); padding: 3px 7px; border-radius: 3px; background: var(--panel-2); color: var(--muted); }
  .chip.speaking { color: var(--teal); background: color-mix(in srgb, var(--teal) 16%, transparent); }
  .grid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 8px 22px; }
  .col { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .small { font-size: 10px; margin-top: 4px; }
  .row { display: grid; grid-template-columns: 38px minmax(0, 1fr) 90px 36px 62px; gap: 8px; align-items: center; font-size: 12px; color: var(--muted); }
  .row.hot { color: var(--accent); }
  .row.hot .bar i { background: var(--accent); }
  .row.on { color: var(--violet); }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .name.wide { grid-column: 1 / 3; }
  .bar { height: 6px; background: var(--panel-2); border-radius: 2px; overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--cool); }
  .bar.violet i { background: var(--violet); }
  .val { text-align: right; color: var(--text); }
  .zval { text-align: right; }
  .code { color: var(--text); }
  dl { display: grid; grid-template-columns: auto 1fr; gap: 3px 12px; margin: 0; font-size: 12px; }
  dt { color: var(--muted); }
  dd { margin: 0; color: var(--text); }
  .dim { color: var(--muted); font-size: 11px; }
  p { margin: 2px 0; }
</style>
