# Security

## Threat model

Attackers control: media files, model files on disk or in transit, configuration files, and
(future) network clients of the API. They want: code execution, file read/write outside the
session dir, resource exhaustion, or corrupted results.

## Controls implemented

* **No shell.** PyAV decodes in-process. The only subprocess calls are fixed argument lists
  (`sysctl`, `nvidia-smi`) for environment detection; none include user data.
* **Pre-allocation limits** (`media/limits.py`): file size (default 4 GiB), declared duration
  (4 h), pixels per frame (4K), decoded frame count (2 M), stream counts. Re-checked per frame
  during decode so a lying container cannot exceed them.
* **Path handling**: input must be a regular file (symlinks resolved explicitly); output names
  are fixed by Lightman (`ev_00012.png`), never derived from input content.
* **Model integrity**: SHA-256 + size pinned in the manifest; streamed downloads abort beyond the
  declared size; temp file + atomic rename; corrupt cache is deleted and re-fetched. Offline
  import goes through the same verification.
* **No unsafe deserialization**: no pickle, no `torch.load`, no YAML. Config is TOML via
  `tomllib`; JSON via stdlib.
* **Dependencies** pinned in `uv.lock`; CI runs `pip-audit --strict` and gitleaks.

## Known gaps / roadmap

* No sandboxing of the decoder. FFmpeg CVEs affect PyAV; keep it updated. Consider running
  decode in a subprocess with resource limits (RLIMIT_AS, seccomp on Linux) for server use.
* No memory cap on Arrow table growth for very long recordings beyond `max_frames`.
* Future ONNX/PyTorch backends must verify hashes and load with `weights_only`/safetensors.
* API layer (FastAPI) will need auth, upload size limits, and per-session quotas.
