# Privacy

Lightman processes biometric behavioral data. Defaults are local-only and minimal.

## Data flow (V0.1)

| Data | Where it goes | Retained? |
|---|---|---|
| Input media | Read in place by PyAV. Never copied. | Not by Lightman. |
| Decoded frames | Process memory only. | No. |
| Landmarks (478x3/frame) | Process memory; turned into scalar features. | No (unless `storage.store_landmarks = true`, currently unimplemented flag reserved). |
| Blendshape coefficients, head pose, EAR, quality | `features.parquet` | Yes (session dir). |
| Face crops | `thumbnails/*.png` and inline in `report.html` at event peaks. | Yes, if `storage.event_thumbnails = true` (default). Disable with `--no-thumbnails`. |
| File name + SHA-256 of input | `metadata.json`, `manifest.json` | Yes. Absolute paths are never stored. |
| Subject identity | Anonymous id (`subject_001`) chosen by the operator. | Yes. |
| Environment (OS, CPU, package versions) | `manifest.json` | Yes. No hostnames or usernames. |
| Network | Only `lightman models download` contacts the model host, and only on request. | - |

There is no telemetry, no crash reporting, no analytics.

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
