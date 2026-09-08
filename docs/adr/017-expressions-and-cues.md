# ADR-017 Expression patterns and the deception-research cue layer

**Context.** The project's inspiration dramatizes two things: reading emotions from brief
facial expressions, and spotting lies. The maintainer wants both to be visible. The evidence
supports much less than the drama: FACS prototype combinations are recognizable in posed
material but spontaneous faces rarely match them and the same combination arises in speech,
humor and effort (Barrett et al. 2019 review); deception cues in meta-analyses are weak
(DePaulo et al. 2003: most d < 0.3; Bond & DePaulo 2006: human accuracy about 54%).

**Decision.** Two INTERPRETATION-level layers, both worded as appearance and checklist:

1. *Expression patterns*: per-frame pattern scores from smoothed AU probabilities for the
   EMFACS prototypes (happiness 6+12, surprise 1+2+5+26, fear 1+2+4+5+7+20+26, anger
   4+5+7+23, sadness 1+4+15, disgust 9+15, contempt one-sided 12/14); hysteresis events of at
   least 100 ms; under 500 ms tagged "brief" (candidate microexpression). Labels say
   "expression pattern: X (AU list)", descriptions say the pattern is the appearance, not the
   feeling. Same code offline and live.
2. *Deception-research cue profile*: per session and per protocol question, a checklist of
   literature cues measured against the person's own baseline (higher pitch, pressed lips,
   less head movement, longer response latency vs control questions, blink-rate change), each
   shown with its published effect size and source. Output is "k of n cues present" with the
   caveat attached. Not an Event, never a probability, never a verdict.

**Rejected.** Emotion labels ("angry", "happy") as facts; any per-question "deception
likelihood"; hiding the effect sizes; a learned deception classifier (no licensed data,
no validated generalization; see scientific-limitations.md).

**Consequences.** The UI shows what the show promised in the honest form: what the face did
(FACS), how long, and which weak literature cues moved. If future licensed data ever allows a
validated model, it would enter as a separate research layer with reported calibration.
