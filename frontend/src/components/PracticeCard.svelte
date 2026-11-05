<script lang="ts">
  import { api, tc } from '../lib/api'
  let { sessionId, playhead, onseek }: { sessionId: string; playhead: number; onseek: (us: number) => void } = $props()
  let doc = $state<any>(null)
  let canvas = $state<HTMLCanvasElement | null>(null)
  let wrap = $state<HTMLDivElement | null>(null)
  let width = $state(800)
  $effect(() => { const id = sessionId; doc = null; api.practice(id).then((d) => { if (id === sessionId) doc = d }).catch(() => (doc = null)) })
  $effect(() => { if (wrap) { const ro = new ResizeObserver(() => (width = wrap!.clientWidth)); ro.observe(wrap); width = wrap.clientWidth; return () => ro.disconnect() } })
  const pct = (x: number | null | undefined) => (x == null ? '-' : `${Math.round(x * 100)}%`)
  const sgn = (x: number | null | undefined) => (x == null ? '-' : `${x >= 0 ? '+' : ''}${x.toFixed(2)}`)
  function css(n: string) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim() || '#888' }
  function draw() {
    const c = canvas, s = doc?.affect_series
    if (!c || !s || !s.t_us.length) return
    const H = 120, W = width, dpr = window.devicePixelRatio || 1
    c.width = W * dpr; c.height = H * dpr; c.style.width = W + 'px'; c.style.height = H + 'px'
    const g = c.getContext('2d')!; g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H)
    const t0 = s.t_us[0], t1 = s.t_us[s.t_us.length - 1] || 1, L = 70
    const x = (t: number) => L + ((t - t0) / Math.max(1, t1 - t0)) * (W - L - 8)
    const lane = (key: 'valence' | 'arousal', y0: number, h: number, posCol: string, negCol: string, label: string) => {
      const mid = y0 + h / 2
      g.fillStyle = css('--muted'); g.font = '10.5px "JetBrains Mono", monospace'; g.textBaseline = 'middle'; g.fillText(label, 6, mid)
      g.strokeStyle = css('--line'); g.beginPath(); g.moveTo(L, mid); g.lineTo(W - 8, mid); g.stroke()
      const vals = s[key] as (number | null)[]
      for (let i = 1; i < vals.length; i++) {
        const v = vals[i]; if (v == null) continue
        g.fillStyle = v >= 0 ? posCol : negCol; g.globalAlpha = 0.75
        const xx = x(s.t_us[i - 1]), ww = Math.max(1, x(s.t_us[i]) - xx)
        g.fillRect(xx, v >= 0 ? mid - v * (h / 2 - 2) : mid, ww, Math.abs(v) * (h / 2 - 2))
      }
      g.globalAlpha = 1
    }
    lane('valence', 4, 54, css('--ok'), css('--warn'), 'valence')
    lane('arousal', 62, 54, css('--accent'), css('--cool'), 'arousal')
    const cal = (doc.calibration_end_s ?? 0) * 1e6
    if (cal > t0) { g.fillStyle = 'rgba(127,180,232,0.08)'; g.fillRect(L, 0, x(cal) - L, H) }
    g.strokeStyle = css('--text'); g.beginPath(); g.moveTo(x(playhead), 0); g.lineTo(x(playhead), H); g.stroke()
  }
  $effect(() => { void doc; void width; void playhead; draw() })
  function click(e: MouseEvent) {
    const s = doc?.affect_series; if (!s?.t_us.length) return
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect(), L = 70
    const f = (e.clientX - r.left - L) / Math.max(1, r.width - L - 8)
    if (f >= 0 && f <= 1) onseek(s.t_us[0] + f * (s.t_us[s.t_us.length - 1] - s.t_us[0]))
  }
</script>

{#if doc && doc.status === 'done'}
<section class="practice">
  <div class="hdr"><span class="eyebrow">session overview</span><span class="muted">{doc.note}</span></div>
  <div class="tiles">
    <div class="tile"><span class="v mono">{sgn(doc.affect?.valence_mean)}</span><span class="k">valence, mean</span><span class="s">{pct(doc.affect?.positive_share)} more positive, {pct(doc.affect?.negative_share)} more negative</span></div>
    <div class="tile"><span class="v mono">{sgn(doc.affect?.arousal_mean)}</span><span class="k">arousal, mean</span><span class="s">{pct(doc.affect?.activated_share)} activated, {pct(doc.affect?.calm_share)} calm</span></div>
    <div class="tile"><span class="v mono">{pct(doc.engagement?.share)}</span><span class="k">oriented to the conversation</span><span class="s">{doc.gaze_away} times looked away for 1 s or more</span></div>
    {#if doc.talk}
      <div class="tile talk">
        <span class="k">talk time</span>
        <div class="bar"><i class="c" style:width="{(doc.talk.client_share ?? 0) * 100}%"></i></div>
        <span class="s mono">client {Math.round(doc.talk.client_s)} s ({pct(doc.talk.client_share)}), {doc.talk.client_turns} turns; others {Math.round(doc.talk.other_s)} s, {doc.talk.other_turns} turns</span>
      </div>
    {:else}
      <div class="tile"><span class="v mono">-</span><span class="k">talk time</span><span class="s">needs the microphone</span></div>
    {/if}
    <div class="tile"><span class="v mono">{doc.speech_rate_syl_s ?? '-'}</span><span class="k">syllables per second</span><span class="s">{doc.pauses} long pauses</span></div>
    <div class="tile"><span class="v mono">{doc.patterns.positive} / {doc.patterns.negative}</span><span class="k">positive / negative patterns</span><span class="s">{doc.patterns.per_min} per minute in total</span></div>
  </div>
  <div class="chart" bind:this={wrap}><canvas bind:this={canvas} onclick={click} aria-label="valence and arousal over time; click to seek"></canvas></div>
  <div class="foot muted mono">{tc(0).slice(3)} to {tc(doc.duration_s * 1e6).slice(3)}. Shaded: calibration. Green and amber above the line, red and blue below.</div>
</section>
{/if}

<style>
  .practice { border-top: 1px solid var(--line); background: var(--panel); padding: 10px 16px 12px; }
  .hdr { display: flex; gap: 12px; align-items: baseline; font-size: 11.5px; flex-wrap: wrap; }
  .tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 8px; margin: 10px 0; }
  .tile { background: var(--panel-2); padding: 10px 12px; display: flex; flex-direction: column; gap: 2px; border-left: 2px solid var(--line-strong); }
  .v { font-size: 20px; color: var(--text); }
  .k { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .s { font-size: 11.5px; color: var(--muted); }
  .talk { grid-column: span 2; }
  .bar { height: 10px; background: var(--cool); opacity: 0.85; border-radius: 2px; overflow: hidden; margin: 6px 0 4px; }
  .bar .c { display: block; height: 100%; background: var(--accent); }
  canvas { display: block; cursor: crosshair; }
  .foot { font-size: 11px; margin-top: 4px; }
</style>
