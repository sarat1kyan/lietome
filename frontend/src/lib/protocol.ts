export interface ScriptQuestion { id: string; text: string; category: 'control' | 'relevant' | 'neutral'; expected: 'truth' | 'lie' | null }

export const DEFAULT_SCRIPT = `N: What did you have for breakfast today?
C: Is your first name the one you were born with?
R: Have you ever taken something from a shop without paying?
C: Did you sleep at home last night?
R: Have you told a lie to someone in this room this week?
N: Describe the last film you watched.`

// One question per line. Prefix C:/R:/N: sets the category; suffix [truth] or [lie] records
// the answer class you expect, for the discrimination score.
export function parseScript(text: string): ScriptQuestion[] {
  const out: ScriptQuestion[] = []
  let n = 0
  for (const raw of text.split('\n')) {
    let line = raw.trim()
    if (!line) continue
    let category: ScriptQuestion['category'] = 'neutral'
    const head = line.slice(0, 2).toUpperCase()
    if (head === 'C:' || head === 'R:' || head === 'N:') { category = head === 'C:' ? 'control' : head === 'R:' ? 'relevant' : 'neutral'; line = line.slice(2).trim() }
    let expected: ScriptQuestion['expected'] = null
    const low = line.toLowerCase()
    for (const tag of ['[truth]', '[lie]'] as const) if (low.endsWith(tag)) { expected = tag.slice(1, -1) as 'truth' | 'lie'; line = line.slice(0, -tag.length).trim() }
    n += 1
    out.push({ id: `q${n}`, text: line, category, expected })
  }
  return out
}
