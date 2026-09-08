// FACS names for on-screen labels (OpenGraphAU ordering; unilateral variants share the base name).
export const AU_NAMES: Record<string, string> = {
  AU1: 'inner brow raiser', AU2: 'outer brow raiser', AU4: 'brow lowerer', AU5: 'upper lid raiser',
  AU6: 'cheek raiser', AU7: 'lid tightener', AU9: 'nose wrinkler', AU10: 'upper lip raiser',
  AU11: 'nasolabial deepener', AU12: 'lip corner puller', AU13: 'sharp lip puller', AU14: 'dimpler',
  AU15: 'lip corner depressor', AU16: 'lower lip depressor', AU17: 'chin raiser', AU18: 'lip pucker',
  AU19: 'tongue show', AU20: 'lip stretcher', AU22: 'lip funneler', AU23: 'lip tightener',
  AU24: 'lip pressor', AU25: 'lips part', AU26: 'jaw drop', AU27: 'mouth stretch', AU32: 'lip bite',
  AU38: 'nostril dilator', AU39: 'nostril compressor',
}
export function auName(key: string): string {
  const k = key.replace(/^au\./, '')
  const base = k.replace(/^AU[LR]/, 'AU')
  const side = k.startsWith('AUL') ? 'left ' : k.startsWith('AUR') ? 'right ' : ''
  return side + (AU_NAMES[base] ?? k)
}

// Prototype patterns mirrored from the server for the live pattern meter.
export const PROTOTYPES: { name: string; required: string[]; absent?: string[]; unilateral?: [string, string][] }[] = [
  { name: 'happiness', required: ['AU6', 'AU12'] },
  { name: 'social smile', required: ['AU12'], absent: ['AU6'] },
  { name: 'brow flash', required: ['AU1', 'AU2'], absent: ['AU5', 'AU26'] },
  { name: 'surprise', required: ['AU1', 'AU2', 'AU5', 'AU26'] },
  { name: 'fear', required: ['AU1', 'AU2', 'AU4', 'AU5', 'AU7', 'AU20', 'AU26'] },
  { name: 'anger', required: ['AU4', 'AU5', 'AU7', 'AU23'] },
  { name: 'sadness', required: ['AU1', 'AU4', 'AU15'] },
  { name: 'disgust', required: ['AU9', 'AU15'] },
  { name: 'contempt', required: [], unilateral: [['AUL12', 'AUR12'], ['AUL14', 'AUR14']] },
  { name: 'lip press', required: ['AU24'], absent: ['AU12'] },
  { name: 'brow furrow', required: ['AU4'], absent: ['AU1', 'AU2', 'AU12'] },
]
export const PATTERN_ENTER = 0.55
export function patternScores(values: Record<string, number>): { name: string; score: number }[] {
  const g = (k: string) => values['au.' + k]
  const out: { name: string; score: number }[] = []
  for (const p of PROTOTYPES) {
    let score: number
    if (p.required.length) {
      const vals = p.required.map(g)
      if (vals.some((v) => v == null)) continue
      const mean = vals.reduce((a, b) => a + b, 0) / vals.length
      score = 0.5 * mean + 0.5 * Math.min(...vals)
      if (p.absent) { const av = p.absent.map(g); if (av.some((v) => v == null)) continue; if (Math.max(...av) >= 0.35) score = 0 }
    } else {
      const diffs = (p.unilateral ?? []).map(([l, r]) => (g(l) != null && g(r) != null ? Math.abs(g(l) - g(r)) : NaN)).filter((d) => !isNaN(d))
      if (!diffs.length) continue
      score = (Math.max(...diffs) / 0.35) * PATTERN_ENTER
    }
    out.push({ name: p.name, score: Math.max(0, Math.min(1, score)) })
  }
  return out.sort((a, b) => b.score - a.score)
}
