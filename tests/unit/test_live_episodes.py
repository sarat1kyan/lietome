from lightman.live.streaming import StreamingEpisodes, is_mouth_signal, tag_speaking
from lightman.schema.events import Event, EvidenceLevel, FeatureContribution


def _dev(eid: str, feature: str, start: int, end: int, z: float) -> Event:
    return Event(
        event_id=eid,
        subject_id="s",
        source="video",
        event_type="baseline_deviation",
        level=EvidenceLevel.OBSERVATION,
        start_us=start,
        end_us=end,
        peak_us=start,
        label=feature,
        contributions=[
            FeatureContribution(
                feature=feature,
                unit="coefficient",
                peak_value=0.5,
                baseline_center=0.1,
                baseline_scale=0.05,
                peak_deviation=z,
                direction="increase",
            )
        ],
        severity=abs(z),
        confidence=1.0,
        quality=1.0,
        baseline_quality=0.7,
        extractor_id="x",
    )


def test_mouth_signal_classification_and_speaking_tag() -> None:
    assert is_mouth_signal("blendshape.jawOpen") and is_mouth_signal("au.AU25")
    assert not is_mouth_signal("blendshape.browDownLeft") and not is_mouth_signal("au.AU4")
    jaw = tag_speaking(_dev("a", "blendshape.jawOpen", 0, 500_000, 6.0))
    assert "speaking" in jaw.tags and jaw.confidence == 0.5
    brow = tag_speaking(_dev("b", "au.AU4", 0, 500_000, 6.0))
    assert "speaking" not in brow.tags and brow.confidence == 1.0
    assert tag_speaking(jaw).confidence == 0.5  # idempotent


def test_episodes_group_overlapping_events_and_close_after_gap() -> None:
    ep = StreamingEpisodes(subject_id="s", extractor_id="x", gap_us=400_000)
    out = ep.add([_dev("a", "au.AU4", 1_000_000, 1_600_000, 4.0)], now_us=1_600_000)
    assert out == []  # still open
    out = ep.add([_dev("b", "au.AU1", 1_300_000, 1_900_000, 7.0)], now_us=1_900_000)
    assert out == []
    out = ep.add([], now_us=2_400_000)  # gap exceeded -> closes
    assert len(out) == 1
    e = out[0]
    assert e.event_type == "episode" and e.level is EvidenceLevel.INTERPRETATION
    assert e.start_us == 1_000_000 and e.end_us == 1_900_000 and e.severity == 7.0
    assert [c.feature for c in e.contributions] == ["au.AU1", "au.AU4"]
    assert "psychological" in e.description


def test_single_signal_episode_is_dropped_and_speaking_propagates() -> None:
    ep = StreamingEpisodes(subject_id="s", extractor_id="x")
    ep.add([_dev("a", "au.AU4", 0, 300_000, 4.0)], now_us=300_000)
    assert ep.flush() == []  # one signal only
    ep.add(
        [
            tag_speaking(_dev("a", "blendshape.jawOpen", 0, 300_000, 4.0)),
            tag_speaking(_dev("b", "au.AU26", 0, 300_000, 4.0)),
        ],
        now_us=300_000,
    )
    (e,) = ep.flush()
    assert "speaking" in e.tags
