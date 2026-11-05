# ADR-030 Practice interface: home, session tabs, profiles, onboarding, settings

**Context.** The interface grew panel by panel into one long scroll of research views. A
practitioner opening Lightman needs three things first: start a session, analyse a recording,
find a client. Inside a session they need an overview before raw signals, and the deception
layer should not be the first thing a client sees on the screen.

**Decision.**

1. *Shell.* Top navigation: Home, Clients, Sessions, Live, Settings; an "Analyse a recording"
   button and the active profile always visible. The session list only shows in Sessions.
2. *Home.* Three actions (live session, analyse a recording, clients), recent sessions, a
   warning when models are missing.
3. *Upload with consent.* Drop or choose a video, record consent and the client code, follow
   the analysis job, open the session when it is done.
4. *Session tabs.* Overview (session overview, plain-language summary, key moments, notes,
   quality), Review (video, frame readout, timeline, compare, event list), Conversation
   (transcript, questions, notes), Research (cue profile, possibility index, validation) only
   in the research profile.
5. *Profiles.* Practice (default) hides the cue gauges, the possibility index, the live answer
   gauges and validation games, and filters those lines out of the narrative and the shareable
   report. Research shows everything. Stored in `<output>/_settings.json`.
6. *Onboarding.* Three screens on first run: what Lightman measures, what it is not, initials
   and profile.
7. *Settings.* Profile, initials, consent policy, version, data folder, network access,
   speech-to-text, benchmark, model status (`GET /api/system`).
8. *Report.* The shareable report adds the session overview, practitioner notes and the consent
   record, and shows deception-research sections only in the research profile.

**Consequences.** The research views are unchanged, one tab away. Keyboard review shortcuts
apply in the Review tab.
