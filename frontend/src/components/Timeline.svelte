<script lang="ts">
  import { tc } from '../lib/api'
  import type { Baseline, FeatureSeries, LmEvent } from '../lib/types'

  let {
    events, video, audio, baseline, audioBaseline, duration, selected, onpick, onseek,
    playhead = $bindable(0),
  }: {
    events: LmEvent[]; video: FeatureSeries | null; audio: FeatureSeries | null
    baseline: Baseline | null; audioBaseline: Baseline | null; duration: number
    selected: LmEvent | null; onpick: (e: LmEvent) => void; onseek: (us: number) => void; playhead: number
  } = $props()

  const ZLIM = 6
  const LANE_H = 44
  const LABEL_W = 168
  const RULER_H = 22
  const EVENT_H = 26

  let canvas = $state<HTMLCanvasElement | null>(null)
  let wrap = $state<HTMLDivElement | null>(null)
  let width = $state(800)
  let hover = $state<{ x: number; us: number } | null>(null)

  type Lane = { name: string; series: (number | null)[]; t: number[]; base: { center: number | null; scale: number | null; unit: string } | null; color: string }

  const lanes = $derived.by((): Lane[] => {
    const out: Lane[] = []
    const add = (fs: FeatureSeries | null, b: Baseline | null, color: (n: string) => string) => {
      if (!fs) return
      for (const [name, series] of Object.entries(fs.signals)) {
        if (name === 'quality') continue
        const sb = b?.signals[name]
        out.push({ name, series, t: fs.t_us, base: sb ? { center: sb.center, scale: sb.scale, unit: sb.unit } : null, color: color(name) })
      }
    }
    add(video, baseline, (n) => (n.startsWith('eye.') || n.startsWith('head.') ? 'var(--cool)' : 'var(--accent)'))
    add(audio, audioBaseline, () => 'var(--teal)')
    return out
  })

  const total = $derived(Math.max(duration, ...lanes.map((l) => l.t[l.t.length - 1] ?? 0), 1))
  const height = $derived(RULER_H + EVENT_H + lanes.length * LANE_H + 8)
  const xOf = (us: number) => LABEL_W + ((width - LABEL_W - 12) * us) / total
  const usOf = (x: number) => Math.max(0, Math.min(total, ((x - LABEL_W) / (width - LABEL_W - 12)) * total))

  function cssVar(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name.replace(/var\((.*)\)/, '$1')).trim() || '#888'
  }

  function draw() {
    const c = canvas
    if (!c) return
    const dpr = window.devicePixelRatio || 1
    c.width = Math.floor(width * dpr); c.height = Math.floor(height * dpr)
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const col = { line: cssVar('--line'), lineS: cssVar('--line-strong'), muted: cssVar('--muted'), text: cssVar('--text'), accent: cssVar('--accent'), soft: cssVar('--accent-soft'), teal: cssVar('--teal'), cool: cssVar('--cool'), panel: cssVar('--panel-2'), faint: cssVar('--faint') }
    ctx.clearRect(0, 0, width, height)
    ctx.font = '10.5px "JetBrains Mono", monospace'
    ctx.textBaseline = 'middle'

    // ruler
    const step = niceStep(total)
    ctx.strokeStyle = col.line; ctx.fillStyle = col.muted
    for (let us = 0; us <= total; us += step) {
      const x = xOf(us)
      ctx.beginPath(); ctx.moveTo(x, RULER_H - 6); ctx.lineTo(x, height); ctx.stroke()
      ctx.fillText(tc(us).slice(3), x + 3, RULER_H / 2)
    }

    // baseline window shading
    if (baseline) {
      ctx.fillStyle = 'rgba(127,180,232,0.05)'
      ctx.fillRect(xOf(0), RULER_H, xOf(baseline.window_end_us) - xOf(0), height - RULER_H)
    }

    // event strip
    const ey = RULER_H
    ctx.fillStyle = col.panel; ctx.fillRect(LABEL_W, ey, width - LABEL_W - 12, EVENT_H)
    ctx.fillStyle = col.muted; ctx.textAlign = 'left'; ctx.fillText('events', 8, ey + EVENT_H / 2)
    for (const e of events) {
      if (e.event_type === 'blink') { ctx.fillStyle = col.cool; ctx.globalAlpha = 0.55; ctx.fillRect(xOf(e.start_us), ey + EVENT_H - 5, Math.max(1, xOf(e.end_us) - xOf(e.start_us)), 3); ctx.globalAlpha = 1; continue }
      const x0 = xOf(e.start_us), x1 = Math.max(x0 + 2, xOf(e.end_us))
      const sel = selected?.event_id === e.event_id
      ctx.fillStyle = e.source === 'audio' ? col.teal : col.accent
      ctx.globalAlpha = sel ? 1 : 0.7
      const h = e.level === 'interpretation' ? EVENT_H - 8 : EVENT_H - 14
      ctx.fillRect(x0, ey + (EVENT_H - h) / 2, x1 - x0, h)
      ctx.globalAlpha = 1
      if (sel) { ctx.strokeStyle = col.text; ctx.strokeRect(x0 - 1.5, ey + 1.5, x1 - x0 + 3, EVENT_H - 3) }
    }

    // lanes in robust SD units
    lanes.forEach((lane, i) => {
      const y0 = RULER_H + EVENT_H + i * LANE_H
      const ymid = y0 + LANE_H / 2
      const scaleY = (LANE_H - 10) / (2 * ZLIM)
      ctx.strokeStyle = col.line; ctx.beginPath(); ctx.moveTo(LABEL_W, y0 + LANE_H); ctx.lineTo(width, y0 + LANE_H); ctx.stroke()
      // threshold guides at +-3 SD
      ctx.strokeStyle = col.faint; ctx.setLineDash([2, 4])
      for (const z of [3, -3]) { const y = ymid - z * scaleY; ctx.beginPath(); ctx.moveTo(LABEL_W, y); ctx.lineTo(width - 12, y); ctx.stroke() }
      ctx.setLineDash([])
      ctx.strokeStyle = col.lineS; ctx.beginPath(); ctx.moveTo(LABEL_W, ymid); ctx.lineTo(width - 12, ymid); ctx.stroke()
      // label
      ctx.fillStyle = col.text; ctx.textAlign = 'left'; ctx.fillText(lane.name, 8, y0 + 14)
      ctx.fillStyle = col.muted
      const b = lane.base
      ctx.fillText(b && b.center != null ? `med ${fmt(b.center)} sd ${fmt(b.scale ?? 0)} ${b.unit}` : 'no baseline', 8, y0 + 30)
      // event spans on this lane
      for (const e of events) {
        if (!e.contributions.some((c) => c.feature === lane.name)) continue
        ctx.fillStyle = e.source === 'audio' ? col.teal : col.accent; ctx.globalAlpha = 0.14
        ctx.fillRect(xOf(e.start_us), y0 + 2, Math.max(2, xOf(e.end_us) - xOf(e.start_us)), LANE_H - 4); ctx.globalAlpha = 1
      }
      // series
      if (!b || b.center == null || !b.scale) return
      ctx.strokeStyle = cssVar(lane.color); ctx.lineWidth = 1.1; ctx.beginPath()
      let pen = false
      for (let k = 0; k < lane.series.length; k++) {
        const v = lane.series[k]
        if (v == null) { pen = false; continue }
        const z = Math.max(-ZLIM, Math.min(ZLIM, (v - b.center) / b.scale))
        const x = xOf(lane.t[k]), y = ymid - z * scaleY
        if (!pen) { ctx.moveTo(x, y); pen = true } else ctx.lineTo(x, y)
      }
      ctx.stroke(); ctx.lineWidth = 1
    })

    // playhead + hover
    const px = xOf(playhead)
    ctx.strokeStyle = col.text; ctx.beginPath(); ctx.moveTo(px, RULER_H - 8); ctx.lineTo(px, height); ctx.stroke()
    ctx.fillStyle = col.text; ctx.beginPath(); ctx.moveTo(px - 4, RULER_H - 8); ctx.lineTo(px + 4, RULER_H - 8); ctx.lineTo(px, RULER_H - 2); ctx.fill()
    if (hover) { ctx.strokeStyle = col.muted; ctx.setLineDash([3, 3]); ctx.beginPath(); ctx.moveTo(hover.x, RULER_H); ctx.lineTo(hover.x, height); ctx.stroke(); ctx.setLineDash([]) }
  }

  function niceStep(total: number): number {
    const target = total / Math.max(4, (width - LABEL_W) / 110)
    const steps = [100e3, 250e3, 500e3, 1e6, 2e6, 5e6, 10e6, 15e6, 30e6, 60e6, 120e6, 300e6, 600e6]
    return steps.find((s) => s >= target) ?? steps[steps.length - 1]
  }
  const fmt = (v: number) => (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(3))

  function onMove(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const x = e.clientX - r.left
    hover = x >= LABEL_W ? { x, us: usOf(x) } : null
  }
  function onClick(e: MouseEvent) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    const x = e.clientX - r.left, y = e.clientY - r.top
    if (x < LABEL_W) return
    const us = usOf(x)
    if (y >= RULER_H && y < RULER_H + EVENT_H) {
      const hit = events.filter((ev) => ev.event_type !== 'blink' && ev.start_us <= us && us <= ev.end_us).sort((a, b) => b.severity - a.severity)[0]
      if (hit) { onpick(hit); return }
    }
    onseek(us)
  }

  $effect(() => { if (wrap) { const ro = new ResizeObserver(() => (width = wrap!.clientWidth)); ro.observe(wrap); width = wrap.clientWidth; return () => ro.disconnect() } })
  $effect(() => { draw() })
</script>

<div class="timeline" bind:this={wrap}>
  <div class="hdr">
    <span class="eyebrow">timeline</span>
    <span class="muted">lanes in robust SD from baseline (median / 1.4826 MAD). dashed = +-3 SD. shaded = calibration window. click the event strip to inspect, elsewhere to seek.</span>
    {#if hover}<span class="mono hov">{tc(hover.us)}</span>{/if}
  </div>
  <canvas bind:this={canvas} style="width:{width}px;height:{height}px" onmousemove={onMove} onmouseleave={() => (hover = null)} onclick={onClick}></canvas>
</div>

<style>
  .timeline { border-top: 1px solid var(--line); background: var(--panel); padding: 8px 12px 6px 0; overflow: hidden; }
  .hdr { display: flex; gap: 14px; align-items: baseline; padding: 0 0 6px 8px; font-size: 11.5px; }
  .hov { margin-left: auto; color: var(--text); }
  canvas { display: block; cursor: crosshair; }
</style>
