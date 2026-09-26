# ADR-024 Control-referenced scoring, personal norms, pulse check, shareable report

**Context.** The cue index compared every answer with the 40 s calibration: quiet sitting,
reading, free talk. An answer to a question is neither; it is speech under a question. On
real sessions every answer looked "tense" against calibration. Comparison-question designs
use the person's own control answers as the reference. Separately, a single calibration can
be unusually still, and the pulse lane had no way to be checked against a contact device.

**Decision.**

1. *Control-referenced index* (protocol/control.py). For each answer, pool the frames of the
   other control answers (leave-one-out, so control answers get a fair score as well), take
   the pooled median and 1.4826 MAD per signal (floored at half the calibration spread), and
   compute the cue profile against that pool: pattern rates against the control answers,
   blink rate against the control answers, pitch against the control mean, latency against
   the control mean. Needs two control answers. The protocol summary carries control_index
   and control_shift (signals that moved most from the pool); the possibility text uses the
   control-referenced index when every scored question has one and says which basis it used.
   Live: the answer card shows it once two controls exist.
2. *Personal norms* (baseline/norms.py). Each session appends its calibration to
   `<root>/_subjects/<subject>.json` (last 20). From two earlier sessions on, a calibration
   spread under half the usual spread is widened to that half, and a center more than 3 usual
   spreads away is reported as calibration drift. Offline and live.
3. *Pulse check.* Live marker kind `reference` with a bpm value (watch or oximeter). At the
   end each reading is paired with the nearest usable estimate within 8 s; the session
   reports mean absolute error and bias.
4. *Shareable report.* `GET /api/sessions/{id}/share` and `lightman report <dir>` produce one
   self-contained HTML file: stats, indices, question table with both indices, key moments
   with embedded thumbnails, patterns, narrative, pulse check, norms. It contains face images:
   share it only with the person it shows.

**Rejected.** Replacing the calibration with the control pool (calibration is still the
reference for everything that is not a protocol answer). Norm-based centers (only the spread
is bounded; centers are reported, never moved).

**Consequences.** New fields in protocol.json (control_index, control_shift, control_cues,
possibility.basis) and analysis.json (norms, pulse_check). `_subjects/` under the output root.
