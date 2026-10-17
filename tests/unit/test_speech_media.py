import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from lightman.api.app import create_app
from lightman.speech.markers import annotate, answers_text, mark_words
from lightman.speech.transcribe import Transcript, Word, transcribe_session


def _words(text: str, start_us: int = 0, step_us: int = 300_000) -> list[dict]:
    return [
        {
            "start_us": start_us + i * step_us,
            "end_us": start_us + i * step_us + 250_000,
            "word": w,
            "prob": 0.9,
        }
        for i, w in enumerate(text.split())
    ]


def test_markers_prefer_longer_denials_and_find_hedges() -> None:
    ws = _words("No, I did not take it. I think maybe it was there, to be honest.")
    marks = mark_words(ws)
    kinds = [(m["kind"], m["phrase"]) for m in marks]
    assert ("denial", "no") in kinds and ("denial", "did not") in kinds
    assert ("denial", "not") not in kinds  # covered by "did not"
    assert (
        ("hedge", "i think") in kinds
        and ("hedge", "maybe") in kinds
        and ("hedge", "to be honest") in kinds
    )


def test_annotate_aligns_denials_and_skips_other_languages() -> None:
    ws = _words("No I never did that", start_us=10_000_000)
    ev = [
        {"event_id": "ev_1", "event_type": "expression_pattern", "start_us": 10_400_000,
         "end_us": 10_700_000, "severity": 3.0, "label": "brief expression pattern: fear"},
        {"event_id": "ev_2", "event_type": "blink", "start_us": 10_100_000, "end_us": 10_200_000,
         "severity": 1.0, "label": "blink"},
    ]  # fmt: skip
    q = [{"id": "q1", "start_us": 9_000_000, "end_us": 20_000_000}]
    doc = annotate({"language": "en", "words": ws}, ev, q)
    assert doc["denial_moments"] and doc["denial_moments"][0]["events"][0]["event_id"] == "ev_1"
    assert all(e["event_type"] != "blink" for d in doc["denial_moments"] for e in d["events"])
    assert doc["answers"]["q1"]["denials"] == 2 and doc["answers"]["q1"]["words"] == 5
    ru = annotate({"language": "ru", "words": ws}, ev, q)
    assert ru["markers"] == [] and "English only" in ru["marking"]
    assert answers_text(ws, [{"id": "x", "start_us": 0, "end_us": 1}])["x"]["words"] == 0


class _FakeTranscriber:
    def transcribe(self, pcm, origin_us=0, language=None):  # type: ignore[no-untyped-def]
        return Transcript(
            language="en",
            language_prob=0.99,
            words=[
                Word(origin_us + 500_000, origin_us + 800_000, "No,", 0.9),
                Word(origin_us + 900_000, origin_us + 1_200_000, "never.", 0.9),
            ],
            segments=[],
            model="fake",
        )


def test_transcribe_session_writes_transcript_and_answer(tmp_path: Path) -> None:
    (tmp_path / "events.json").write_text(json.dumps({"events": []}))
    (tmp_path / "protocol.json").write_text(
        json.dumps({"questions": [{"id": "q1", "start_us": 0, "end_us": 5_000_000}]})
    )
    doc = transcribe_session(
        tmp_path, np.zeros(16_000, dtype=np.float32), 1_000_000, _FakeTranscriber()
    )
    assert doc["status"] == "done" and len(doc["words"]) == 2
    assert doc["words"][0]["start_us"] == 1_500_000
    proto = json.loads((tmp_path / "protocol.json").read_text())
    assert proto["questions"][0]["answer"]["text"] == "No, never."
    none = transcribe_session(tmp_path, np.zeros(16_000, dtype=np.float32), 0, None)
    assert none["status"] == "unavailable" and "asr" in none["reason"]


def test_live_audio_keeps_pcm_for_transcription() -> None:
    from lightman.config import BaselineConfig, LightmanConfig
    from lightman.live.audio_stream import StreamingAudioAnalyzer
    from tests.unit.test_audio_stream import _FakeVAD, _tone

    cfg = LightmanConfig(baseline=BaselineConfig(window_s=2.0, min_samples=10, good_samples=30))
    an = StreamingAudioAnalyzer(cfg, _FakeVAD(), subject_id="s")  # type: ignore[arg-type]
    x = _tone(150.0, 1.0)
    an.push(x[:8000], 2_000_000)
    an.push(x[8000:], 2_500_000)
    pcm, origin = an.session_pcm()
    assert origin == 2_000_000 and pcm.size == x.size
    assert np.max(np.abs(pcm - x)) < 1e-3
    assert an.session_pcm()[0].size == 0  # released


def test_recording_upload_and_serving(tmp_path: Path) -> None:
    sid = "20260101T000000Z-dddddd"
    d = tmp_path / sid
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"subject_ids": ["s"]}))
    (d / "analysis.json").write_text(json.dumps({"mode": "live"}))
    client = TestClient(create_app(tmp_path))
    bad = client.post(f"/api/sessions/{sid}/media", files={"file": ("x.txt", b"hi", "text/plain")})
    assert bad.status_code == 415
    ok = client.post(
        f"/api/sessions/{sid}/media",
        files={"file": ("r.webm", b"\x1aE\xdf\xa3" + b"0" * 100, "video/webm")},
        data={"offset_us": "120000"},
    )
    assert ok.status_code == 201 and ok.json()["file"] == "media.webm"
    assert client.get(f"/api/sessions/{sid}/media-info").json()["offset_us"] == 120000
    m = client.get(f"/api/sessions/{sid}/media")
    assert m.status_code == 200 and m.headers["content-type"].startswith("video/webm")
    assert client.get("/api/sessions").json()[0]["has_media"] is True
    assert client.get(f"/api/sessions/{sid}/transcript").json() == {"status": "none"}
