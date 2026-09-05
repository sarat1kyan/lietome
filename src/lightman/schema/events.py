"""Events: time-bounded findings with explicit evidence level and contributors."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceLevel(StrEnum):
    """The epistemic ladder. Higher rungs carry more interpretation and less certainty.

    OBSERVATION    - a measurement: "eye_aspect_ratio dropped from 0.31 to 0.09"
    INTERPRETATION - a named movement: "blink", "brow lowering (proxy)"
    INFERENCE      - a proposed behavioral state: "possible stress-related change"
    SPECULATION    - anything about intent or truthfulness. Never emitted by V0.x.
    """

    OBSERVATION = "observation"
    INTERPRETATION = "interpretation"
    INFERENCE = "inference"
    SPECULATION = "speculation"


class FeatureContribution(BaseModel):
    """One signal's contribution to an event, in baseline-relative units."""

    model_config = ConfigDict(frozen=True)

    feature: str = Field(description="Signal name, e.g. 'blendshape.browDownLeft'")
    unit: str = Field(description="Unit of value/baseline, e.g. 'coefficient', 'deg', 'ratio'")
    peak_value: float
    baseline_center: float = Field(description="Robust center (median) of the baseline window")
    baseline_scale: float = Field(description="Robust scale (1.4826*MAD) of the baseline window")
    peak_deviation: float = Field(description="Signed robust z-score at the peak")
    direction: str = Field(pattern="^(increase|decrease)$")


class Event(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    subject_id: str
    source: str = Field(description="Modality: 'video', 'audio', 'speech', 'multimodal'")
    event_type: str = Field(description="Machine-readable type, e.g. 'baseline_deviation', 'blink'")
    level: EvidenceLevel
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    peak_us: int | None = None
    label: str = Field(description="Short human label, carefully worded (see product language)")
    description: str = Field(default="", description="One-sentence factual description")
    contributions: list[FeatureContribution] = Field(default_factory=list)
    severity: float = Field(
        ge=0.0, description="Magnitude, e.g. max |robust z| across contributors"
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence that the *measurement* is real"
    )
    quality: float = Field(ge=0.0, le=1.0, description="Input quality during the event window")
    baseline_quality: float = Field(ge=0.0, le=1.0)
    extractor_id: str = Field(description="Provenance reference into the manifest")
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_interval(self) -> Event:
        if self.end_us < self.start_us:
            raise ValueError("end_us must be >= start_us")
        if self.peak_us is not None and not (self.start_us <= self.peak_us <= self.end_us):
            raise ValueError("peak_us must lie within [start_us, end_us]")
        if self.level is EvidenceLevel.SPECULATION:
            raise ValueError("SPECULATION-level events are not permitted in this version")
        return self

    @property
    def duration_us(self) -> int:
        return self.end_us - self.start_us
