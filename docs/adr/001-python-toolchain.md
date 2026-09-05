# ADR-001 Python toolchain

**Context.** The project must run on macOS (Apple Silicon) and Linux (CUDA desktop), be
reproducible, and be pleasant for several engineers.

**Decision.** Python >= 3.12 (3.12 default, 3.13 in CI). `uv` for environments and the lockfile
(`uv.lock`); hatchling build backend; `ruff` for lint + format (line 100, security and bugbear
rule sets on); `mypy --strict` with the pydantic plugin; `pytest` + `hypothesis`; `pre-commit`
with ruff, hygiene hooks, and detect-secrets; `pip-audit` in CI.

**Why not** Poetry (slower, no interpreter management), pip-tools (no env management), pyright
(mypy plugin ecosystem for pydantic is mature; either is fine - don't run both).

**Consequences.** Python 3.14 is not blocked (all core deps resolve) but not tested; add to the
matrix when PyTorch CUDA coverage is confirmed.
