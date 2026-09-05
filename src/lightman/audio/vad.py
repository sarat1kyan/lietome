"""Voice activity detection with the Silero VAD ONNX model (MIT) via onnxruntime.

The model is stateful: each 512-sample chunk at 16 kHz is fed with the previous 64 samples of
context prepended (576 inputs) and a recurrent state of shape (2, 1, 128). Output is a speech
probability per chunk (32 ms).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from lightman import __version__
from lightman.core.logging import get_logger
from lightman.schema.provenance import Provenance

log = get_logger(__name__)

EXTRACTOR_ID = "audio.silero_vad_onnx"
EXTRACTOR_VERSION = "0.1.0"
RATE = 16_000
CHUNK = 512
CONTEXT = 64
CHUNK_US = CHUNK * 1_000_000 // RATE  # 32000 us


@dataclass(slots=True)
class SpeechSegment:
    start_us: int
    end_us: int
    mean_prob: float


class SileroVAD:
    def __init__(self, model_path: Path, *, model_id: str, model_sha256: str | None = None) -> None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        so.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), sess_options=so, providers=["CPUExecutionProvider"]
        )
        self._provenance = Provenance(
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            model_id=model_id,
            model_sha256=model_sha256,
            runtime=f"onnxruntime-{ort.__version__}-cpu",
            lightman_version=__version__,
        )
        log.info("vad_loaded", backend=EXTRACTOR_ID)

    @property
    def provenance(self) -> Provenance:
        return self._provenance

    def probabilities(self, samples: npt.NDArray[np.float32]) -> npt.NDArray[np.float32]:
        """Speech probability for each consecutive 512-sample chunk (32 ms at 16 kHz)."""
        x = np.asarray(samples, dtype=np.float32)
        n = x.size // CHUNK
        out = np.zeros(n, dtype=np.float32)
        state = np.zeros((2, 1, 128), dtype=np.float32)
        ctx = np.zeros(CONTEXT, dtype=np.float32)
        sr = np.array(RATE, dtype=np.int64)
        for i in range(n):
            chunk = x[i * CHUNK : (i + 1) * CHUNK]
            inp = np.concatenate([ctx, chunk])[None, :]
            prob, state = self._session.run(None, {"input": inp, "state": state, "sr": sr})
            out[i] = float(prob.ravel()[0])
            ctx = chunk[-CONTEXT:]
        return out

    def close(self) -> None:
        del self._session


def segments_from_probabilities(
    probs: npt.NDArray[np.floating],
    *,
    origin_us: int,
    threshold: float = 0.5,
    min_speech_ms: int = 250,
    min_silence_ms: int = 300,
    pad_ms: int = 30,
) -> list[SpeechSegment]:
    """Turn per-chunk probabilities into speech segments (hysteresis-free, gap-merged)."""
    speech = probs >= threshold
    segs: list[list[int]] = []
    start: int | None = None
    for i, s in enumerate(speech):
        if s and start is None:
            start = i
        elif not s and start is not None:
            segs.append([start, i])
            start = None
    if start is not None:
        segs.append([start, len(speech)])
    # merge gaps shorter than min_silence
    min_gap = max(1, min_silence_ms * 1000 // CHUNK_US)
    merged: list[list[int]] = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_gap:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    min_len = max(1, min_speech_ms * 1000 // CHUNK_US)
    out: list[SpeechSegment] = []
    pad = pad_ms * 1000
    for a, b in merged:
        if b - a < min_len:
            continue
        out.append(
            SpeechSegment(
                start_us=max(0, origin_us + a * CHUNK_US - pad),
                end_us=origin_us + b * CHUNK_US + pad,
                mean_prob=float(np.mean(probs[a:b])),
            )
        )
    return out
