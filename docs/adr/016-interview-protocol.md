# ADR-016 Interview protocol mode

**Context.** The maintainer wants to run structured sessions: a set of questions, some
neutral or control, some relevant, and compare behavior across them. This is the shape of
the polygraph's Comparison Question Test, whose evidence base for detecting deception is weak
and contested. Lightman can support the *protocol* as an instrument without adopting its
claims.

**Decision.** In the live tab the operator writes a question script (one per line, `C:`/`R:`/
`N:` category prefix, optional `[truth]`/`[lie]` expected class). "Ask next" (or the n key)
sends a timestamped marker; "end answer" and free-text notes are markers too. At stop the
session gets `protocol.json`: per question, response latency (first detected speech onset
after the mark), answer duration and speech fraction, deviation count and rate, episodes,
strongest signals, blink rate, mean voice-pitch deviation, and a descriptive score
(deviations/min + max severity). Categories are compared by mean difference with a permutation
p-value; when expected classes exist for both classes the AUROC of the descriptive score is
reported with the sample sizes. Narrative lines and a table in the UI follow, with the caveats
attached to every number.

**What it does not do.** No question is labelled a lie. The score is descriptive and
unvalidated; with 5-10 questions per session every estimate is wide. Question type, wording,
length and order all move the numbers. Results are per person and per session only.

**Consequences.** Marker timestamps come from the client frame clock; latency depends on the
VAD (microphone on). Prerecorded protocol files are a later addition.
