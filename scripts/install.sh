#!/usr/bin/env sh
# Lightman installer for macOS and Linux.
#   curl -LsSf https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.sh | sh
# Installs uv (if missing), then Lightman from the latest GitHub release as an isolated tool,
# downloads and verifies the models, and times them on this machine.
# Options (environment): LIGHTMAN_VERSION=v0.2.0  LIGHTMAN_NO_SPEECH=1  LIGHTMAN_SKIP_SETUP=1
set -eu

REPO="sarat1kyan/lietome"
say() { printf '%s\n' "lightman: $*"; }
fail() { printf '%s\n' "lightman: $*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || fail "curl is required"

if ! command -v uv >/dev/null 2>&1; then
  say "installing uv (Python package manager from astral.sh)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
  export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || fail "uv is not on PATH; open a new terminal and run this again"

if [ -n "${LIGHTMAN_VERSION:-}" ]; then
  api="https://api.github.com/repos/$REPO/releases/tags/$LIGHTMAN_VERSION"
else
  api="https://api.github.com/repos/$REPO/releases/latest"
fi
wheel=$(curl -fsSL "$api" | grep -o '"browser_download_url": *"[^"]*\.whl"' | head -1 | sed 's/.*"\(https[^"]*\)"/\1/') \
  || fail "could not read the release list from GitHub"
[ -n "$wheel" ] || fail "no release found; see the README for installing from source"

extra="[asr]"
[ -n "${LIGHTMAN_NO_SPEECH:-}" ] && extra=""
say "installing $(basename "$wheel")$extra with Python 3.12"
uv tool install --force --python 3.12 "lightman$extra @ $wheel"
uv tool update-shell >/dev/null 2>&1 || true

if [ -z "${LIGHTMAN_SKIP_SETUP:-}" ]; then
  "$(uv tool dir --bin)/lightman" setup || say "setup did not finish; run 'lightman setup' later"
fi
say "done. Open a new terminal and run: lightman serve"
