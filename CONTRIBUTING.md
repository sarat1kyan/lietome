# Contributing

Thanks for considering a contribution. Lightman is early; the most valuable contributions
right now are careful ones: measurement code with tests, honest documentation, and
benchmarks.

## Ground rules

1. **No fake outputs.** Never return a made-up score, confidence, or placeholder model result. If a
   capability is incomplete, say so in code and docs.
2. **Respect the epistemic ladder.** Observation -> interpretation -> inference -> speculation.
   Code that emits an event must choose its level honestly (`lightman.schema.EvidenceLevel`).
   Nothing in this repository may label a person as lying/truthful.
3. **Licenses first.** Before adding a dependency, model, or dataset, record its license in
   `docs/licensing.md`. Research-only / non-commercial weights do not go in the core package.
4. **Privacy by default.** Do not log biometric payloads, transcripts, or subject names. Do not
   add telemetry. Do not commit recordings of real people.
5. **Tests with every change.** Fast tests must not require model downloads; mark model tests
   with `@pytest.mark.model`.

## Development setup

```bash
uv sync                                 # creates .venv with dev tools
uv run pre-commit install
uv run lightman models download mediapipe/face_landmarker
uv run pytest -q                        # full suite (model tests skip if not cached)
uv run ruff check src tests && uv run mypy
```

## Pull requests

* Keep commits focused; describe *why* in the message.
* Significant design changes need an ADR in `docs/adr/` (short; see existing ones).
* Update `docs/project-state.md` when you change what works, what is known-broken, or
  benchmark numbers.
