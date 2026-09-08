import numpy as np

from lightman.interpretation.cues import CUES, cue_profile
from lightman.interpretation.expressions import (
    PATTERN_ENTER,
    StreamingExpressionDetector,
    detect_expression_patterns,
    pattern_scores,
)
from lightman.schema.events import EvidenceLevel


def _aus(n: int, **high: tuple[int, int]) -> dict[str, np.ndarray]:
    names = [
        "AU1",
        "AU2",
        "AU4",
        "AU5",
        "AU6",
        "AU7",
        "AU9",
        "AU12",
        "AU15",
        "AU20",
        "AU23",
        "AU26",
        "AUL12",
        "AUR12",
        "AUL14",
        "AUR14",
    ]
    sig = {f"au.{a}": np.full(n, 0.1) for a in names}
    for au, (a, b) in high.items():
        sig[f"au.{au}"][a:b] = 0.9
    return sig


def test_happiness_pattern_and_brief_tag() -> None:
    n = 300
    t_us = (np.arange(n) * 33_333).astype(np.int64)
    sig = _aus(
        n,
        AU6=(100, 160),
        AU12=(100, 160),
        AU1=(200, 206),
        AU2=(200, 206),
        AU5=(200, 206),
        AU26=(200, 206),
    )
    scores = pattern_scores(sig, n)
    assert scores["happiness"][130] >= PATTERN_ENTER and scores["happiness"][50] < PATTERN_ENTER
    ev = detect_expression_patterns(
        t_us=t_us,
        quality=np.ones(n),
        signals=sig,
        subject_id="s",
        extractor_id="x",
        baseline_quality=0.8,
    )
    names = {e.tags[1]: e for e in ev}
    assert "happiness" in names and "surprise" in names
    h = names["happiness"]
    assert h.level is EvidenceLevel.INTERPRETATION and "brief" not in h.tags
    assert abs(h.start_us - 100 * 33_333) < 40_000 and "not a felt emotion" in h.description
    s = names["surprise"]
    assert "brief" in s.tags and s.label.startswith("brief expression pattern: surprise")
    assert "fear" not in names  # AU4/AU7/AU20 stayed low


def test_contempt_is_unilateral() -> None:
    n = 60
    sig = _aus(n)
    sig["au.AUL12"][20:40] = 0.8  # one-sided lip corner pull
    scores = pattern_scores(sig, n)
    assert scores["contempt"][30] >= PATTERN_ENTER and scores["contempt"][5] < 0.1


def test_streaming_matches_offline_pattern_boundaries() -> None:
    n = 300
    t_us = (np.arange(n) * 33_333).astype(np.int64)
    sig = _aus(n, AU6=(100, 160), AU12=(100, 160))
    off = detect_expression_patterns(
        t_us=t_us,
        quality=np.ones(n),
        signals=sig,
        subject_id="s",
        extractor_id="x",
        baseline_quality=0.8,
    )
    det = StreamingExpressionDetector(
        subject_id="s", extractor_id="x", baseline_quality=0.8, frame_period_us=33_333
    )
    live = []
    for i in range(n):
        live += det.update(int(t_us[i]), 1.0, {k: float(v[i]) for k, v in sig.items()})
    live += det.flush(int(t_us[-1]))
    assert len(live) == len(off) == 1
    assert live[0].start_us == off[0].start_us and abs(live[0].end_us - off[0].end_us) <= 33_333


def test_cue_profile_flags_direction_and_reports_effect_sizes() -> None:
    n = 600
    t_us = (np.arange(n) * 100_000).astype(np.int64)
    signals = {
        "au.AU24": np.full(n, 0.5),  # baseline 0.2 / 0.1 -> +3 SD (pressed lips present)
        "head.speed_deg_s": np.full(n, 2.0),  # baseline 10 / 4 -> -2 SD (less movement present)
    }
    prof = cue_profile(
        window=(0, 60_000_000), t_us=t_us, signals=signals,
        baseline_center={"au.AU24": 0.2, "head.speed_deg_s": 10.0},
        baseline_scale={"au.AU24": 0.1, "head.speed_deg_s": 4.0},
        voice_f0_z=None, blink_times_us=[i * 2_000_000 for i in range(30)],
        reference_blink_rate=30.0, response_latency_ms=1500.0, control_latency_ms=800.0,
    )  # fmt: skip
    by = {c["key"]: c for c in prof["cues"]}
    assert by["lip_press"]["present"] and by["movement"]["present"] and by["latency"]["present"]
    assert not by["blink"]["present"]  # 30/min vs 30 reference
    assert by["pitch"]["value"] is None and not by["pitch"]["present"]
    assert prof["present"] == 3 and prof["evaluated"] == 4
    assert "not a probability" in prof["caveat"]
    assert {c.key for c in CUES} == set(by)
    assert by["pitch"]["effect_size"] == 0.21 and "DePaulo" in by["pitch"]["source"]
