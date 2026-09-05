# Development

## Setup

```bash
uv sync                      # Python 3.12 env in .venv with dev tools
uv run pre-commit install
uv run lightman doctor       # environment + model cache
uv run lightman models download mediapipe/face_landmarker
```

FFmpeg is **not** required (PyAV wheels bundle it). It is handy for creating test clips.

## Everyday commands

```bash
uv run pytest -q                        # fast + model tests (model tests skip if not cached)
uv run pytest -q -m "not model"         # what CI's matrix runs
uv run ruff check src tests --fix && uv run ruff format src tests
uv run mypy
uv export --frozen --no-emit-project --no-hashes --format requirements-txt -o req.txt && uv run pip-audit --strict --disable-pip --no-deps -r req.txt
uv run lightman analyze samples/clip.mp4 -o output/ --fps 15
uv run python experiments/bench_face_landmarker.py
```

## Layout

```
src/lightman/         package (see docs/architecture.md)
tests/unit            fast tests; synthetic media generated with PyAV in tests/conftest.py
tests/integration     real-model tests, @pytest.mark.model
tests/fixtures        small licensed assets only (see docs/licensing.md)
configs/default.toml  documented defaults (a test asserts parity with code defaults)
docs/                 architecture, limitations, privacy, security, licensing, research, ADRs
experiments/          benchmark / research scripts (results recorded in docs/benchmarks.md)
datasets/             adapters + manifests only; data stays out of Git
samples/, output/     gitignored working dirs
```

## Adding a face backend

Implement `lightman.face.base.FaceLandmarker` (`provenance`, `blendshape_names`, `process`,
`close`), add its asset to `models/manifest.json` with SHA-256, add a licensing.md row, add a
`@pytest.mark.model` test on `tests/fixtures/portrait_mediapipe_apache2.jpg`, and a factory
option in `pipeline/analyze.py`.

## Adding an event detector

Write a pure function over numpy arrays in `lightman/events/`, return `Event` objects with an
honest `EvidenceLevel`, unit-test it on synthetic series, wire it in `pipeline/analyze.py`.

## Creating test clips

`tests/conftest.py::write_video` encodes numpy frames with PyAV (H.264, optional AAC, rotation
metadata, custom PTS for VFR). `ken_burns_frames` animates the licensed portrait so a face is
present and moving. Do not add clips of real people to the repo.

## Release checklist (future)

version bump in `pyproject.toml`, CHANGELOG, `uv lock`, tests on both OSes, `pip-audit`, tag.

## Maintainer notes

Read `docs/project-state.md` first, then the ADR index in `docs/adr/`.

Non-negotiables:

1. Epistemic ladder (`lightman.schema.EvidenceLevel`). No SPECULATION events. No output,
   label, docstring or UI string may assert "lying", "truthful", "deceptive".
2. No fake outputs in `src/`. Mocks live in `tests/` and are named as such.
3. Licenses before code. New dependency/model/dataset -> row in `docs/licensing.md` first.
   Research-only or non-commercial weights never go in the core package.
4. Privacy. Never log landmarks, embeddings, transcripts, names or absolute input paths. No
   telemetry. Never copy input media.
5. Hostile input. Media, model files and configs are untrusted. No `shell=True`, no string-built
   commands, limits enforced before allocation, models SHA-256 pinned.

Conventions:

* Media time is `int` microseconds `t_us` (ADR-004). Wall clock is ISO-8601 UTC.
* Signals are `group.name` (`head.yaw_deg`, `eye.aspect_ratio_mean`, `blendshape.browDownLeft`);
  units via `features.table.signal_unit`.
* Blendshape-to-AU text carries "(proxy)".
* Heavy/optional imports (mediapipe, cv2) are lazy, inside functions.
* Fast tests need no downloads; real-model tests carry `@pytest.mark.model`.

Known traps:

* `mediapipe==1.0.1` aborts on macOS arm64 ("Service is unavailable", Metal helper). Pinned out.
  1.0.0 works. Re-test before lifting the pin.
* PyAV and OpenCV each bundle FFmpeg; macOS prints objc duplicate-class warnings. Harmless so
  far. Keep `cv2` use minimal (thumbnails only) so it can be swapped for Pillow.
* MediaPipe VIDEO mode needs strictly increasing ms timestamps; the backend enforces it.
* First frames of tracking are noisy; `events.warmup_ms` suppresses them.

When finishing work: update `docs/project-state.md` (facts only), tests, `CHANGELOG.md`. Add an
ADR only for decisions someone would otherwise re-litigate.
