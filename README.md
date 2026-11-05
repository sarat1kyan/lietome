# Lightman

**Behavioral insight for people who work with people.**

Lightman watches a conversation through the camera and microphone and measures how a person's
face, voice and posture move, against that same person's baseline: expressed affect,
engagement, who is talking, expressions, gestures, pauses, and the moments worth replaying,
side by side with the transcript and your own notes.

It runs entirely on your computer. Nothing is uploaded. It does not diagnose, it does not read
minds, and it is not a lie detector.

```
Session C-014, 24 min        valence +0.18   arousal -0.05   oriented 86%   client talk 61%
  12:41  brief expression pattern: sadness (AU1+AU4+AU15)        note: "talked about her father"
  12:44  gaze away (down): 3.1 s
  13:02  speech pause: 2.4 s
```

## Who it is for

* **Psychologists, counsellors and therapists**: review a session, see how expression and
  engagement moved, track a client across sessions, export or erase their data on request.
* **Coaches and trainers**: give feedback on presence, pace, pauses and talk balance.
* **Researchers**: the research profile adds deception-research cues, validation games and raw
  signal views, with effect sizes and caveats next to every number.
* **Anyone practising**: interviews, presentations and difficult conversations, reviewed with
  your own consent.

## What it does

| | |
|---|---|
| **Live sessions** | Camera and microphone in the browser. A 40 second calibration (sit, read, talk), then live overlays: face mesh, Action Units with names, expression pattern meter, gaze, head pose, shoulders and hands, voice, pulse estimate, expressed affect. A second screen for the client shows only instructions and questions. |
| **Recordings** | Drop a video file; it is analysed on this machine with the same models. |
| **Session overview** | Expressed affect over time (valence and arousal), engagement, talk time split between client and others, speech rate, pauses, positive and negative expression patterns, a plain-language summary and the key moments with thumbnails. |
| **Review** | Video (if recorded) with the measurements drawn on it, timeline, frame-by-frame readout, event list, compare any two stretches of the session. |
| **Conversation** | Local speech-to-text with word timing; hedges and denials marked; denials that came with a face or body change listed as moments to replay; answers per question. |
| **Clients** | Pseudonymous codes, sessions grouped per client, trends across sessions, export everything as a zip, erase everything with one confirmed action. |
| **Consent built in** | Before every session you record who agreed and to what (analysis, voice, transcript, recording). Without it nothing starts. |
| **Reports** | A single self-contained HTML report per session: overview, notes, key moments, consent record. |

Everything Lightman reports is measured against the person's own calibration and labelled
with what it does and does not mean.

## Install

**macOS and Linux**

```bash
curl -LsSf https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.sh | sh
```

**Windows** (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/sarat1kyan/lietome/main/scripts/install.ps1 | iex"
```

The installer sets up an isolated Python 3.12 environment with
[uv](https://docs.astral.sh/uv/), installs the latest release, downloads and verifies the
models (about 350 MB with speech-to-text), and times them on your machine. Then:

```bash
lightman serve
```

and open **http://127.0.0.1:8710**. Sessions are stored in your user data folder; the path is
printed when the server starts.

Other ways to install (from source, Docker, other devices on your network) and
troubleshooting: [docs/installation.md](docs/installation.md).

## Your first session

1. Open Lightman, finish the three onboarding screens (your initials and the profile).
2. **Start a live session**, choose or create a client code, and record their consent.
3. Sit the person facing the camera in even light, about an arm's length away.
4. Follow the 40 second calibration on screen: sit quietly, read the passage aloud, talk freely.
5. Talk as you normally would. Press **stop and save** at the end and open the session.

The full walkthrough, including how to read the results and how to explain Lightman to a
client: [docs/user-guide.md](docs/user-guide.md).

## Privacy and ethics

* Everything runs locally. No telemetry, no cloud processing, no account.
* Frames are analysed in memory; video is kept only when the consent includes recording.
* Every session stores its consent record. Clients are codes, not names.
* Export or erase everything about a client from the Clients page.
* Lightman must not be used for hiring decisions, interrogation, security screening, covert
  recording, or diagnosis. Read [docs/ethics.md](docs/ethics.md) before using it with others.

## How it works

Video frames go through MediaPipe face landmarks and blendshapes, an Action Unit model
(OpenGraphAU), a pose model for shoulders and hands; audio through voice activity detection,
pitch, loudness and speech rate, and a local Whisper model for the transcript. Every signal is
compared with a robust baseline (median and scaled MAD) from the calibration window, split into
speaking and silent states and allowed to adapt slowly. Events, patterns, affect, engagement and
talk time are built on top, each with its evidence level and the numbers that produced it.

* [Architecture](docs/architecture.md) and [design decisions](docs/adr/README.md)
* [What the measurements can and cannot tell you](docs/scientific-limitations.md)
* [Models, sizes and licences](docs/models.md), [benchmarks](docs/benchmarks.md)

## Documentation

| Guide | |
|---|---|
| [Installation](docs/installation.md) | installers, from source, Docker, network access, troubleshooting |
| [User guide](docs/user-guide.md) | running sessions, reading results, clients, reports |
| [Ethics and intended use](docs/ethics.md) | consent, what not to use it for, talking to clients |
| [Privacy](docs/privacy.md) and [Security](docs/security.md) | what is stored where, access control |
| [Scientific limitations](docs/scientific-limitations.md) | the honest version of every measure |
| [Development](docs/development.md) and [Contributing](CONTRIBUTING.md) | building, testing, conventions |

## Development

```bash
git clone https://github.com/sarat1kyan/lietome && cd lietome
uv sync --extra asr                         # Python 3.12 environment with dev tools
(cd frontend && npm ci && npm run build)    # web UI
uv run lightman setup                       # models + benchmark
uv run lightman serve                       # http://127.0.0.1:8710
uv run pytest -q                            # tests
```

## License

Apache-2.0. Models are downloaded at first use from their original sources, pinned by SHA-256;
each keeps its own licence (Apache-2.0 or MIT), listed in [docs/licensing.md](docs/licensing.md).

Lightman is built by Mher Saratikyan.
