# Security policy

Lightman treats every media file, model file, and configuration file as untrusted input.

## Reporting a vulnerability

Please do not open public issues for security problems. Use GitHub's private vulnerability
reporting on this repository ("Report a vulnerability" under the Security tab). Include a
minimal reproduction (a crafted media file is ideal) and the Lightman version.

We aim to acknowledge reports within 7 days.

## Scope of hardening (current)

* Media is demuxed/decoded with PyAV in-process. Lightman never builds shell commands and never
  invokes `ffmpeg` binaries with user-controlled strings.
* File size, declared duration, per-frame pixel count, decoded frame count, and stream counts
  are limit-checked before pixel memory is allocated (`lightman.media.limits`).
* Model assets are pinned by SHA-256 and size in `src/lightman/models/manifest.json`; downloads
  are streamed with a byte cap, written to a temp file, verified, then atomically renamed.
* No pickle/torch.load of untrusted files. Current model runtime is MediaPipe (`.task` bundle
  of TFLite flatbuffers).
* Outputs never persist absolute input paths; only the file name and hash.
* CI runs `pip-audit` and secret scanning.

See `docs/security.md` for the threat model and roadmap.
