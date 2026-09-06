# Calibration protocol

The baseline is only as good as the calibration window. Lightman scores every later frame
against it, and since ADR-013 it keeps separate baselines for the silent and speaking
states. The window therefore has to contain both, in known proportions, under the same
camera, light and framing as the rest of the session.

## Guided live calibration (default, 40 s)

| Phase | Duration | Instruction | State |
|---|---|---|---|
| settle | 12 s | Sit as you normally would. Look at the screen. Do not talk. Blink normally. | silent |
| read | 14 s | Read the passage below aloud at your normal pace and volume. | speaking |
| talk | 14 s | Talk freely: describe what you did earlier today, in your own words. | speaking |

The live tab shows the instruction, a countdown and the passage; the speaking state comes
from the voice activity detector when the microphone is on, and from the phase otherwise.

## The passage

Original text, neutral content, varied consonants and vowels, no emotional words, about 55
words (14 s at a brisk pace, 18 s at a slow one):

> The morning train leaves at seven and stops twice before the coast. A blue kettle sits
> on the stove, and the window faces a quiet street with three maple trees. Count the steps
> from the door to the gate, then name the months from January to June. The weather this
> week has been mild.

Why a free-talk phase too: the third real session showed that reading is not conversation
(jaw barely moves, pitch is flat), so a reading-only speaking baseline made ordinary talking
look deviant. Reading gives a controlled sample; free talk gives the conversational range.

Why a fixed passage: the speaking-state baseline then measures *how this person articulates
neutral text*, so later differences are not explained by different words. Why neutral: an
emotional or personal passage would bake that reaction into the baseline.

## Prerecorded interviews

Record the same two phases at the start (quiet, then the passage) before the interview
proper. If that is impossible, the pipeline still builds a speaking baseline from whatever
speech falls in the first 30 s, or falls back to tagging mouth-region events "speaking".

## What calibration cannot fix

A baseline describes this person, this camera, this room, this moment. It says nothing about
what is normal for people in general, and a change relative to it has many possible causes.
See scientific-limitations.md.
