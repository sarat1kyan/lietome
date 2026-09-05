# Privacy

Lightman processes biometric behavioral data. Defaults are local-only and minimal.

## Data flow (V0.1)

| Data | Where it goes | Retained? |
|---|---|---|
| Input media | Read in place by PyAV. Never copied. | Not by Lightman. |
| Decoded frames | Process memory only. | No. |
| Landmarks (478x3/frame) | Process memory; turned into scalar features. | No (unless `storage.store_landmarks = true`, currently unimplemented flag reserved). |
| Blendshape coefficients, head pose, EAR, quality | `features.parquet` | Yes (session dir). |
| Face crops | `thumbnails/*.jpg` and inline in `report.html` at event peaks. | Yes, if `storage.event_thumbnails = true` (default). Disable with `--no-thumbnails`. |
| File name + SHA-256 of input | `metadata.json`, `manifest.json` | Yes. Absolute paths are never stored. |
| Subject identity | Anonymous id (`subject_001`) chosen by the operator. | Yes. |
| Environment (OS, CPU, package versions) | `manifest.json` | Yes. No hostnames or usernames. |
| Network | Only `lightman models download` contacts the model host, and only on request. | - |

There is no telemetry, no crash reporting, no analytics.

## Web UI

`lightman serve` binds to 127.0.0.1 by default and has no authentication; do not expose it.
The video stage plays a file you attach from disk through the browser's object URL; the file
is not uploaded. `POST /api/analyze` stores the uploaded file only for the duration of the
analysis unless `keep_media` is requested, in which case it is kept as `media.mp4` in the
session directory so the UI can stream it.

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
