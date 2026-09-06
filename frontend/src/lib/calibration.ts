// Guided calibration: fixed phases so every baseline has the same structure. See docs/calibration.md.
export interface Phase { name: string; seconds: number; speaking: boolean; instruction: string }

export const PASSAGE =
  'The morning train leaves at seven and stops twice before the coast. A blue kettle sits on the stove, and the window faces a quiet street with three maple trees. Count the steps from the door to the gate, then name the months from January to June. The weather this week has been mild.'

export const PHASES: Phase[] = [
  { name: 'settle', seconds: 12, speaking: false, instruction: 'Sit as you normally would. Look at the screen. Do not talk. Blink normally.' },
  { name: 'read', seconds: 14, speaking: true, instruction: 'Read the passage aloud at your normal pace and volume.' },
  { name: 'talk', seconds: 14, speaking: true, instruction: 'Now talk freely: describe what you did earlier today, in your own words, until the timer ends.' },
]

export const CALIBRATION_SECONDS = PHASES.reduce((a, p) => a + p.seconds, 0)

export function phaseAt(elapsedS: number): { phase: Phase; index: number; remaining: number } | null {
  let t = 0
  for (let i = 0; i < PHASES.length; i++) {
    const p = PHASES[i]
    if (elapsedS < t + p.seconds) return { phase: p, index: i, remaining: t + p.seconds - elapsedS }
    t += p.seconds
  }
  return null
}
