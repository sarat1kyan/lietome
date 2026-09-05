"""End-to-end pipeline test with a deterministic fake landmarker (no model download)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
import pytest

from lightman import __version__
from lightman.config import BaselineConfig, EventsConfig, LightmanConfig, ModelsConfig
from lightman.face.base import FaceObservation
from lightman.features.blendshapes import BLENDSHAPE_NAMES
from lightman.features.eyes import LEFT_EYE_EAR, RIGHT_EYE_EAR
from lightman.features.head_pose import rotation_matrix
from lightman.pipeline import analyze_video
from lightman.schema import AnalysisManifest, Provenance
from tests.conftest import noise_frames, write_video


class FakeLandmarker:
    """Synthesizes a face whose brow blendshape spikes at frames 60-70 and blinks at 40-43.
    Frames 0-2 carry a large jawOpen spike to emulate tracker warm-up jitter."""

    def __init__(self) -> None:
        self.calls = 0
        self.closed = False

    @property
    def provenance(self) -> Provenance:
        return Provenance(
            extractor_id="face.fake",
            extractor_version="0",
            runtime="test",
            lightman_version=__version__,
        )

    @property
    def blendshape_names(self) -> list[str]:
        return list(BLENDSHAPE_NAMES)

    def process(self, rgb: np.ndarray, t_us: int) -> list[FaceObservation]:
        i = self.calls
        self.calls += 1
        if 20 <= i < 25:
            return []  # face briefly lost
        lm = np.zeros((478, 3), dtype=np.float32)
        lm[:, 0] = np.linspace(0.3, 0.7, 478)
        lm[:, 1] = np.linspace(0.2, 0.8, 478)
        openness = 0.0 if 40 <= i < 44 else 0.03
        for idx in (RIGHT_EYE_EAR, LEFT_EYE_EAR):
            outer, up1, up2, inner, low2, low1 = idx
            lm[outer] = (0.30, 0.50, 0)
            lm[inner] = (0.40, 0.50, 0)
            lm[up1] = lm[up2] = (0.35, 0.50 - openness / 2, 0)
            lm[low1] = lm[low2] = (0.35, 0.50 + openness / 2, 0)
        rng = np.random.default_rng(i)
        shapes = {n: float(abs(rng.normal(0.05, 0.01))) for n in BLENDSHAPE_NAMES}
        if 60 <= i < 70:
            shapes["browDownLeft"] = 0.8
            shapes["browDownRight"] = 0.8
        if i < 3:
            shapes["jawOpen"] = 0.9  # warm-up artifact, must be filtered by warmup_ms
        m = np.eye(4, dtype=np.float32)
        m[:3, :3] = rotation_matrix(5.0 + rng.normal(0, 0.3), -2.0, 1.0)
        m[:3, 3] = (0, 0, -40)
        return [FaceObservation(landmarks=lm, blendshapes=shapes, transform=m)]

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def cfg() -> LightmanConfig:
    return LightmanConfig(
        baseline=BaselineConfig(window_s=1.0, min_samples=10, good_samples=30),
        events=EventsConfig(),
        models=ModelsConfig(allow_download=False),
    )


def test_pipeline_end_to_end_with_fake_backend(tmp_path: Path, cfg: LightmanConfig) -> None:
    video = write_video(tmp_path / "v.mp4", noise_frames(90, w=160, h=120), fps=30)
    fake = FakeLandmarker()
    result = analyze_video(video, tmp_path / "out", cfg, landmarker_factory=lambda _c, _r: fake)
    assert fake.closed and fake.calls == 90
    d = result.session_dir
    for name in (
        "metadata.json",
        "features.parquet",
        "baseline.json",
        "events.json",
        "analysis.json",
        "report.html",
        "manifest.json",
    ):
        assert (d / name).is_file(), name

    manifest = AnalysisManifest.model_validate_json((d / "manifest.json").read_text())
    assert manifest.quality.frames_decoded == 90
    assert manifest.quality.frames_with_face == 85
    assert manifest.provenance[0].extractor_id == "face.fake"
    assert "not" in manifest.disclaimer.lower() and "lie" in manifest.disclaimer.lower()
    # every artifact hash in the manifest matches the file on disk
    from lightman.media import sha256_file

    for art in manifest.outputs:
        assert sha256_file(d / art.name) == art.sha256

    table = pq.read_table(d / "features.parquet")
    assert table.num_rows == 90
    assert "blendshape.browDownLeft" in table.column_names
    assert not table.column("face_present").to_numpy()[22]

    events = json.loads((d / "events.json").read_text())["events"]
    types = {e["event_type"] for e in events}
    assert "blink" in types
    assert "baseline_deviation" in types
    assert "multi_signal_deviation" in types  # both brows deviate together
    brow = [
        e
        for e in events
        if e["event_type"] == "baseline_deviation"
        and e["contributions"][0]["feature"] == "blendshape.browDownLeft"
    ]
    assert len(brow) == 1
    assert abs(brow[0]["start_us"] - 2_000_000) < 40_000
    assert all(e["level"] != "speculation" for e in events)
    assert all(e["start_us"] >= 300_000 for e in events)  # warm-up filtered
    assert not any(c["feature"] == "blendshape.jawOpen" for e in events for c in e["contributions"])

    # privacy: no absolute source path persisted anywhere in JSON outputs
    for name in ("metadata.json", "manifest.json", "analysis.json"):
        assert str(tmp_path) not in (d / name).read_text()

    html = (d / "report.html").read_text()
    assert "does not detect lies" in html
    assert "<svg" in html and "browDownLeft" in html


def test_pipeline_no_face_at_all(tmp_path: Path, cfg: LightmanConfig) -> None:
    class NoFace(FakeLandmarker):
        def process(self, rgb, t_us):  # type: ignore[override]
            self.calls += 1
            return []

    video = write_video(tmp_path / "v.mp4", noise_frames(30, w=160, h=120), fps=30)
    result = analyze_video(video, tmp_path / "out", cfg, landmarker_factory=lambda _c, _r: NoFace())
    assert result.manifest.quality.face_coverage == 0.0
    assert result.events == []
    assert any("face visible" in n for n in result.manifest.quality.notes)
    assert result.baseline.quality == 0.0
