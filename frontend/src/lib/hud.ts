// On-video heads-up display for the live view. Pure canvas drawing; no state of its own.
import { auName, patternScores, PATTERN_ENTER } from './facs'

// MediaPipe Face Mesh contour index chains.
const FACE_OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109, 10]
const LIPS_OUT = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270, 269, 267, 0, 37, 39, 40, 185, 61]
const LIPS_IN = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310, 311, 312, 13, 82, 81, 80, 191, 78]
const EYE_L = [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386, 387, 388, 466, 263]
const EYE_R = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246, 33]
const BROW_L1 = [276, 283, 282, 295, 285], BROW_L2 = [300, 293, 334, 296, 336]
const BROW_R1 = [46, 53, 52, 65, 55], BROW_R2 = [70, 63, 105, 66, 107]
const IRIS_L = [474, 475, 476, 477, 474], IRIS_R = [469, 470, 471, 472, 469]
const NOSE = [168, 6, 197, 195, 5, 4]

export const C = {
  text: '#d7dee7', muted: '#7c8794', faint: '#4b5663', line: '#1f2933',
  accent: '#d4a24c', cool: '#7fb4e8', teal: '#5fb8ae', violet: '#b48ce6', pulse: '#e0907a', warn: '#e06b5e', ok: '#63b57f',
  ink: 'rgba(5,7,10,0.68)',
}

export interface Flash { text: string; until: number; color: string }
export interface HudInput {
  ctx: CanvasRenderingContext2D
  w: number; h: number                 // canvas css size
  map: { ox: number; oy: number; dw: number; dh: number } // video -> canvas mapping (object-fit: contain)
  landmarks: number[] | null
  bbox: [number, number, number, number] | null
  values: Record<string, number>
  base: Record<string, { center: number; scale: number }>
  baselineReady: boolean
  tUs: number
  stats: { analyzed_fps: number; latency_ms_p50: number | null; frames_dropped: number }
  audio: { speech_prob: number; f0_hz: number | null; energy_db: number; rate_syl_s?: number | null } | null
  pulse: { bpm: number; snr_db: number; usable: boolean } | null
  pulseWave: number[] | null
  gazeAwaySinceUs: number | null
  blinkAgoMs: number
  flashes: Flash[]
  now: number
  tape: { name: string; label: string; color: string; t: number[]; v: number[] }[]
  windowUs: number
  question: { id: string; text: string; category: string; sinceUs: number; devs: number; latencyMs: number | null } | null
  phase: string | null
  ticker: string | null
  lastIndex: { id: string; value: number | null; band: string } | null
  full: boolean
}

const mono = (px: number) => `${px}px "JetBrains Mono", "SFMono-Regular", Menlo, monospace`
const sans = (px: number, w = 500) => `${w} ${px}px "Instrument Sans", "Helvetica Neue", Arial, sans-serif`

function tc(us: number): string {
  const s = Math.max(0, Math.floor(us / 1e6))
  const mm = Math.floor(s / 60), ss = s % 60, ms = Math.floor((us % 1e6) / 1e5)
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}.${ms}`
}

function chain(ctx: CanvasRenderingContext2D, lm: number[], idx: number[], m: HudInput['map']) {
  ctx.beginPath()
  idx.forEach((i, k) => {
    const x = m.ox + lm[i * 2] * m.dw, y = m.oy + lm[i * 2 + 1] * m.dh
    if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
  })
  ctx.stroke()
}

function panel(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number) {
  ctx.fillStyle = C.ink; ctx.fillRect(x, y, w, h)
  ctx.strokeStyle = 'rgba(215,222,231,0.08)'; ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1)
}

export function drawHud(inp: HudInput) {
  const { ctx, w, h, map, values: v, base } = inp
  ctx.textBaseline = 'middle'; ctx.textAlign = 'left'; ctx.lineWidth = 1

  // ---- face mesh contours
  if (inp.landmarks && inp.landmarks.length >= 956) {
    const lm = inp.landmarks
    ctx.strokeStyle = 'rgba(127,180,232,0.35)'; ctx.lineWidth = 1
    chain(ctx, lm, FACE_OVAL, map)
    ctx.strokeStyle = 'rgba(127,180,232,0.55)'
    chain(ctx, lm, EYE_L, map); chain(ctx, lm, EYE_R, map)
    chain(ctx, lm, BROW_L1, map); chain(ctx, lm, BROW_L2, map); chain(ctx, lm, BROW_R1, map); chain(ctx, lm, BROW_R2, map)
    ctx.strokeStyle = 'rgba(212,162,76,0.55)'
    chain(ctx, lm, LIPS_OUT, map); chain(ctx, lm, LIPS_IN, map)
    ctx.strokeStyle = 'rgba(215,222,231,0.35)'; chain(ctx, lm, NOSE, map)
    if (lm.length >= 956) { ctx.strokeStyle = 'rgba(215,222,231,0.8)'; chain(ctx, lm, IRIS_L, map); chain(ctx, lm, IRIS_R, map) }
    ctx.fillStyle = 'rgba(127,180,232,0.22)'
    for (let i = 0; i < lm.length; i += 6) ctx.fillRect(map.ox + lm[i] * map.dw - 0.5, map.oy + lm[i + 1] * map.dh - 0.5, 1, 1)
  }

  // ---- face box: corner brackets
  if (inp.bbox) {
    const [x0, y0, x1, y1] = inp.bbox
    const bx = map.ox + x0 * map.dw, by = map.oy + y0 * map.dh, bw = (x1 - x0) * map.dw, bh = (y1 - y0) * map.dh
    const L = Math.max(10, Math.min(bw, bh) * 0.14)
    ctx.strokeStyle = inp.baselineReady ? C.accent : C.cool; ctx.lineWidth = 1.5
    const corners: [number, number, number, number][] = [[bx, by, 1, 1], [bx + bw, by, -1, 1], [bx, by + bh, 1, -1], [bx + bw, by + bh, -1, -1]]
    for (const [cx, cy, sx, sy] of corners) { ctx.beginPath(); ctx.moveTo(cx, cy + sy * L); ctx.lineTo(cx, cy); ctx.lineTo(cx + sx * L, cy); ctx.stroke() }
    ctx.font = mono(10); ctx.fillStyle = inp.baselineReady ? C.accent : C.cool
    ctx.fillText(inp.baselineReady ? 'TRACKING vs BASELINE' : 'TRACKING, CALIBRATING', bx, by - 9)
    ctx.textAlign = 'right'; ctx.fillStyle = C.muted; ctx.fillText(`q ${(v['quality'] ?? 0).toFixed(2)}`, bx + bw, by + bh + 10); ctx.textAlign = 'left'
  }

  if (!inp.full) return
  const cx = inp.bbox ? map.ox + ((inp.bbox[0] + inp.bbox[2]) / 2) * map.dw : w / 2
  const faceW = inp.bbox ? (inp.bbox[2] - inp.bbox[0]) * map.dw : 200

  // ---- head axes + gaze reticle
  if (inp.bbox && v['head.yaw_deg'] != null) {
    const [x0, y0, x1, y1] = inp.bbox
    const cy = map.oy + ((y0 + y1) / 2) * map.dh, L = 0.22 * faceW
    const yaw = (v['head.yaw_deg'] * Math.PI) / 180, pitch = (v['head.pitch_deg'] * Math.PI) / 180, roll = (v['head.roll_deg'] * Math.PI) / 180
    const axis = (x: number, y: number, z: number, color: string, label: string) => {
      let [X, Y, Z] = [x, y, z]
      ;[Y, Z] = [Y * Math.cos(pitch) - Z * Math.sin(pitch), Y * Math.sin(pitch) + Z * Math.cos(pitch)]
      ;[X, Z] = [X * Math.cos(yaw) + Z * Math.sin(yaw), -X * Math.sin(yaw) + Z * Math.cos(yaw)]
      ;[X, Y] = [X * Math.cos(roll) - Y * Math.sin(roll), X * Math.sin(roll) + Y * Math.cos(roll)]
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + X * L, cy - Y * L); ctx.stroke()
      ctx.fillStyle = color; ctx.font = mono(9); ctx.fillText(label, cx + X * L + 3, cy - Y * L)
    }
    axis(1, 0, 0, 'rgba(224,107,94,0.9)', 'x'); axis(0, 1, 0, 'rgba(99,181,127,0.9)', 'y'); axis(0, 0, 1, 'rgba(127,180,232,0.9)', 'z')
    if (v['gaze.horizontal'] != null) {
      const gx = -v['gaze.horizontal'], gy = -v['gaze.vertical']
      const ex = cx, ey = map.oy + (y0 + 0.38 * (y1 - y0)) * map.dh
      const tx = ex + gx * L * 1.4, ty = ey + gy * L * 1.4
      const away = inp.gazeAwaySinceUs != null
      ctx.strokeStyle = away ? C.accent : 'rgba(215,222,231,0.9)'; ctx.lineWidth = 1.5
      ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(tx, ty); ctx.stroke()
      ctx.beginPath(); ctx.arc(tx, ty, 7, 0, Math.PI * 2); ctx.stroke()
      ctx.beginPath(); ctx.moveTo(tx - 11, ty); ctx.lineTo(tx - 4, ty); ctx.moveTo(tx + 4, ty); ctx.lineTo(tx + 11, ty); ctx.moveTo(tx, ty - 11); ctx.lineTo(tx, ty - 4); ctx.moveTo(tx, ty + 4); ctx.lineTo(tx, ty + 11); ctx.stroke()
      if (away) { ctx.fillStyle = C.accent; ctx.font = mono(10); ctx.fillText(`gaze away ${((inp.tUs - inp.gazeAwaySinceUs!) / 1e6).toFixed(1)} s`, tx + 12, ty - 10) }
    }
  }

  // ---- top-left: status block
  {
    const x = 12, y = 12
    panel(ctx, x, y, 236, 74)
    const rec = Math.floor(inp.now / 600) % 2 === 0
    ctx.fillStyle = rec ? C.warn : 'rgba(224,107,94,0.35)'; ctx.beginPath(); ctx.arc(x + 14, y + 14, 4.5, 0, Math.PI * 2); ctx.fill()
    ctx.fillStyle = C.text; ctx.font = mono(15); ctx.fillText(tc(inp.tUs), x + 26, y + 14)
    ctx.fillStyle = C.muted; ctx.font = mono(10)
    ctx.fillText(`${inp.stats.analyzed_fps.toFixed(1)} fps  lat ${inp.stats.latency_ms_p50?.toFixed(0) ?? '-'} ms  drop ${inp.stats.frames_dropped}`, x + 12, y + 34)
    const phase = inp.phase ? `calibration: ${inp.phase}` : inp.baselineReady ? 'baseline armed, adapting within bounds' : 'computing baseline'
    ctx.fillStyle = inp.baselineReady ? C.ok : C.cool; ctx.fillText(phase.toUpperCase().slice(0, 36), x + 12, y + 50)
    ctx.fillStyle = C.faint; ctx.fillText('frames analyzed in memory, not stored', x + 12, y + 64)
  }

  // ---- top-center: question (protocol) or blink/speech chips
  {
    const q = inp.question
    if (q) {
      const txt = q.text.length > 78 ? q.text.slice(0, 76) + '...' : q.text
      ctx.font = sans(13)
      const tw = Math.min(w - 520, Math.max(260, ctx.measureText(txt).width + 24))
      const x = (w - tw) / 2, y = 12
      panel(ctx, x, y, tw, 52)
      ctx.fillStyle = q.category === 'relevant' ? C.accent : q.category === 'control' ? C.cool : C.muted
      ctx.font = mono(10); ctx.fillText(`${q.id}  ${q.category.toUpperCase()}  ${((inp.tUs - q.sinceUs) / 1e6).toFixed(0)} s`, x + 12, y + 14)
      ctx.textAlign = 'right'; ctx.fillStyle = C.muted; ctx.fillText(`${q.devs} dev${q.latencyMs != null ? `  answer +${q.latencyMs.toFixed(0)} ms` : ''}`, x + tw - 12, y + 14); ctx.textAlign = 'left'
      if (inp.lastIndex && inp.lastIndex.value != null) {
        const li = inp.lastIndex, lv = li.value!
        const gx = x, gy = y + 52, gw = tw
        panel(ctx, gx, gy, gw, 22)
        ctx.fillStyle = C.muted; ctx.font = mono(10); ctx.fillText(`last answer Q${li.id.replace(/^q/, '')}  cue index`, gx + 12, gy + 11)
        const col = lv < 40 ? C.cool : lv < 55 ? C.muted : lv < 70 ? C.accent : C.warn
        ctx.fillStyle = C.line; ctx.fillRect(gx + 150, gy + 8, gw - 230, 6)
        ctx.fillStyle = col; ctx.fillRect(gx + 150, gy + 8, (gw - 230) * (lv / 100), 6)
        ctx.textAlign = 'right'; ctx.fillStyle = col; ctx.fillText(`${lv.toFixed(0)} ${li.band}`, gx + gw - 12, gy + 11); ctx.textAlign = 'left'
      }
      ctx.fillStyle = C.text; ctx.font = sans(13); ctx.fillText(txt, x + 12, y + 36)
    } else {
      const bx = w / 2 - 70, by = 12
      panel(ctx, bx, by, 150, 24)
      const blink = inp.blinkAgoMs < 300
      ctx.fillStyle = blink ? C.cool : 'rgba(127,180,232,0.25)'; ctx.beginPath(); ctx.arc(bx + 14, by + 12, 4.5, 0, Math.PI * 2); ctx.fill()
      ctx.fillStyle = C.muted; ctx.font = mono(10); ctx.fillText('blink', bx + 24, by + 12)
      const sp = inp.audio?.speech_prob ?? 0
      ctx.fillStyle = sp >= 0.5 ? C.teal : 'rgba(95,184,174,0.25)'; ctx.beginPath(); ctx.arc(bx + 76, by + 12, 4.5, 0, Math.PI * 2); ctx.fill()
      ctx.fillStyle = C.muted; ctx.fillText(inp.audio ? 'speech' : 'no mic', bx + 86, by + 12)
    }
  }

  // ---- right: action units
  {
    const aus = Object.entries(v).filter(([k, val]) => k.startsWith('au.AU') && !/AU[LR]/.test(k) && val >= 0.25).sort((a, b) => b[1] - a[1]).slice(0, 9)
    const pw = 250, px = w - pw - 12, py = 12
    const ph = 30 + Math.max(1, aus.length) * 18
    panel(ctx, px, py, pw, ph)
    ctx.fillStyle = C.muted; ctx.font = mono(10); ctx.fillText('ACTION UNITS   p(occurrence)   vs baseline', px + 10, py + 13)
    ctx.font = mono(10.5)
    aus.forEach(([k, val], i) => {
      const y = py + 34 + i * 18
      const b = base[k]
      const z = b && b.scale > 0 ? (val - b.center) / b.scale : null
      const hot = z != null && z >= 4
      ctx.fillStyle = hot ? C.accent : C.text
      ctx.fillText(k.slice(3).padEnd(5), px + 10, y)
      ctx.fillStyle = hot ? C.accent : C.muted; ctx.fillText(auName(k).slice(0, 17), px + 48, y)
      ctx.fillStyle = C.line; ctx.fillRect(px + 160, y - 4, 54, 8)
      ctx.fillStyle = hot ? C.accent : C.cool; ctx.fillRect(px + 160, y - 4, 54 * Math.min(1, val), 8)
      ctx.textAlign = 'right'; ctx.fillStyle = hot ? C.accent : C.muted
      ctx.fillText(z != null ? `${z >= 0 ? '+' : ''}${z.toFixed(0)}` : '', px + pw - 10, y); ctx.textAlign = 'left'
    })
    if (!aus.length) { ctx.fillStyle = C.faint; ctx.fillText(inp.values['au.AU12'] == null ? 'AU model off (enable action units)' : 'no AU above 0.25', px + 10, py + 34) }
  }

  // ---- left: pattern meter
  {
    const pats = patternScores(v).filter((p) => p.score >= 0.2).slice(0, 4)
    const pw = 236, px = 12, py = 96
    const ph = 30 + Math.max(1, pats.length) * 18
    panel(ctx, px, py, pw, ph)
    ctx.fillStyle = C.muted; ctx.font = mono(10); ctx.fillText('FACS PATTERN   appearance, not feeling', px + 10, py + 13)
    ctx.font = mono(10.5)
    pats.forEach((p, i) => {
      const y = py + 34 + i * 18, on = p.score >= PATTERN_ENTER
      ctx.fillStyle = on ? C.violet : C.muted; ctx.fillText(p.name, px + 10, y)
      ctx.fillStyle = C.line; ctx.fillRect(px + 120, y - 4, 70, 8)
      ctx.fillStyle = on ? C.violet : C.faint; ctx.fillRect(px + 120, y - 4, 70 * p.score, 8)
      ctx.textAlign = 'right'; ctx.fillStyle = C.muted; ctx.fillText(p.score.toFixed(2), px + pw - 10, y); ctx.textAlign = 'left'
    })
    if (!pats.length) { ctx.fillStyle = C.faint; ctx.fillText('neutral', px + 10, py + 34) }
  }

  // ---- bottom-left: signal tape (mini sparklines, last window)
  {
    const tape = inp.tape.filter((t) => t.v.length > 1)
    const rows = Math.max(1, inp.tape.length)
    const pw = 236, ph = 16 + rows * 26, px = 12, py = h - ph - 12
    panel(ctx, px, py, pw, ph)
    ctx.font = mono(9.5)
    inp.tape.forEach((t, i) => {
      const y0 = py + 10 + i * 26, hh = 20
      ctx.fillStyle = C.muted; ctx.fillText(t.label, px + 10, y0 + 6)
      const b = base[t.name]
      const cur = t.v.length ? t.v[t.v.length - 1] : null
      const z = cur != null && b && b.scale > 0 ? (cur - b.center) / b.scale : null
      ctx.textAlign = 'right'; ctx.fillStyle = z != null && Math.abs(z) >= 3 ? C.accent : C.text
      ctx.fillText(cur == null ? '-' : z != null ? `${z >= 0 ? '+' : ''}${z.toFixed(1)} SD` : Math.abs(cur) >= 100 ? cur.toFixed(0) : cur.toFixed(2), px + pw - 10, y0 + 6); ctx.textAlign = 'left'
      if (t.v.length < 2) return
      const x0 = px + 78, x1 = px + pw - 58, t0 = inp.tUs - inp.windowUs
      ctx.strokeStyle = t.color; ctx.lineWidth = 1; ctx.beginPath()
      if (b && b.scale > 0) {
        const Z = 6, ymid = y0 + 6, sy = (hh - 4) / (2 * Z)
        ctx.save(); ctx.strokeStyle = 'rgba(75,86,99,0.6)'; ctx.setLineDash([2, 3]); ctx.beginPath(); ctx.moveTo(x0, ymid); ctx.lineTo(x1, ymid); ctx.stroke(); ctx.restore()
        ctx.beginPath()
        for (let k = 0; k < t.v.length; k++) {
          const zz = Math.max(-Z, Math.min(Z, (t.v[k] - b.center) / b.scale))
          const xx = x0 + ((t.t[k] - t0) / inp.windowUs) * (x1 - x0), yy = ymid - zz * sy
          if (k === 0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy)
        }
      } else {
        let lo = Infinity, hi = -Infinity
        for (const x of t.v) { if (x < lo) lo = x; if (x > hi) hi = x }
        if (hi - lo < 1e-6) { lo -= 0.5; hi += 0.5 }
        for (let k = 0; k < t.v.length; k++) {
          const xx = x0 + ((t.t[k] - t0) / inp.windowUs) * (x1 - x0), yy = y0 - 2 + (1 - (t.v[k] - lo) / (hi - lo)) * (hh - 4)
          if (k === 0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy)
        }
      }
      ctx.stroke()
    })
    void tape
  }

  // ---- bottom-right: pulse waveform + voice
  {
    const pw = 250, ph = 92, px = w - pw - 12, py = h - ph - 12
    panel(ctx, px, py, pw, ph)
    ctx.font = mono(10); ctx.fillStyle = C.muted; ctx.fillText('PULSE ESTIMATE  rPPG, camera', px + 10, py + 13)
    const p = inp.pulse
    ctx.font = mono(18); ctx.fillStyle = p ? (p.usable ? C.pulse : C.faint) : C.faint
    ctx.fillText(p ? `${p.bpm.toFixed(0)}` : '--', px + 10, py + 36)
    ctx.font = mono(10); ctx.fillStyle = C.muted
    ctx.fillText(p ? (p.usable ? `bpm   snr ${p.snr_db.toFixed(0)} dB` : 'bpm   not usable: hold still') : 'bpm   needs 10 s of a lit, still face', px + 52, py + 36)
    if (inp.pulseWave && inp.pulseWave.length > 2) {
      const wv = inp.pulseWave, x0 = px + 10, x1 = px + pw - 10, ymid = py + 58, amp = 10
      ctx.strokeStyle = p?.usable ? C.pulse : 'rgba(224,144,122,0.4)'; ctx.lineWidth = 1.3; ctx.beginPath()
      wv.forEach((s, k) => { const xx = x0 + (k / (wv.length - 1)) * (x1 - x0), yy = ymid - s * amp; if (k === 0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy) })
      ctx.stroke()
    } else { ctx.strokeStyle = 'rgba(224,144,122,0.25)'; ctx.beginPath(); ctx.moveTo(px + 10, py + 58); ctx.lineTo(px + pw - 10, py + 58); ctx.stroke() }
    // voice line
    const a = inp.audio
    ctx.fillStyle = C.muted; ctx.font = mono(10)
    if (a) {
      const lvl = Math.max(0, Math.min(1, (a.energy_db + 60) / 60))
      ctx.fillStyle = C.line; ctx.fillRect(px + 10, py + 76, 60, 6)
      ctx.fillStyle = a.speech_prob >= 0.5 ? C.teal : C.faint; ctx.fillRect(px + 10, py + 76, 60 * lvl, 6)
      ctx.fillStyle = a.speech_prob >= 0.5 ? C.teal : C.muted
      ctx.fillText(`${a.f0_hz ? a.f0_hz.toFixed(0) + ' Hz' : 'unvoiced'}  ${a.rate_syl_s != null ? a.rate_syl_s.toFixed(1) + ' syl/s' : ''}`, px + 78, py + 79)
    } else ctx.fillText('microphone off', px + 10, py + 79)
  }

  // ---- bottom-center ticker: last event
  if (inp.ticker) {
    ctx.font = sans(12)
    const tw = Math.min(w - 540, ctx.measureText(inp.ticker).width + 24)
    if (tw > 80) {
      const x = (w - tw) / 2, y = h - 12 - 26
      panel(ctx, x, y, tw, 26)
      ctx.fillStyle = C.text; ctx.fillText(inp.ticker.length > 90 ? inp.ticker.slice(0, 88) + '...' : inp.ticker, x + 12, y + 13)
    }
  }

  // ---- event flashes near the face box
  const live = inp.flashes.filter((f) => f.until > inp.now)
  ctx.font = mono(11)
  live.forEach((f, i) => {
    ctx.globalAlpha = Math.min(1, (f.until - inp.now) / 800)
    const fx = inp.bbox ? map.ox + inp.bbox[2] * map.dw + 10 : w / 2, fy = (inp.bbox ? map.oy + inp.bbox[1] * map.dh : 100) + 8 + i * 20
    ctx.fillStyle = 'rgba(5,7,10,0.8)'; ctx.fillRect(fx - 4, fy - 9, ctx.measureText(f.text).width + 8, 18)
    ctx.fillStyle = f.color; ctx.fillText(f.text, fx, fy)
    ctx.globalAlpha = 1
  })
}
