"""Validated data models shared by every pipeline stage.

The epistemic ladder (docs/scientific-limitations.md) is encoded in :class:`EvidenceLevel`
and must never be collapsed: an OBSERVATION is a measurement; an INTERPRETATION names a
movement; an INFERENCE proposes a behavioral state; SPECULATION is anything about intent.
"""

from lightman.schema.events import Event, EvidenceLevel, FeatureContribution
from lightman.schema.media import AudioStreamInfo, MediaInfo, VideoStreamInfo
from lightman.schema.provenance import EnvironmentSnapshot, Provenance
from lightman.schema.session import AnalysisManifest, OutputArtifact, QualitySummary

__all__ = [
    "AnalysisManifest",
    "AudioStreamInfo",
    "EnvironmentSnapshot",
    "Event",
    "EvidenceLevel",
    "FeatureContribution",
    "MediaInfo",
    "OutputArtifact",
    "Provenance",
    "QualitySummary",
    "VideoStreamInfo",
]
