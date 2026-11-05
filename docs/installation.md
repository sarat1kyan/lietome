# Installation

## Requirements

| | |
|---|---|
| Operating system | macOS 13 or later (Apple silicon or Intel), Windows 10 or 11, Linux (x86_64 or arm64, glibc) |
| Memory | 4 GB free; 8 GB recommended with speech-to-text |
| Disk | about 1.5 GB for Python packages and 350 MB for models |
| Camera and microphone | any webcam; a separate microphone improves voice measures |
| Browser | a current Chrome, Edge, Firefox or Safari |

Python is handled by the installer (uv downloads Python 3.12 if needed). You do not need
administrator rights.

## One-line installer

**macOS and Linux**

```bash
curl -LsSf https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.sh | sh
```

**Windows** (PowerShell, not as administrator)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.ps1 | iex"
```

What it does:

1. Installs [uv](https://docs.astral.sh/uv/) if it is not already there.
2. Installs the latest Lightman release from GitHub as an isolated command-line tool, with
   speech-to-text.
3. Runs `lightman setup`: downloads the models from their original sources, checks each
   SHA-256, and times them on this machine to choose the live facial model.

Options, set as environment variables before running the installer:

| Variable | Effect |
|---|---|
| `LIGHTMAN_VERSION=v0.2.0` | install a specific release |
| `LIGHTMAN_NO_SPEECH=1` | skip speech-to-text (saves about 200 MB) |
| `LIGHTMAN_SKIP_SETUP=1` | do not download models now; they download on first use |

## Start

```bash
lightman serve
```

Open http://127.0.0.1:8710. The terminal prints where sessions are stored (your user data
folder: `~/Library/Application Support/lightman/sessions` on macOS,
`%LOCALAPPDATA%\lightman\sessions` on Windows, `~/.local/share/lightman/sessions` on Linux).
Use `-o <folder>` to keep them somewhere else.

## Use it from another device on your network

For a second screen for the client, or a laptop in another room:

```bash
lightman serve --host 0.0.0.0
```

This turns on an access token and a self-signed HTTPS certificate (browsers only allow the
camera on secure pages). The terminal prints a link with the token for each network address;
open it on the other device and accept the certificate warning once. On the computer running
Lightman, `http://localhost:8711` keeps working without a token.

## From source

```bash
git clone https://github.com/sarat1kyan/lietome && cd lietome
uv sync --extra asr
(cd frontend && npm ci && npm run build)
uv run lightman setup
uv run lightman serve
```

Node.js 20 or later is needed to build the web interface.

## Docker

```bash
docker compose up --build
docker compose logs lightman      # shows the link with the access token
```

The compose project, container and volumes are all named `lightman`, and everything carries
the label `dev.lightman.project=lightman`. The camera works from the browser on the same
computer (http://localhost:8710).

```bash
docker compose down                                          # stop
docker compose down -v                                       # stop and delete sessions and models
docker images --filter label=dev.lightman.project=lightman   # list what Docker keeps for Lightman
docker volume ls --filter label=dev.lightman.project=lightman
```

## Updating

Run the installer again, or `uv tool upgrade lightman` when installed from a release URL.
Sessions and settings are kept.

## Uninstalling

```bash
uv tool uninstall lightman
```

This removes the program. Your sessions, settings and models stay in the user data and cache
folders until you delete them; `lightman setup` prints their locations.

## Troubleshooting

| Problem | What to do |
|---|---|
| The browser does not ask for the camera | Use http://127.0.0.1:8710 or http://localhost on the same computer, or the HTTPS link on other devices. Check the browser's site permissions. |
| "microphone hears no speech" on the video | The wrong input device is selected in the browser or the operating system, or the microphone is muted. |
| Low frame rate warning | Close other heavy apps; untick "action units" for a lighter live session; run `lightman bench` to see per-model timings. |
| Models fail to download | Check the network; corporate proxies may block GitHub release downloads. `lightman models list` shows what is missing. |
| Certificate warning on another device | Expected with the self-signed certificate; accept it once per device. |
