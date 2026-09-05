import pytest

from lightman.schema.events import Event, EvidenceLevel


def _event(**kw):
    base = {
        "event_id": "ev_00001",
        "subject_id": "s",
        "source": "video",
        "event_type": "blink",
        "level": EvidenceLevel.INTERPRETATION,
        "start_us": 100,
        "end_us": 200,
        "label": "blink",
        "severity": 0.0,
        "confidence": 0.9,
        "quality": 0.9,
        "baseline_quality": 0.5,
        "extractor_id": "x",
    }
    base.update(kw)
    return Event(**base)


def test_speculation_level_rejected() -> None:
    with pytest.raises(ValueError, match="SPECULATION"):
        _event(level=EvidenceLevel.SPECULATION, label="lying")


def test_interval_validation() -> None:
    with pytest.raises(ValueError, match="end_us"):
        _event(start_us=200, end_us=100)
    with pytest.raises(ValueError, match="peak_us"):
        _event(peak_us=999)


def test_duration_property_and_json_roundtrip() -> None:
    e = _event(peak_us=150)
    assert e.duration_us == 100
    assert Event.model_validate_json(e.model_dump_json()) == e
