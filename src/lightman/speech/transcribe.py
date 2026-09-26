"""Local speech-to-text (faster-whisper, CTranslate2) with word timestamps.

Runs on this machine; audio never leaves it. The model (Whisper base, multilingual, MIT) is
SHA-pinned in the model manifest. faster-whisper is an optional dependency (`lightman[asr]`):
without it, or without the model, transcription is skipped and the session says so.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

RATE = 16_000


@dataclass(slots=True)
class Word:
    start_us: int
    end_us: int
    word: str
    prob: float


@dataclass(slots=True)
class Transcript:
    language: str | None
    language_prob: float | None
    words: list[Word] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "language_prob": self.language_prob,
            "model": self.model,
            "segments": self.segments,
            "words": [asdict(w) for w in self.words],
        }


class Transcriber(Protocol):
    def transcribe(
        self, pcm: npt.NDArray[np.float32], origin_us: int = 0, language: str | None = None
    ) -> Transcript: ...


class FasterWhisperTranscriber:
    def __init__(
        self, model_dir: str, *, compute_type: str = "int8", model_id: str = "whisper/base"
    ) -> None:
        from faster_whisper import WhisperModel

        self.model_id = model_id
        self._model = WhisperModel(model_dir, device="auto", compute_type=compute_type)

    def transcribe(
        self, pcm: npt.NDArray[np.float32], origin_us: int = 0, language: str | None = None
    ) -> Transcript:
        x = np.asarray(pcm, dtype=np.float32).reshape(-1)
        segments, info = self._model.transcribe(
            x,
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
            condition_on_previous_text=False,
        )
        words: list[Word] = []
        segs: list[dict[str, Any]] = []
        for s in segments:
            segs.append(
                {
                    "start_us": origin_us + int(s.start * 1e6),
                    "end_us": origin_us + int(s.end * 1e6),
                    "text": s.text.strip(),
                }
            )
            words.extend(
                Word(
                    start_us=origin_us + int(w.start * 1e6),
                    end_us=origin_us + int(w.end * 1e6),
                    word=w.word.strip(),
                    prob=round(float(w.probability), 3),
                )
                for w in s.words or []
            )
        return Transcript(
            language=getattr(info, "language", None),
            language_prob=round(float(getattr(info, "language_probability", 0.0) or 0.0), 3),
            words=words,
            segments=segs,
            model=self.model_id,
        )


def default_transcriber(cfg: Any, registry: Any) -> Transcriber | None:
    """faster-whisper transcriber, or None when speech is off, the extra is missing or the
    model cannot be had."""
    from lightman.core.errors import LightmanError

    if not cfg.speech.enabled:
        return None
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return None
    try:
        d = registry.ensure_group(cfg.speech.model_group)
        return FasterWhisperTranscriber(str(d), compute_type=cfg.speech.compute_type)
    except (LightmanError, OSError, RuntimeError, ValueError):
        return None


def transcribe_session(
    session_dir: Any,
    pcm: npt.NDArray[np.float32],
    origin_us: int,
    transcriber: Transcriber | None,
    *,
    language: str | None = None,
) -> dict[str, Any]:
    """Transcribe, annotate against the session's events and questions, write transcript.json,
    and add answer text to protocol.json. Returns the written document."""
    import json
    from pathlib import Path

    from lightman.speech.markers import annotate

    d = Path(session_dir)
    out_path = d / "transcript.json"
    if transcriber is None or pcm.size < RATE // 2:
        doc: dict[str, Any] = {
            "status": "unavailable",
            "reason": (
                "speech-to-text not installed (pip install lightman[asr])"
                if transcriber is None
                else "no audio"
            ),
        }
        out_path.write_text(json.dumps(doc))
        return doc
    tr = transcriber.transcribe(pcm, origin_us=origin_us, language=language).to_json()

    def read(name: str) -> Any:
        p = d / name
        try:
            return json.loads(p.read_text("utf-8")) if p.is_file() else None
        except (OSError, json.JSONDecodeError):
            return None

    events = (read("events.json") or {}).get("events", [])
    proto = read("protocol.json")
    questions = (proto or {}).get("questions", [])
    doc = {"status": "done", **annotate(tr, events, questions)}
    out_path.write_text(json.dumps(doc))
    if proto and questions:
        for q in proto["questions"]:
            a = doc["answers"].get(q["id"])
            if a is not None:
                q["answer"] = a
        (d / "protocol.json").write_text(json.dumps(proto, indent=2))
    return doc
