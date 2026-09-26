# ADR-025 Subject screen and the blind validation game

**Context.** Two problems for tests with friends. The subject watched the operator's screen
(HUD, numbers, gauges) and could react to their own readings. And nothing measured whether
any readout works for a given person: the operator's "expected" labels were guesses.

**Decision.**

1. *Subject screen.* `#subject` on the same URL opens a view with only the calibration
   instruction and passage, the current question, and in validation mode a private card.
   The operator's live page posts subject state over its live WebSocket (`type: subject`);
   a hub keeps the latest state and fans it out on `/api/subject`. State is whitelisted
   (status, phase, instruction, passage, remaining, question, card, note) and bounded; the
   subject screen never receives measurements. Same access rules as the live socket.
2. *Blind validation game.* Template "validation card game (blind)": relevant questions that
   can be answered either way. With blind on, the app draws truth or lie per relevant question
   at ask time, shows it only on the subject screen (green "Tell the TRUTH" or red "LIE on this
   answer") and records it as the expected label. The operator sees "?" until the session ends.
3. *Scoring.* Per session: AUROC with a stratified bootstrap 95% interval for the deviation
   score, the calibration index and the control-referenced index. Per subject:
   `GET /api/subjects/{id}/validation` pools labelled answers across sessions; the history
   card shows the three AUROCs with intervals and the item counts.

**Rejected.** Letting the operator see the card (unblinds the operator's own reading of the
face). Accuracy at a fixed threshold (depends on the threshold; AUROC does not).

**Consequences.** The only per-person evidence the app can produce that a readout carries
information. With under about 20 items per class the intervals stay wide; the note says so.
