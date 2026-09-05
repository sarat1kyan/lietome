# ADR-011 Web UI: FastAPI + Svelte 5 workstation

**Context.** The HTML report is a static artifact. Analysts need to scrub video, click an event
and see its evidence, and compare sessions. The maintainer chose Svelte 5 + Vite + TypeScript
with a hand-written design system (project-state decision, 2026-09-05).

**Decision.** `lightman serve` runs a FastAPI app bound to 127.0.0.1 by default. Read-only
endpoints expose session lists, manifests, events, baselines, decimated feature series
(video and audio tables), thumbnails and retained media. `POST /api/analyze` accepts an upload
(size-capped), runs the pipeline in a worker thread, and deletes the upload unless
`keep_media` is set. The SPA (frontend/) builds into `src/lightman/api/static` and is served
by the same process. Layout: session rail, video stage with local-file playback (the file never
leaves the browser), canvas timeline in robust-SD units with an event strip and per-signal
lanes, evidence panel with contributors and confidence meters, quality strip. A demo build
(`npm run build:demo`) inlines one session so the UI can be viewed without a server.

**Design.** Dark-first (video is the primary object): ground #0b0f14, panels #10161d, hairlines
#1f2933, text #d7dee7, muted #7c8794; accent amber #d4a24c reserved for evidence/deviation,
cool blue #7fb4e8 for eyes/head, teal #5fb8ae for voice; Instrument Sans for UI, JetBrains Mono
for every number and timestamp. No component kits, no charts library: the timeline is a canvas.

**Rejected.** React (heavier runtime, no benefit for one author), Tailwind/UI kits (generic
look), embedding video into session outputs by default (privacy), WebSocket live view (later,
with live audio).

**Consequences.** Node is a build-time dependency (CI and Docker build the UI; wheels ship the
static files). The API has no auth: it binds to localhost and must not be exposed as-is.
