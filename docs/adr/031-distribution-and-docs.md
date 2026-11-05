# ADR-031 Distribution: installers, setup command, releases, documentation

**Context.** Installing Lightman meant cloning the repository, installing uv and Node.js,
building the interface and downloading models by name. Practitioners will not do that. The
installed tool also wrote sessions to `./output` in whatever folder it was started from.

**Decision.**

1. *Wheel with the interface.* The built web UI is included in the wheel
   (`artifacts = ["src/lightman/api/static/**"]`), together with a bundled benchmark image.
   Installing the wheel needs no Node.js.
2. *Installers.* `scripts/install.sh` and `scripts/install.ps1` install uv if missing, install
   the latest GitHub release with `uv tool install --python 3.12 "lightman[asr] @ <wheel>"`,
   and run `lightman setup`. `LIGHTMAN_VERSION`, `LIGHTMAN_NO_SPEECH` and `LIGHTMAN_SKIP_SETUP`
   change that.
3. *`lightman setup`.* Downloads and verifies the face, AU (resnet18 and resnet50), voice
   activity and pose models, Whisper base when speech-to-text is installed, runs the benchmark,
   and prints how to start. `--minimal` and `--skip-bench` for slow links.
4. *Sessions folder.* `./output` when it exists (development), otherwise the platform user
   data folder (`platformdirs`). `serve` prints the path.
5. *Releases.* A `v*` tag builds the interface, checks the tag matches the package version,
   builds the wheel and sdist, verifies the wheel contains the interface, publishes a GitHub
   release with the changelog notes, and pushes `ghcr.io/<owner>/lightman:<tag>` and `latest`.
6. *Docs.* README rewritten for practitioners; new `docs/installation.md`,
   `docs/user-guide.md`, `docs/ethics.md`; issue and pull request templates.

**Consequences.** One command installs a working tool on macOS, Linux and Windows. The
installers depend on a published release; until the first tag they fail with a clear message,
and from-source install stays documented. No PyPI package yet: the name and the size of the
dependency set need a decision first.
