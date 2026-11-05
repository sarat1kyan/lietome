# ADR-028 Clients, consent records, session notes, export and erasure

**Context.** Lightman is moving from a personal experiment to a tool for people who work with
people: psychologists, counsellors, coaches, researchers. Their first needs are not new
measurements. They need to know whose session this is, to prove the person agreed, to write
their own observations next to the measurements, and to give a client their data or delete
it on request.

**Decision.**

1. *Clients.* A client is a short pseudonymous code (`C-014`) used as the session subject id.
   An optional label and note live in `<output>/_clients/<code>.json` on this machine.
   `GET /api/clients` lists registered codes and codes found only in sessions, with counts.
2. *Consent.* `ConsentRecord`: who agreed (client, guardian, self), how (verbal, written,
   electronic), scope (video analysis, audio analysis, recording, transcription), practitioner
   initials, time. With `practice.require_consent = true` (default) a live session does not
   start and an upload is refused (HTTP 428) without a record whose scope includes video
   analysis. The microphone, transcription and the video recording only run when in scope;
   a recording upload outside scope gets 403. Every session stores consent.json; command-line
   analyses record that consent was not captured in Lightman.
3. *Notes.* notes.json per session: free text, optionally pinned to a moment. Live note
   markers become notes when the session is saved. CRUD under
   `/api/sessions/{id}/notes`.
4. *Export and erasure.* `GET /api/clients/{code}/export` returns a zip of the entry, norms
   and every session. `DELETE /api/clients/{code}?confirm={code}` deletes all of it; the UI
   asks for the code to be typed.
5. *Settings.* `/api/settings`: interface profile (practice or research), onboarding flag,
   practitioner initials, in `<output>/_settings.json`.

**Rejected.** Storing client names in sessions (codes travel, names stay local). Soft delete
(erasure requests mean deletion).

**Consequences.** Every live and uploaded analysis now requires a consent step in the UI;
API clients must send a consent record.
