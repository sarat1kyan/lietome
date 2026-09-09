// Plain-language framing per event type: what was measured, what it does not mean, what to check.
import type { LmEvent } from './types'

export interface Explanation { measured: string; not: string; check: string }

export function explain(e: LmEvent): Explanation {
  switch (e.event_type) {
    case 'episode':
    case 'multi_signal_deviation':
      return {
        measured: 'Several signals left this person\'s baseline range at the same time. The contributors below are ranked by how far each moved, in robust standard deviations of their own calibration.',
        not: 'Not an emotion and not a lie. Animated speech, a laugh, a posture change or a glance at notes produce the same picture.',
        check: 'Scrub to the moment. Was the person talking, moving or reacting to something in the room? Compare with the same signals during a control question.',
      }
    case 'baseline_deviation':
      return {
        measured: 'One signal moved well outside its usual range for this person, for longer than a flicker.',
        not: 'A single signal says little on its own. Classifier outputs jitter; head and gaze move for ordinary reasons.',
        check: 'Look for an episode (several signals together) at the same time, or a repeating pattern across questions.',
      }
    case 'expression_pattern':
      return {
        measured: 'The Action Units matched a FACS prototype for a while. The label names the appearance and the AU list says which muscles moved.',
        not: 'Not what the person felt. Posed prototypes rarely match spontaneous faces; smiles occur in politeness and embarrassment, brow lowering in concentration and bright light.',
        check: e.tags.includes('brief')
          ? 'Brief (under 500 ms): a candidate for what the microexpression literature studies. At 13-15 fps this cannot be confirmed; treat it as a place to look, not a finding.'
          : 'Long patterns during speech are usually conversational. Check whether it recurs at the same kind of question.',
      }
    case 'head_gesture':
      return {
        measured: 'A rhythmic head movement: up and down (nod) or side to side (shake), with the swing size and cycle count in the label.',
        not: 'Not agreement or denial by itself. People nod while listening, keep rhythm while talking and shake off hair.',
        check: 'Compare the gesture with what was being said. A nod during a spoken "no" is only interesting if it repeats.',
      }
    case 'au_novelty':
      return {
        measured: 'Two or more Action Units were active together for the first time since calibration. Each pairing is reported once.',
        not: 'Not a sign of anything specific. A 40 s calibration cannot show every face a person makes; early in a session these arrive often and then stop.',
        check: 'Pairings that appear late in the session, or only at one kind of question, are worth a second look. Early ones are usually the face warming up.',
      }
    case 'pulse_change':
      return {
        measured: 'The camera pulse estimate (skin color flicker over forehead and cheeks) stayed away from its reference for several seconds. Only windows above the SNR gate count.',
        not: 'Not a medical reading and not arousal. Talking, laughing, leaning and lighting change the estimate as much as anything internal.',
        check: 'Was the person still and evenly lit through the window? If the pulse lane is faded around it, the estimate was not trusted.',
      }
    case 'blink_rate_change':
      return {
        measured: 'Blinks per minute over 30 s windows moved far from the reference rate measured right after calibration.',
        not: 'Blink rate follows attention, screen use, dryness and speech. Both suppression and rebound are documented; neither identifies a cause.',
        check: 'Look at what the person was doing: reading, listening, talking or thinking all change blink rate.',
      }
    case 'eye_closure':
      return {
        measured: 'The eyes stayed closed longer than a blink.',
        not: 'Not avoidance by itself: thinking, fatigue and bright light do the same.',
        check: 'Note the duration and whether it repeats at specific questions.',
      }
    case 'blink':
      return { measured: 'A blink.', not: 'Individual blinks carry no meaning here.', check: 'See blink rate changes instead.' }
    default:
      if (e.source === 'audio')
        return {
          measured: 'A voice measure (pitch, loudness or pause structure) left this speaker\'s own baseline.',
          not: 'Pitch rises with emphasis, questions and laughter. Loudness follows distance to the microphone.',
          check: 'Compare with the same speaker on control questions; check that the audio SNR was good.',
        }
      return {
        measured: 'A measured change relative to this person\'s own calibration.',
        not: 'Not a psychological state and not a verdict.',
        check: 'Look at the moment in the video and at what else happened at the same time.',
      }
  }
}
