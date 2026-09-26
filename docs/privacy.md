# Privacy

Lightman processes biometric behavioral data. Defaults are local-only and minimal.

## Data flow (V0.1)

| Data | Where it goes | Retained? |
|---|---|---|
| Input media | Read in place by PyAV. Never copied. | Not by Lightman. |
| Decoded frames | Process memory only. | No. |
| Landmarks (478x3/frame) | Process memory; turned into scalar features. | No (unless `storage.store_landmarks = true`, currently unimplemented flag reserved). |
| Blendshape coefficients, head pose, EAR, quality | `features.parquet` | Yes (session dir). |
| Subject norms (median calibration center/spread per signal, last 20 sessions) | `<output>/_subjects/<id>.json` | Yes. Delete the file to reset. |
| Skin color means (3 floats/frame over forehead and cheeks, for the pulse estimate) | `features.parquet`, `pulse.json` | Yes (session dir). Not an identifier; disable with `[pulse] enabled = false`. |
| Session audio (live) | Process memory (int16), transcribed after the session, then released. | No. Only the transcript is kept. |
| Transcript (words with times, hedges, denials) | `transcript.json`, answer text in `protocol.json` | Yes (session dir). Disable with `[speech] enabled = false`. |
| Video recording (live, opt-in) | `media.webm` + `media.json` in the session dir | Only when the operator ticks "record video". Delete the files to remove it. |
| Face crops | `thumbnails/*.jpg` and inline in `report.html` at event peaks. | Yes, if `storage.event_thumbnails = true` (default). Disable with `--no-thumbnails`. |
| File name + SHA-256 of input | `metadata.json`, `manifest.json` | Yes. Absolute paths are never stored. |
| Subject identity | Anonymous id (`subject_001`) chosen by the operator. | Yes. |
| Environment (OS, CPU, package versions) | `manifest.json` | Yes. No hostnames or usernames. |
| Network | Models are fetched from their pinned URLs on first use (or with `lightman models download`), SHA-256 verified. Set `models.allow_download = false` to forbid downloads. Nothing else leaves the machine. | - |

There is no telemetry, no crash reporting, no analytics.

## Web UI

`lightman serve` binds to 127.0.0.1 by default without authentication. With `--host` set to a
non-loopback address it requires a random token (URL once, then cookie) and serves HTTPS with
a self-signed certificate (ADR-015); anyone holding the URL can read sessions while the server
runs.
The video stage plays a file you attach from disk through the browser's object URL; the file
is not uploaded. `POST /api/analyze` stores the uploaded file only for the duration of the
analysis unless `keep_media` is requested, in which case it is kept as `media.mp4` in the
session directory so the UI can stream it.

## Browser live tab

The page asks the browser for camera/microphone permission. Frames (JPEG) and audio (16 kHz
PCM) are sent to the local server over a WebSocket, analyzed in memory and discarded; only
features and events are written to the session directory. A red LIVE badge is shown on the
self-view while capture runs.

## Live mode

`lightman live` prints a visible notice naming the camera, and the preview window is labelled
"LIVE ANALYSIS". Frames are analyzed in memory and discarded; no video or audio is written.
The session directory contains the same feature/event tables as prerecorded analysis (no
thumbnails). Stop with q in the preview or Ctrl-C. Camera and microphone permissions are
granted by the operating system to the terminal or app running Lightman; Lightman never
bypasses them.

## Logging

Structured logs record processing events (session created, frames decoded, model loaded,
counts, timings). They never contain landmark arrays, embeddings, transcripts, names, or full
input paths.

## Deletion

Delete the session directory. Nothing else is written outside it except the model cache
(`lightman doctor` prints its location), which contains only public model files.

## Roadmap items

no-retention mode (in-memory report only), encrypted session directories, automatic expiry,
metadata-only mode (no thumbnails, no per-frame table), explicit recording indicator for live
mode, consent prompt and on-screen indicator for webcam capture. Covert capture will not be a
default behavior of any Lightman component.
