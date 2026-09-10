<script lang="ts">
  import { onDestroy } from 'svelte'
  import { tc } from '../lib/api'
  import { LiveSession, listCameras, type LiveBaselineMsg, type LiveFrameMsg, type LiveMsg } from '../lib/live'
  import { CALIBRATION_SECONDS, PASSAGE, phaseAt } from '../lib/calibration'
  import { DEFAULT_SCRIPT, parseScript, type ScriptQuestion } from '../lib/protocol'
  import { auName, patternScores, PATTERN_ENTER } from '../lib/facs'
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
  let readoutGaze = $derived(last && last.values['gaze.horizontal'] != null ? (Math.abs(last.values['gaze.horizontal']) < 0.15 ? 'gaze center' : last.values['gaze.horizontal'] > 0 ? 'gaze left' : 'gaze right') : '')
  let calib = $state<{ name: string; instruction: string; remaining: number; speaking: boolean } | null>(null)
  let baselineInfo = $state<LiveBaselineMsg | null>(null)
  let lastPhaseSpeaking: boolean | null = null
  const shown = $derived(showAll ? events : events.filter((e) => FLASH_TYPES.has(e.event_type) || e.source === 'audio'))
  const sev = (v: number) => (v > 20 ? '>20' : v.toFixed(1))

  const WINDOW_US = 60e6
  const LANES = ['head.yaw_deg', 'head.speed_deg_s', 'gaze.horizontal', 'blendshape.browInnerUp', 'blendshape.jawOpen', 'asym.mouth_smile', 'au.AU4', 'au.AU12', 'voice.f0_hz', 'voice.energy_db']
  let laneBase = $state<Record<string, { center: number; scale: number }>>({})
  let flashes: { text: string; until: number; color: string }[] = []
  const FLASH_TYPES = new Set(['episode', 'expression_pattern', 'blink_rate_change', 'head_gesture', 'au_novelty', 'pulse_change'])
  let pulseHold = $state<{ bpm: number; snr_db: number; usable: boolean } | null>(null)
  let tally = $state<Record<string, number>>({})
  const TALLY = [['episode', 'episodes'], ['expression_pattern', 'patterns'], ['head_gesture', 'gestures'], ['au_novelty', 'pairings'], ['voice', 'voice'], ['pulse_change', 'pulse'], ['blink', 'blinks']] as const
  let lastBlinkAt = 0
  let showOverlay = $state(true)
  let showProtocol = $state(false)
  let script = $state(DEFAULT_SCRIPT)
  const questions = $derived(parseScript(script))
  let qIndex = $state(-1)
  let asked = $state<{ q: ScriptQuestion; t_us: number; devs: number; latency_ms: number | null }[]>([])
  let noteText = $state('')
  let speakingAtAsk: boolean | null = null
  const currentQ = $derived(qIndex >= 0 && qIndex < asked.length ? asked[qIndex] : null)
  function askNext() {
    if (!last || qIndex + 1 >= questions.length) return
    const q = questions[qIndex + 1]
    qIndex += 1
    asked = [...asked, { q, t_us: last.t_us, devs: 0, latency_ms: null }]
    speakingAtAsk = audioLast ? audioLast.speech_prob >= 0.5 : null
    session?.mark({ kind_of: 'question', id: q.id, text: q.text, category: q.category, expected: q.expected, t_us: last.t_us })
  }
  function endAnswer() {
    if (!last || !currentQ) return
    session?.mark({ kind_of: 'end', t_us: last.t_us })
  }
  function addNote() {
    if (!last || !noteText.trim()) return
    session?.mark({ kind_of: 'note', text: noteText.trim(), t_us: last.t_us })
    noteText = ''
  }
  function onWindowKey(ev: KeyboardEvent) {
    const tag = (ev.target as HTMLElement)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    if (ev.key === 'n' && state === 'running' && showProtocol) { askNext(); ev.preventDefault() }
  }
  $effect(() => { window.addEventListener('keydown', onWindowKey); return () => window.removeEventListener('keydown', onWindowKey) })
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
      last = m; if (m.pulse) pulseHold = m.pulse
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
      if (currentQ && currentQ.latency_ms == null && m.speech_prob >= 0.5 && m.t_us > currentQ.t_us + 150_000) {
        asked[qIndex] = { ...asked[qIndex], latency_ms: (m.t_us - currentQ.t_us) / 1000 }
      }
      push('voice.f0_hz', m.t_us, m.f0_hz); push('voice.energy_db', m.t_us, m.energy_db)
    } else if (m.type === 'events') {
      events = [...m.events.filter((e: LmEvent) => e.event_type !== 'blink'), ...events].slice(0, 300)
      const now = performance.now()
      for (const e of m.events as LmEvent[]) {
        const tk = e.source === 'audio' ? 'voice' : e.event_type
        tally[tk] = (tally[tk] ?? 0) + 1
        if (e.event_type === 'blink') { lastBlinkAt = now; continue }
        if (FLASH_TYPES.has(e.event_type) || e.source === 'audio')
          flashes = [{ text: e.label.replace('expression pattern: ', '').replace('new AU pairing: ', 'new: '), until: now + 2500, color: e.event_type === 'expression_pattern' || e.event_type === 'au_novelty' ? '#b48ce6' : e.event_type === 'head_gesture' ? '#7fb4e8' : e.event_type === 'pulse_change' ? '#e0907a' : e.source === 'audio' ? '#5fb8ae' : '#d4a24c' }, ...flashes].slice(0, 4)
      }
      if (currentQ) { const n = m.events.filter((e: LmEvent) => e.event_type === 'baseline_deviation').length; if (n) asked[qIndex] = { ...asked[qIndex], devs: asked[qIndex].devs + n } }
    } else if (m.type === 'baseline') {
      baselineInfo = m
      if (m.signals) laneBase = m.signals
    } else if (m.type === 'baseline_update') {
      laneBase = m.signals
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
    if (!showOverlay) return
    ctx.font = '11px "JetBrains Mono", monospace'; ctx.textBaseline = 'middle'
    const vals = m.values
    // head pose axes at face center (yaw/pitch/roll in degrees)
    if (m.bbox && vals['head.yaw_deg'] != null) {
      const [x0, y0, x1, y1] = m.bbox
      const cx = ox + ((x0 + x1) / 2) * dw, cy = oy + ((y0 + y1) / 2) * dh, L = 0.25 * (x1 - x0) * dw
      const yaw = (vals['head.yaw_deg'] * Math.PI) / 180, pitch = (vals['head.pitch_deg'] * Math.PI) / 180, roll = (vals['head.roll_deg'] * Math.PI) / 180
      const axis = (x: number, y: number, z: number, color: string) => {
        // rotate unit axis by roll(z), pitch(x), yaw(y); project ignoring depth
        let [X, Y, Z] = [x, y, z]
        ;[Y, Z] = [Y * Math.cos(pitch) - Z * Math.sin(pitch), Y * Math.sin(pitch) + Z * Math.cos(pitch)]
        ;[X, Z] = [X * Math.cos(yaw) + Z * Math.sin(yaw), -X * Math.sin(yaw) + Z * Math.cos(yaw)]
        ;[X, Y] = [X * Math.cos(roll) - Y * Math.sin(roll), X * Math.sin(roll) + Y * Math.cos(roll)]
        ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + X * L, cy - Y * L); ctx.stroke()
      }
      axis(1, 0, 0, 'rgba(224,107,94,0.9)'); axis(0, 1, 0, 'rgba(99,181,127,0.9)'); axis(0, 0, 1, 'rgba(127,180,232,0.9)')
      // gaze arrow from between the eyes
      if (vals['gaze.horizontal'] != null) {
        const gx = -vals['gaze.horizontal'], gy = -vals['gaze.vertical'] // screen: subject's left is viewer's right
        const ex = cx, ey = oy + (y0 + 0.4 * (y1 - y0)) * dh
        ctx.strokeStyle = '#d7dee7'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(ex + gx * L * 1.2, ey + gy * L * 1.2); ctx.stroke()
        ctx.fillStyle = '#d7dee7'; ctx.beginPath(); ctx.arc(ex + gx * L * 1.2, ey + gy * L * 1.2, 3, 0, Math.PI * 2); ctx.fill()
      }
    }
    // active AUs (right side of frame) with names and bars, amber when deviating from baseline
    const aus = Object.entries(vals).filter(([k, val]) => k.startsWith('au.AU') && !/AU[LR]/.test(k) && val >= 0.3).sort((a, b) => b[1] - a[1]).slice(0, 8)
    const px = rect.width - 232, py0 = 44
    ctx.fillStyle = 'rgba(5,7,10,0.65)'; ctx.fillRect(px - 8, py0 - 14, 232, 16 + Math.max(1, aus.length) * 18 + 8)
    ctx.fillStyle = '#7c8794'; ctx.fillText('ACTION UNITS (occurrence probability)', px, py0 - 4)
    aus.forEach(([k, val], i) => {
      const y = py0 + 12 + i * 18
      const b = laneBase[k]
      const z = b && b.scale > 0 ? (val - b.center) / b.scale : null
      const hot = z != null && z >= 4
      ctx.fillStyle = hot ? '#d4a24c' : '#d7dee7'
      ctx.fillText(`${k.slice(3)} ${auName(k)}`.slice(0, 26), px, y)
      ctx.fillStyle = '#1f2933'; ctx.fillRect(px + 150, y - 4, 60, 8)
      ctx.fillStyle = hot ? '#d4a24c' : '#7fb4e8'; ctx.fillRect(px + 150, y - 4, 60 * val, 8)
      ctx.fillStyle = '#7c8794'; ctx.fillText(z != null ? `${z >= 0 ? '+' : ''}${z.toFixed(0)}` : '', px + 214, y)
    })
    if (!aus.length) { ctx.fillStyle = '#4b5663'; ctx.fillText('no AU above 0.30', px, py0 + 12) }
    // pattern meter (left side)
    const pats = patternScores(vals).filter((p) => p.score >= 0.25).slice(0, 3)
    if (pats.length) {
      const lx = 12, ly0 = rect.height - 36 - pats.length * 18
      ctx.fillStyle = 'rgba(5,7,10,0.65)'; ctx.fillRect(lx - 6, ly0 - 16, 230, pats.length * 18 + 26)
      ctx.fillStyle = '#7c8794'; ctx.fillText('PATTERN (FACS appearance)', lx, ly0 - 6)
      pats.forEach((p, i) => {
        const y = ly0 + 10 + i * 18
        const on = p.score >= PATTERN_ENTER
        ctx.fillStyle = on ? '#b48ce6' : '#7c8794'; ctx.fillText(p.name, lx, y)
        ctx.fillStyle = '#1f2933'; ctx.fillRect(lx + 110, y - 4, 80, 8)
        ctx.fillStyle = on ? '#b48ce6' : '#4b5663'; ctx.fillRect(lx + 110, y - 4, 80 * p.score, 8)
        ctx.fillStyle = '#7c8794'; ctx.fillText(p.score.toFixed(2), lx + 196, y)
      })
    }
    // blink + speech indicators (top center)
    const now = performance.now()
    const blink = now - lastBlinkAt < 300
    ctx.fillStyle = blink ? '#7fb4e8' : 'rgba(127,180,232,0.25)'; ctx.beginPath(); ctx.arc(rect.width / 2 - 40, 16, 5, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = '#7c8794'; ctx.fillText('blink', rect.width / 2 - 30, 16)
    const sp = audioLast?.speech_prob ?? 0
    ctx.fillStyle = sp >= 0.5 ? '#5fb8ae' : 'rgba(95,184,174,0.25)'; ctx.beginPath(); ctx.arc(rect.width / 2 + 30, 16, 5, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = '#7c8794'; ctx.fillText(audioLast?.f0_hz ? `speech ${audioLast.f0_hz.toFixed(0)} Hz` : 'speech', rect.width / 2 + 40, 16)
    // event flashes near the face box top
    flashes = flashes.filter((f) => f.until > now)
    flashes.forEach((f, i) => {
      const alpha = Math.min(1, (f.until - now) / 800)
      ctx.globalAlpha = alpha
      const fx = m.bbox ? ox + m.bbox[0] * dw : 12, fy = (m.bbox ? oy + m.bbox[1] * dh : 60) - 12 - i * 18
      ctx.fillStyle = 'rgba(5,7,10,0.75)'; ctx.fillRect(fx - 4, fy - 9, ctx.measureText(f.text).width + 8, 16)
      ctx.fillStyle = f.color; ctx.fillText(f.text, fx, fy)
      ctx.globalAlpha = 1
    })
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
    const labelW = 215
    const x = (t: number) => labelW + ((t - (now - WINDOW_US)) / WINDOW_US) * (W - labelW - 8)
    LANES.forEach((name, i) => {
      const y0 = 2 + i * 34, h = 30
      ctx.strokeStyle = '#1f2933'; ctx.beginPath(); ctx.moveTo(labelW, y0 + h); ctx.lineTo(W, y0 + h); ctx.stroke()
      ctx.fillStyle = '#d7dee7'; ctx.fillText(name, 6, y0 + 10)
      const hh = hist[name]
      const cur = hh.v.length ? hh.v[hh.v.length - 1] : null
      ctx.fillStyle = '#7c8794'; ctx.fillText(cur == null ? '-' : Math.abs(cur) >= 100 ? cur.toFixed(0) : cur.toFixed(2), 6, y0 + 23)
      ctx.fillStyle = '#4b5663'; ctx.fillText(laneBase[name] ? 'SD lanes: baseline center = mid line' : 'raw (baseline pending)', 100, y0 + 10)
      if (hh.v.length < 2) return
      const b = laneBase[name]
      ctx.strokeStyle = name.startsWith('voice.') ? '#5fb8ae' : name.startsWith('au.') || name.startsWith('blendshape.') || name.startsWith('asym.') ? '#d4a24c' : '#7fb4e8'
      ctx.lineWidth = 1; ctx.beginPath()
      if (b && b.scale > 0) {
        // SD units: mid line = baseline center, +-6 SD span, dashed guides at +-3
        const Z = 6, ymid = y0 + h / 2, sy = (h - 6) / (2 * Z)
        ctx.save(); ctx.strokeStyle = '#4b5663'; ctx.setLineDash([2, 4])
        for (const z of [3, -3]) { ctx.beginPath(); ctx.moveTo(labelW, ymid - z * sy); ctx.lineTo(W - 8, ymid - z * sy); ctx.stroke() }
        ctx.setLineDash([]); ctx.strokeStyle = '#2b3846'; ctx.beginPath(); ctx.moveTo(labelW, ymid); ctx.lineTo(W - 8, ymid); ctx.stroke(); ctx.restore()
        ctx.beginPath()
        for (let k = 0; k < hh.v.length; k++) {
          const z = Math.max(-Z, Math.min(Z, (hh.v[k] - b.center) / b.scale))
          const px = x(hh.t[k]), py = ymid - z * sy
          if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
        }
        ctx.stroke()
        const zc = cur == null ? null : (cur - b.center) / b.scale
        ctx.fillStyle = zc != null && Math.abs(zc) >= 3 ? '#d4a24c' : '#7c8794'
        ctx.fillText(zc == null ? '' : `${zc >= 0 ? '+' : ''}${zc.toFixed(1)} SD`, labelW - 62, y0 + 23)
      } else {
        let lo = Infinity, hi = -Infinity
        for (const v of hh.v) { if (v < lo) lo = v; if (v > hi) hi = v }
        if (hi - lo < 1e-6) { lo -= 0.5; hi += 0.5 }
        for (let k = 0; k < hh.v.length; k++) {
          const px = x(hh.t[k]), py = y0 + 3 + (1 - (hh.v[k] - lo) / (hi - lo)) * (h - 6)
          if (k === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py)
        }
        ctx.stroke()
      }
    })
    for (const e of events) {
      if (e.end_us < now - WINDOW_US) continue
      ctx.fillStyle = e.source === 'audio' ? 'rgba(95,184,174,0.18)' : 'rgba(212,162,76,0.18)'
      ctx.fillRect(x(e.start_us), 0, Math.max(2, x(e.end_us) - x(e.start_us)), H)
    }
  }

  async function start() {
    if (!videoEl) return
    events = []; sessionId = null; audioLast = null; last = null; baselineInfo = null; calib = null; lastPhaseSpeaking = null; qIndex = -1; asked = []; tally = {}; pulseHold = null
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
    <button onclick={() => (showProtocol = !showProtocol)}>{showProtocol ? 'hide protocol' : 'protocol'}</button>
    <label><input type="checkbox" bind:checked={showOverlay} /> overlays</label>
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
          {#if readoutGaze}<div>{readoutGaze}{last?.values['head.speed_deg_s'] != null ? `, head ${last.values['head.speed_deg_s'].toFixed(0)} deg/s` : ''}</div>{/if}
          {#if audioLast}<div>speech {audioLast.speech_prob.toFixed(2)} f0 {audioLast.f0_hz ? audioLast.f0_hz.toFixed(0) + ' Hz' : '-'} {audioLast.energy_db.toFixed(0)} dB</div>{/if}
          {#if pulseHold}<div class="pulse" class:dim={!pulseHold.usable}>pulse ~{pulseHold.bpm.toFixed(0)} bpm <span class="muted">camera estimate, {pulseHold.usable ? 'snr ' + pulseHold.snr_db.toFixed(0) + ' dB' : 'not usable: hold still, face the light'}</span></div>{/if}
          <div class="muted">{last.stats.analyzed_fps.toFixed(1)} fps, latency {last.stats.latency_ms_p50?.toFixed(0) ?? '-'} ms, dropped {last.stats.frames_dropped}</div>
        </div>
      {/if}
    </div>
    <div class="side">
      {#if showProtocol}
        <div class="proto">
          <div class="eyebrow">interview protocol</div>
          {#if state !== 'running'}
            <textarea bind:value={script} rows="7" spellcheck="false"></textarea>
            <div class="muted tiny">one question per line. C: control, R: relevant, N: neutral. add [truth] or [lie] at the end if you know the expected answer class.</div>
          {:else}
            {#if currentQ}
              <div class="qcur">
                <span class="eyebrow">{currentQ.q.category} {currentQ.q.id}</span>
                <p>{currentQ.q.text}</p>
                <div class="mono tiny">asked {tc(currentQ.t_us).slice(3)} {currentQ.latency_ms != null ? `. answer after ${currentQ.latency_ms.toFixed(0)} ms` : ''} . {currentQ.devs} deviations so far</div>
              </div>
            {:else}
              <div class="muted">press ask (or n) when you read the first question aloud</div>
            {/if}
            <div class="proto-btns">
              <button class="primary" onclick={askNext} disabled={!last || !last.baseline_ready || qIndex + 1 >= questions.length}>ask next ({Math.max(0, questions.length - qIndex - 1)} left)</button>
              <button onclick={endAnswer} disabled={!currentQ}>end answer</button>
            </div>
            <div class="note-row"><input placeholder="note at current time" bind:value={noteText} onkeydown={(e) => e.key === 'Enter' && addNote()} /><button onclick={addNote}>add</button></div>
            {#if asked.length}
              <ol class="asked">
                {#each asked as a (a.q.id)}<li class:rel={a.q.category === 'relevant'}><span class="mono">{tc(a.t_us).slice(3)}</span> {a.q.text.slice(0, 40)}{a.q.text.length > 40 ? '...' : ''} <span class="mono muted">{a.devs}</span></li>{/each}
              </ol>
            {/if}
          {/if}
        </div>
      {/if}
      <div class="tally">
        {#each TALLY as [k, label] (k)}<span class:zero={!tally[k]}><b class="mono">{tally[k] ?? 0}</b> {label}</span>{/each}
      </div>
      <div class="side-hdr"><span class="eyebrow">{showAll ? 'all events' : 'episodes, patterns, gestures, voice'}</span><button onclick={() => (showAll = !showAll)}>{showAll ? 'episodes' : 'all'}</button></div>
      <ul>
        {#each shown as e (e.event_id)}
          <li class:audio={e.source === 'audio'} class:episode={e.event_type === 'episode'} class:expr={e.event_type === 'expression_pattern'}><span class="mono">{tc(e.start_us).slice(3)}</span> <span class="lbl">{e.label}{#if e.tags.includes('speaking')} <em class="tag">speaking</em>{/if}</span> <span class="mono sev">{sev(e.severity)}</span></li>
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
  li.expr { border-left: 2px solid var(--violet); padding-left: 6px; }
  li.expr .sev { color: var(--violet); }
  .tag { font-style: normal; color: var(--muted); font-size: 10.5px; border: 1px solid var(--line-strong); padding: 0 4px; border-radius: 2px; }
  .side-hdr { display: flex; justify-content: space-between; align-items: center; }
  .side-hdr button { padding: 1px 8px; font-size: 11px; }
  li.audio .sev { color: var(--teal); }
  .proto { border-bottom: 1px solid var(--line); padding-bottom: 10px; margin-bottom: 8px; }
  .proto textarea { width: 100%; background: var(--panel-2); color: var(--text); border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 6px; font: 12px/1.4 var(--font-ui); resize: vertical; }
  .tiny { font-size: 10.5px; }
  .qcur { border-left: 2px solid var(--accent); padding: 4px 8px; margin: 6px 0; }
  .qcur p { margin: 2px 0 4px; font-size: 14px; }
  .proto-btns { display: flex; gap: 6px; margin: 6px 0; }
  .note-row { display: flex; gap: 6px; }
  .note-row input { flex: 1; background: var(--panel-2); border: 1px solid var(--line-strong); border-radius: var(--radius); padding: 3px 6px; font-size: 12px; }
  .asked { margin: 8px 0 0; padding-left: 18px; font-size: 11.5px; }
  .asked li { padding: 2px 0; }
  .asked li.rel { color: var(--accent); }
  .lanes { width: 100%; display: block; border-top: 1px solid var(--line); background: var(--panel); }
  .readout .pulse { color: var(--pulse); }
  .readout .pulse.dim { color: var(--muted); }
  .tally { display: flex; flex-wrap: wrap; gap: 4px 12px; font-size: 11px; color: var(--muted); margin-bottom: 8px; }
  .tally b { color: var(--text); font-weight: 500; }
  .tally .zero { opacity: 0.55; }
</style>
