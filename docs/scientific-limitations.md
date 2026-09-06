# Scientific limitations

This document is normative: any feature added to Lightman must be consistent with it.

## The epistemic ladder

| Level | Meaning | Lightman status |
|---|---|---|
| Observation | A measurement with units and error. "EAR fell from 0.31 to 0.09." | Emitted. |
| Interpretation | A named movement. "Blink." "Brow lowering (proxy)." | Emitted, with "(proxy)" where the mapping is unvalidated. |
| Inference | A proposed behavioral/physiological state. "Possible stress-related change." | Not emitted. Requires calibrated evidence we do not have. |
| Speculation | Claims about intent or truthfulness. | Never presented as fact. The schema rejects SPECULATION events. |

Collapsing these levels is the central failure mode of "lie detection" products. Lightman keeps
them separate in the data model, the report, and the language.

## What the current signals are

* **Blendshapes (MediaPipe Blendshape-V2)**: 52 ARKit-style animation coefficients regressed
  from landmarks. They are *not* FACS Action Units. The AU correspondences in
  `features/blendshapes.py` come from semantic definitions; the only published mapping we found
  (Blendshape features meet action units, 2026) was itself built by expert consensus without
  empirical validation. Hence "(proxy)".
* **Action Units (OpenGraphAU)**: occurrence probabilities from a classifier trained on six
  research datasets (posed + spontaneous, lab + in-the-wild). Upstream hybrid-set F1 is low
  (~23, 41 classes, heavy imbalance); per-dataset F1 in the source paper is ~65 on BP4D.
  Probabilities are not FACS intensities. Not validated on this project's footage or
  demographics. Left/right variants are the least reliable outputs.
* **Head pose**: Euler angles from MediaPipe's canonical-face transform. Fine for *changes*;
  absolute accuracy and sign conventions are unverified.
* **Eye aspect ratio**: purely geometric, well-understood (Soukupova & Cech 2016). Blink
  thresholds are subject-relative because EAR varies with eye shape and camera angle.
* **Quality**: a heuristic. It gates statistics; it is not a measurement of anything
  psychological.

## Baseline modeling: what it can and cannot claim

The leading-window baseline says: *this is how the signals looked in the first N seconds of
this recording, under this camera, this lighting, this framing*. A deviation says the signal
left that regime. It does **not** say the subject was calm during the window, nor that the
change has any particular cause. Known confounds: camera motion, zoom (changes face size and
apparent pose), lighting changes, speaking vs. listening, laughing, the question being asked,
the tracker settling (first frames), and chance excursions in noisy signals.

**Speaking is a confound for every mouth signal.** Jaw and lip motion during speech produced
most of the deviation events in the first real sessions. When the calibration window contains
enough speech, a separate speaking-state baseline is built and speaking frames are scored
against it (ADR-013); otherwise mouth-region events during speech are tagged "speaking" with
halved confidence. Calibrate with both silence and talking.

Robust statistics (median/MAD, trimmed SD for degenerate cases) tolerate some contamination of the window by such excursions;
they do not make the window representative.

Near-constant signals hit the per-unit *scale floor*; small render/tracker jitter can then
exceed 3 SD. This is visible in the baseline (`floor_applied`) and noted in the report. Treat
events on floored signals with extra suspicion.

**Adaptation is bounded on purpose.** After calibration each signal tracks the subject slowly
(half-life 60 s) within limits set by the calibration (ADR-014). A deviation therefore means
"unusual relative to this person's behavior so far in this session"; slow drifts over minutes
are partly absorbed and appear in the stored baselines rather than as events.

## Microexpression spotting

Public benchmarks (CASME II, SAMM, SMIC, CAS(ME)3) are small (16-100 subjects), lab-elicited,
high-frame-rate, and mostly East-Asian or European young adults. Cross-dataset generalization is
poor. In MEGC 2025 the spot-then-recognize score (STRS) of participating systems was ~ 0.006 on
SAMM and ~ 0.009 on CAS(ME)3, i.e. spotting is the bottleneck and remains far from usable.
Lightman therefore treats microexpression spotting as a research track with rigorous
subject-independent (LOSO) and cross-dataset evaluation, not as a product feature.

## Voice

Current implementation: Silero VAD, pyin F0, RMS energy, pauses, syllable-rate proxy and
*approximate* jitter/shimmer from frame tracks. Baselines use speech frames only. Without
diarization, several speakers are pooled into one baseline; without question/answer structure,
response latency is not measured. The pipeline reports voice pitch/loudness deviations and
long pauses as observations only.

Decades of research and reviews by the U.S. National Research Council and others find that
"voice stress analysis" devices perform at chance for deception. Acoustic features (F0, energy,
jitter, shimmer, speech rate, pauses, response latency) *are* measurable and *do* vary with
arousal and cognitive load. Lightman will measure them as observations and compare them to the
subject's baseline, and will not label them "stress" or "deception".

## Deception

There is no validated, generalizable, single-channel or multimodal behavioral signature of
deception. Published multimodal deception datasets (Real-life Trial, Bag-of-Lies, MU3D,
Box-of-Lies, DOLOS) are small, culturally narrow, and mix low-stakes with high-stakes settings;
cross-domain benchmarks show large drops. Any future "deception hypothesis" module must:
state uncertainty; distinguish deception from stress, anxiety, fear, and cognitive load (it
cannot, from behavior alone); avoid deterministic output; document dataset, cultural, and
demographic limits; expose calibration, false-positive and false-negative rates. Until such a
module exists with evidence, Lightman's ceiling is *behavioral deviation analysis*.

## Population and fairness

Face models can perform differently across skin tones, ages, facial hair, glasses, and
head-covering. Baseline-relative analysis reduces (but does not remove) between-person bias
because each subject is compared with themselves. We do not yet measure this. Any published
claim about accuracy must include per-group results.

## What a Lightman result may be used for

Prompting a human analyst to look at a moment in a recording and inspect the evidence. Nothing
in the output is suitable as evidence of honesty, intent, or character.
