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

export const SCRIPT_TEMPLATES: { name: string; text: string }[] = [
  { name: 'default mix', text: DEFAULT_SCRIPT },
  { name: 'baseline truths first', text: `C: What is your full name?
C: What city do you live in?
C: What day of the week is it today?
R: Did you take anything from the shared kitchen this week that was not yours?
R: Have you ever read a message on someone else's phone without permission?
C: Did you have coffee this morning?
R: Have you lied to a friend this month to avoid meeting them?
N: Describe your commute.` },
  { name: 'mock theft game', text: `N: Tell me about your morning so far.
C: Is today ${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][new Date().getDay()]}?
R: Did you take the item from the desk?
C: Are you sitting down right now?
R: Do you know where the item is now?
R: Did anyone help you?
C: Have you eaten today?
N: What will you do after this?` },
]

// Shuffle questions while keeping the first line first (a warm-up) and alternating categories where possible.
export function shuffleScript(text: string): string {
  const lines = text.split('\n').filter((l) => l.trim())
  if (lines.length < 3) return text
  const [head, ...rest] = lines
  for (let i = rest.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [rest[i], rest[j]] = [rest[j], rest[i]] }
  return [head, ...rest].join('\n')
}
