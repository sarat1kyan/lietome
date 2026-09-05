# Lightman

**Lightman is an open-source, local-first platform for analyzing observable human behavior
over time** - facial motion, head pose, blinks, and (in upcoming phases) voice and speech
timing - and comparing it against a **subject-specific baseline**.

It is a research and analysis instrument. **It is not a lie detector**, and it will not tell
you that someone is lying. It tells you *what measurably changed, when, by how much relative
to that person's own baseline, and how much to trust the measurement*.

> Behavioral deviation 2.6 SD , `browDownLeft` up (AU4 proxy) , 420 ms , face quality 0.97 , baseline quality 0.71
> - *this event alone establishes nothing about truthfulness.*

## Philosophy

**Measure observable behavior first. Interpret cautiously second.**

Every result carries an explicit evidence level and is traceable to the frames, signals, model
version, and baseline that produced it:

| Level | Example | Emitted today |
|---|---|---|
| **Observation** | `blendshape.browDownLeft` reached 0.81 (+3.4 SD vs baseline median 0.12) | yes |
| **Interpretation** | blink; co-occurring deviation across 3 signals | yes |
| **Inference** | possible stress-related change | no (future, with calibration data) |
| **Speculation** | deception | never presented as fact |

## What works now (v0.1.0a0)

```bash
uv sync
uv run lightman models download mediapipe/face_landmarker   # 3.7 MB, SHA-256 verified
uv run lightman models download opengraphau/resnet50_s2     # 143 MB AU model (or resnet18_s2, 48 MB)
uv run lightman models download silero/vad_v6               # 2.3 MB voice activity model
uv run lightman analyze interview.mp4 -o output/
```

Produces `output/<session_id>/`:

| File | Content |
|---|---|
| `metadata.json` | container/stream info, file hash (no absolute paths) |
| `features.parquet` | per-frame table: us timestamps, head pose, eye aspect ratio, 52 blendshape coefficients, 41 Action Unit probabilities, quality |
| `audio_features.parquet`, `speech_segments.json`, `audio_baseline.json` | 20 ms voice frames (F0, energy, voicing, speech probability), speech segments with pause/rate/pitch statistics, speaker baseline |
| `baseline.json` | robust per-signal baseline (median, 1.4826,MAD, sample counts, reliability) |
| `events.json` | blinks, per-signal baseline deviations, co-occurrence clusters - each with contributors, confidence, quality, provenance |
| `analysis.json` | summary statistics and stage timings |
| `report.html` | self-contained inspection report: timelines in SD units, ranked events, thumbnails |
| `manifest.json` | versions, model hashes, environment, config snapshot, output hashes |

Measured on Apple M5 Pro (CPU only): **3.5 ms/frame** landmarks + blendshapes, **67-88 ms/frame**
AU detector (resnet50) or **17-20 ms** (resnet18). A 20 s 640x480 clip takes 3.4 s without AUs,
58 s with the default AU model. See `docs/benchmarks.md`.

### Live webcam

```bash
uv run lightman live                    # camera 0, preview window, landmarks + blendshapes
uv run lightman live --au               # adds the fast AU model (resnet18), still 30 fps on M5 Pro CPU
uv run lightman live --source clip.mp4  # replay a file at real-time pace (no camera needed)
```

Baseline is calibrated on the first 30 s; deviation and blink events print as they happen and
a normal session directory is written when you press q. Frames are never saved.

## What it does not do (yet, or ever)

* Audio covers voice activity, pitch, loudness, pauses; no transcription, no diarization,
  no question/answer timing yet (Phase 6).
* Action Units come from OpenGraphAU (occurrence probabilities, research-dataset training,
  not validated on our footage). Blendshape-derived AU hints stay labelled **"(proxy)"**.
* No microexpression spotting. State of the art on public benchmarks is far from usable
  (MEGC 2025 spot-then-recognize scores ~ 0.006-0.009); see `docs/scientific-limitations.md`.
* No deception score. See the same document for why.
* Single face per video; multi-person tracking is on the roadmap.
* Live mode is video-only so far (no microphone yet).

## Documentation

* `docs/architecture.md` - pipeline, module boundaries, data model
* `docs/scientific-limitations.md` - what the signals can and cannot support
* `docs/privacy.md`, `docs/security.md` - data handling and threat model
* `docs/licensing.md`, `docs/models.md`, `docs/datasets.md` - every third-party component and why it was accepted or rejected
* `docs/research/` - stack research with sources; answers to the founding research questions
* `docs/roadmap.md`, `docs/project-state.md` - where we are and what's next
* `docs/adr/` - architecture decision records

## Development

```bash
uv sync && uv run pre-commit install
uv run pytest -q              # 55 tests, ~5 s; model tests skip unless the model is cached
uv run ruff check src tests && uv run mypy
```

Python >= 3.12. Tested on macOS (Apple Silicon) and Linux in CI. See `CONTRIBUTING.md`.

## License

Apache-2.0 (see `LICENSE`). Third-party model and dataset licenses are tracked in
`docs/licensing.md`; nothing with research-only or non-commercial terms ships in the core.

## Disclaimer

Lightman is inspired by the fictional behavioral-analysis work portrayed in the television
series *Lie to Me*. It is an independent open-source project. It is not affiliated with,
endorsed by, or connected to that series, its producers, broadcasters, cast, rights holders,
or any researcher depicted or referenced by it. No material from the series is used.

Lightman analyzes observable behavioral signals. It does not and cannot provide reliable lie
detection, and its output must not be used as evidence of anyone's honesty, intent, or
character.
