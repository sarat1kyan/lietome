# Lightman installer for Windows (PowerShell).
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.ps1 | iex"
# Installs uv (if missing), then Lightman from the latest GitHub release as an isolated tool,
# downloads and verifies the models, and times them on this machine.
# Options (environment): $env:LIGHTMAN_VERSION="v0.2.0"  $env:LIGHTMAN_NO_SPEECH="1"  $env:LIGHTMAN_SKIP_SETUP="1"
$ErrorActionPreference = "Stop"
$Repo = "sarat1kyan/lietome"
function Say($m) { Write-Host "lightman: $m" }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say "installing uv (Python package manager from astral.sh)"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "uv is not on PATH; open a new terminal and run this again" }

$api = if ($env:LIGHTMAN_VERSION) { "https://api.github.com/repos/$Repo/releases/tags/$($env:LIGHTMAN_VERSION)" } else { "https://api.github.com/repos/$Repo/releases/latest" }
$release = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "lightman-installer" }
$wheel = ($release.assets | Where-Object { $_.name -like "*.whl" } | Select-Object -First 1).browser_download_url
if (-not $wheel) { throw "no release found; see the README for installing from source" }

$extra = if ($env:LIGHTMAN_NO_SPEECH) { "" } else { "[asr]" }
Say "installing $(Split-Path $wheel -Leaf)$extra with Python 3.12"
uv tool install --force --python 3.12 "lightman$extra @ $wheel"
uv tool update-shell | Out-Null

if (-not $env:LIGHTMAN_SKIP_SETUP) {
  $bin = Join-Path (uv tool dir --bin) "lightman.exe"
  try { & $bin setup } catch { Say "setup did not finish; run 'lightman setup' later" }
}
Say "done. Open a new terminal and run: lightman serve"
