<script lang="ts">
  import { onDestroy } from 'svelte'
  import { tc } from '../lib/api'
  import { LiveSession, listCameras, type LiveBaselineMsg, type LiveFrameMsg, type LiveMsg } from '../lib/live'
  import { CALIBRATION_SECONDS, PASSAGE, phaseAt } from '../lib/calibration'
  import type { LmEvent } from '../lib/types'

  let { ondone }: { ondone: (sessionId: string) => void } = $props()

  let videoEl = $state<HTMLVideoElement | null>(null)
  let overlay = $state<HTMLCanvasElement | null>(null)
  let lanesEl = $state<HTMLCanvasElement | null>(null)
  let cameras = $state<MediaDeviceInfo[]>([])
  let camera = $state<string>('')
  let useAu = $state(true)
  let useAudio = $state(true)
  let state = $state<'idle' | 'connecting' | 'running' | 'stopped' | 'error'>('idle')
  let detail = $state<string>('')
  let last = $state<LiveFrameMsg | null>(null)
  let audioLast = $state<{ speech_prob: number; f0_hz: number | null; energy_db: number; voiced: boolean } | null>(null)
  let events = $state<LmEvent[]>([])
  let session: LiveSession | null = null
  let sessionId = $state<string | null>(null)
  let showAll = $state(false)
  let calib = $state<{ name: string; instruction: string; remaining: number; speaking: boolean } | null>(null)
  let baselineInfo = $state<LiveBaselineMsg | null>(null)
  let lastPhaseSpeaking: boolean | null = null
  const shown = $derived(showAll ? events : events.filter((e) => e.event_type === 'episode' || e.source === 'audio'))
  const sev = (v: number) => (v > 20 ? '>20' : v.toFixed(1))

  const WINDOW_US = 60e6
  const LANES = ['head.yaw_deg', 'eye.aspect_ratio_mean', 'blendshape.browDownLeft', 'au.AU4', 'au.AU12', 'voice.f0_hz', 'voice.energy_db']
  // rolling raw values per lane; drawn as raw values scaled to a running min/max until the server
  // baseline is ready (we do not have the baseline numbers client-side; the lanes show shape, the
  // events carry the SD numbers)
  const hist: Record<string, { t: number[]; v: number[] }> = Object.fromEntries(LANES.map((n) => [n, { t: [], v: [] }]))

  async function refreshCams() { try { cameras = await listCameras(); if (!camera && cameras[0]) camera = cameras[0].deviceId } catch {} }
  refreshCams()

  function push(name: string, t: number, v: number | null | undefined) {
    if (v == null || !isFinite(v)) return
    const h = hist[name]; if (!h) return
    h.t.push(t); h.v.push(v)
    while (h.t.length && h.t[0] < t - WINDOW_US) { h.t.shift(); h.v.shift() }
  }

  function onmessage(m: LiveMsg) {
    if (m.type === 'frame') {
      last = m
      if (!m.baseline_ready) {
        const ph = phaseAt(m.t_us / 1e6)
        calib = ph ? { name: ph.phase.name, instruction: ph.phase.instruction, remaining: ph.remaining, speaking: ph.phase.speaking } : { name: 'finishing', instruction: 'Hold on, computing the baseline.', remaining: 0, speaking: false }
        if (ph && ph.phase.speaking !== lastPhaseSpeaking) { lastPhaseSpeaking = ph.phase.speaking; session?.setPhase(ph.phase.speaking) }
      } else if (calib) {
        calib = null
      }
      for (const n of LANES) push(n, m.t_us, m.values[n])
      drawOverlay(m); drawLanes(m.t_us)
    } else if (m.type === 'audio') {
      audioLast = m
      push('voice.f0_hz', m.t_us, m.f0_hz); push('voice.energy_db', m.t_us, m.energy_db)
    } else if (m.type === 'events') {
      events = [...m.events.filter((e: LmEvent) => e.event_type !== 'blink'), ...events].slice(0, 300)
    } else if (m.type === 'baseline') {
      baselineInfo = m
    } else if (m.type === 'session') {
      sessionId = m.session_id
    }
  }

  function drawOverlay(m: LiveFrameMsg) {
    const c = overlay, v = videoEl
    if (!c || !v || !v.videoWidth) return
    const dpr = window.devicePixelRatio || 1
    const rect = v.getBoundingClientRect()
    c.width = rect.width * dpr; c.height = rect.height * dpr
    c.style.width = rect.width + 'px'; c.style.height = rect.height + 'px'
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, rect.width, rect.height)
    // object-fit: contain mapping
    const scale = Math.min(rect.width / v.videoWidth, rect.height / v.videoHeight)
    const dw = v.videoWidth * scale, dh = v.videoHeight * scale
    const ox = (rect.width - dw) / 2, oy = (rect.height - dh) / 2
    if (m.landmarks) {
      ctx.fillStyle = 'rgba(127,180,232,0.75)'
      for (let i = 0; i < m.landmarks.length; i += 2) ctx.fillRect(ox + m.landmarks[i] * dw - 0.6, oy + m.landmarks[i + 1] * dh - 0.6, 1.2, 1.2)
    }
    if (m.bbox) {
      const [x0, y0, x1, y1] = m.bbox
      ctx.strokeStyle = m.baseline_ready ? '#d4a24c' : '#7fb4e8'; ctx.lineWidth = 1
      ctx.strokeRect(ox + x0 * dw, oy + y0 * dh, (x1 - x0) * dw, (y1 - y0) * dh)
    }
  }

  function drawLanes(now: number) {
    const c = lanesEl
    if (!c) return
    const W = c.clientWidth, H = LANES.length * 34 + 4
    const dpr = window.devicePixelRatio || 1
    c.width = W * dpr; c.height = H * dpr; c.style.height = H + 'px'
    const ctx = c.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.font = '10.5px "JetBrains Mono", monospace'; ctx.textBaseline = 'middle'
    const labelW = 150
    const x = (t: number) => labelW + ((t - (now - WINDOW_US)) / WINDOW_US) * (W - labelW - 8)
    LANES.forEach((name, i) => {
      const y0 = 2 + i * 34, h = 30
      ctx.strokeStyle = '#1f2933'; ctx.beginPath(); ctx.moveTo(labelW, y0 + h); ctx.lineTo(W, y0 + h); ctx.stroke()
      ctx.fillStyle = '#d7dee7'; ctx.fillText(name, 6, y0 + 10)
      const hh = hist[name]
      const cur = hh.v.length ? hh.v[hh.v.length - 1] : null
      ctx.fillStyle = '#7c8794'; ctx.fillText(cur == null ? '-' : Math.abs(cur) >= 100 ? cur.toFixed(0) : cur.toFixed(2), 6, y0 + 23)
      if (hh.v.length < 2) return
      let lo = Infinity, hi = -Infinity
      for (const v of hh.v) { if (v < lo) lo = v; if (v > hi) hi = v }
      if (hi - lo < 1e-6) { lo -= 0.5; hi += 0.5 }
      ctx.strokeStyle = name.startsWith('voice.') ? '#5fb8ae' : name.startsWith('au.') || name.startsWith('blendshape.') ? '#d4a24c' : '#7fb4e8'
      ctx.lineWidth = 1; ctx.beginPath()
      for (let k = 0; k < hh.v.length; k++) {
        const px = x(hh.t[k]), py = y0 + 3 + (1 - (hh.v[k] - lo) / (hi - lo)) * (h - 6)
        if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
      }
      ctx.stroke()
    })
    for (const e of events) {
      if (e.end_us < now - WINDOW_US) continue
      ctx.fillStyle = e.source === 'audio' ? 'rgba(95,184,174,0.18)' : 'rgba(212,162,76,0.18)'
      ctx.fillRect(x(e.start_us), 0, Math.max(2, x(e.end_us) - x(e.start_us)), H)
    }
  }

  async function start() {
    if (!videoEl) return
    events = []; sessionId = null; audioLast = null; last = null; baselineInfo = null; calib = null; lastPhaseSpeaking = null
    for (const n of LANES) { hist[n].t = []; hist[n].v = [] }
    session = new LiveSession(videoEl, {
      au: useAu, audio: useAudio, fps: 15, width: 640, jpegQuality: 0.72,
      onmessage,
      onstate: (s, d) => { state = s; detail = d ?? '' },
    })
    try { await session.start(camera || undefined) } catch (e) { state = 'error'; detail = String(e) }
  }
  function stop() { session?.stop() }
  onDestroy(() => session?.stop())
</script>

<section class="live">
  <div class="controls">
    <span class="eyebrow">live analysis</span>
    <select bind:value={camera} disabled={state === 'running' || state === 'connecting'}>
      {#each cameras as c}<option value={c.deviceId}>{c.label || 'camera'}</option>{/each}
    </select>
    <label><input type="checkbox" bind:checked={useAu} disabled={state === 'running'} /> action units (resnet18)</label>
    <label><input type="checkbox" bind:checked={useAudio} disabled={state === 'running'} /> microphone</label>
    {#if state === 'running' || state === 'connecting'}
      <button class="primary" onclick={stop}>stop and save</button>
    {:else}
      <button class="primary" onclick={start}>start</button>
    {/if}
    <span class="status mono" class:rec={state === 'running'}>{state}{detail ? ': ' + detail : ''}</span>
    {#if sessionId}<button onclick={() => ondone(sessionId!)}>open session {sessionId}</button>{/if}
  </div>
  <div class="stage">
    <div class="cam">
      <video bind:this={videoEl} muted playsinline></video>
      <canvas bind:this={overlay} class="overlay"></canvas>
      {#if state === 'running'}
        <div class="badge"><span class="dot"></span> LIVE ANALYSIS. frames analyzed in memory, not stored.</div>
      {/if}
      {#if calib}
        <div class="calib">
          <div class="calib-hdr"><span class="eyebrow">calibration {calib.name}</span><span class="mono">{Math.ceil(calib.remaining)} s</span></div>
          <div class="calib-bar"><i style="width:{Math.min(100, 100 * (1 - calib.remaining / CALIBRATION_SECONDS))}%"></i></div>
          <p class="instr">{calib.instruction}</p>
          {#if calib.speaking}<p class="passage">{PASSAGE}</p>{/if}
        </div>
      {:else if baselineInfo && last && last.t_us < (CALIBRATION_SECONDS + 8) * 1e6}
        <div class="calib done">
          <span class="eyebrow">baseline ready</span>
          <p class="instr mono">{baselineInfo.frames_used} frames, quality {baselineInfo.quality.toFixed(2)}{#each Object.entries(baselineInfo.states) as [k, v]} / {k} {v.frames_used}{/each}</p>
          {#if !baselineInfo.states.speaking}<p class="instr warn">no speaking-state baseline: mouth events while talking will be tagged, not scored fairly</p>{/if}
        </div>
      {/if}
      {#if last}
        <div class="readout mono">
          <div>{tc(last.t_us)}</div>
          <div>{last.baseline_ready ? 'baseline ready' : 'calibrating baseline'} quality {last.quality.toFixed(2)}</div>
          {#if last.values['head.yaw_deg'] != null}<div>yaw {last.values['head.yaw_deg'].toFixed(0)} pitch {last.values['head.pitch_deg'].toFixed(0)} roll {last.values['head.roll_deg'].toFixed(0)}</div>{/if}
          {#if audioLast}<div>speech {audioLast.speech_prob.toFixed(2)} f0 {audioLast.f0_hz ? audioLast.f0_hz.toFixed(0) + ' Hz' : '-'} {audioLast.energy_db.toFixed(0)} dB</div>{/if}
          <div class="muted">{last.stats.analyzed_fps.toFixed(1)} fps, latency {last.stats.latency_ms_p50?.toFixed(0) ?? '-'} ms, dropped {last.stats.frames_dropped}</div>
        </div>
      {/if}
    </div>
    <div class="side">
      <div class="side-hdr"><span class="eyebrow">{showAll ? 'all events' : 'episodes and voice'}</span><button onclick={() => (showAll = !showAll)}>{showAll ? 'episodes' : 'all'}</button></div>
      <ul>
        {#each shown as e (e.event_id)}
          <li class:audio={e.source === 'audio'} class:episode={e.event_type === 'episode'}><span class="mono">{tc(e.start_us).slice(3)}</span> <span class="lbl">{e.label}{#if e.tags.includes('speaking')} <em class="tag">speaking</em>{/if}</span> <span class="mono sev">{sev(e.severity)}</span></li>
        {:else}
          <li class="muted">none yet. the first 30 s calibrate the baseline.</li>
        {/each}
      </ul>
    </div>
  </div>
  <canvas bind:this={lanesEl} class="lanes"></canvas>
</section>

<style>
  .live { grid-area: stage; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-height: 0; }
  .controls { display: flex; gap: 12px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--line); background: var(--panel); flex-wrap: wrap; font-size: 12px; }
  select { background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 4px 8px; max-width: 220px; }
  .status { color: var(--muted); }
  .status.rec { color: var(--warn); }
  .stage { display: grid; grid-template-columns: minmax(0, 1fr) 300px; min-height: 0; }
  .cam { position: relative; background: #05070a; display: grid; place-items: center; min-height: 0; }
  video { max-width: 100%; max-height: 100%; width: 100%; height: 100%; object-fit: contain; display: block; }
  .overlay { position: absolute; inset: 0; pointer-events: none; }
  .badge { position: absolute; top: 10px; left: 12px; display: flex; gap: 8px; align-items: center; background: rgba(5,7,10,0.7); border: 1px solid var(--warn); color: var(--text); padding: 4px 10px; font-size: 11.5px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--warn); }
  .calib { position: absolute; left: 12px; right: 12px; top: 44px; max-width: 720px; margin: 0 auto; background: rgba(5,7,10,0.82); border: 1px solid var(--accent); padding: 12px 16px; }
  .calib.done { border-color: var(--ok); }
  .calib-hdr { display: flex; justify-content: space-between; align-items: baseline; }
  .calib-bar { height: 4px; background: var(--line); margin: 6px 0 10px; }
  .calib-bar i { display: block; height: 100%; background: var(--accent); }
  .instr { margin: 0 0 8px; font-size: 14px; }
  .instr.warn { color: var(--warn); font-size: 12px; }
  .passage { margin: 0; font-size: 19px; line-height: 1.5; color: var(--text); font-family: var(--font-ui); text-wrap: pretty; }
  .readout { position: absolute; right: 12px; bottom: 10px; text-align: right; background: rgba(5,7,10,0.65); padding: 6px 10px; font-size: 11.5px; line-height: 1.5; }
  .side { border-left: 1px solid var(--line); background: var(--panel); padding: 10px 14px; overflow-y: auto; min-height: 0; }
  ul { list-style: none; margin: 8px 0 0; padding: 0; font-size: 12px; }
  li { padding: 5px 0; border-bottom: 1px solid var(--line); display: flex; gap: 8px; }
  li .sev { margin-left: auto; color: var(--accent); }
  li .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li.episode { border-left: 2px solid var(--accent); padding-left: 6px; }
  .tag { font-style: normal; color: var(--muted); font-size: 10.5px; border: 1px solid var(--line-strong); padding: 0 4px; border-radius: 2px; }
  .side-hdr { display: flex; justify-content: space-between; align-items: center; }
  .side-hdr button { padding: 1px 8px; font-size: 11px; }
  li.audio .sev { color: var(--teal); }
  .lanes { width: 100%; display: block; border-top: 1px solid var(--line); background: var(--panel); }
</style>
