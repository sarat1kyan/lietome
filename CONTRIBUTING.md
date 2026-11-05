# Contributing

Lightman measures real people, often in vulnerable moments. Contributions are welcome when
they keep it honest, private and careful: measurement code with tests, clearer documentation,
benchmarks on more machines, and reports from people who use it in practice.

## Ground rules

1. **No fake outputs.** Never return a made-up score, confidence, or placeholder model result.
   If a capability is incomplete, say so in code and docs.
2. **Respect the evidence ladder.** Observation, interpretation, inference, speculation. Code
   that emits an event chooses its level honestly (`lightman.schema.EvidenceLevel`). Nothing in
   this repository labels a person as lying, truthful, or as having a condition.
3. **Practice first.** Deception-research material stays behind the research profile. New
   measures shown in the practice profile need a plain-language meaning and caveat.
4. **Consent is not optional.** New ways of capturing data go through the consent scope
   (`lightman.practice.consent`).
5. **Licenses first.** Before adding a dependency, model, or dataset, record its license in
   `docs/licensing.md`. Research-only or non-commercial weights do not go in the core package.
6. **Privacy by default.** Do not log biometric payloads, transcripts, or names. No telemetry.
   Do not commit recordings of real people.
7. **Tests with every change.** Fast tests must not need model downloads; mark model tests
   with `@pytest.mark.model`.

## Setup

```bash
uv sync --extra asr
uv run pre-commit install
(cd frontend && npm ci && npm run build)
uv run lightman setup
```

## Checks

```bash
uv run pytest -q
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy
(cd frontend && npm run check)
```

CI runs the same on Linux, macOS and Windows with Python 3.12 and 3.13, plus model tests,
the Docker build, `pip-audit` and secret scanning.

## Pull requests

* One topic per pull request; the message says why.
* Design changes need a short ADR in `docs/adr/`.
* Update `docs/project-state.md` and `CHANGELOG.md` when behaviour or numbers change.
* Plain ASCII in code, docs and commit messages.
