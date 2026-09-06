"""Columnar per-frame feature table (Arrow/Parquet).

One row per analyzed frame. Frames without a face keep their timestamp row with NaN signal
values so gaps are explicit and coverage can be computed. Landmarks are *not* stored here by
default (478x3 per frame is large and biometric); see StorageConfig.store_landmarks.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq

from lightman.features.action_units import OPENGRAPHAU_NAMES
from lightman.features.blendshapes import BLENDSHAPE_NAMES

HEAD_COLUMNS: tuple[str, ...] = (
    "head.yaw_deg",
    "head.pitch_deg",
    "head.roll_deg",
    "head.tx",
    "head.ty",
    "head.tz",
)
EYE_COLUMNS: tuple[str, ...] = (
    "eye.aspect_ratio_right",
    "eye.aspect_ratio_left",
    "eye.aspect_ratio_mean",
)
BLENDSHAPE_COLUMNS: tuple[str, ...] = tuple(f"blendshape.{n}" for n in BLENDSHAPE_NAMES)
AU_COLUMNS: tuple[str, ...] = tuple(f"au.{n}" for n in OPENGRAPHAU_NAMES)
META_COLUMNS: tuple[str, ...] = (
    "frame_index",
    "source_index",
    "t_us",
    "timestamp_estimated",
    "face_present",
    "face_count",
    "quality",
    "face.bbox_x0",
    "face.bbox_y0",
    "face.bbox_x1",
    "face.bbox_y1",
    "face.width_px",
    "speaking",
)
SIGNAL_COLUMNS: tuple[str, ...] = HEAD_COLUMNS + EYE_COLUMNS + BLENDSHAPE_COLUMNS + AU_COLUMNS
FEATURE_COLUMNS: tuple[str, ...] = META_COLUMNS + SIGNAL_COLUMNS


def signal_unit(name: str) -> str:
    """Physical unit for a signal column (used in events and reports)."""
    if name.endswith("_deg"):
        return "deg"
    if name.startswith("head.t"):
        return "model_units"
    if name.startswith("eye.aspect_ratio"):
        return "ratio"
    if name.startswith("blendshape."):
        return "coefficient"
    if name.startswith("au."):
        return "probability"
    if name == "voice.f0_hz":
        return "hz"
    if name == "voice.energy_db":
        return "db"
    if name.startswith("voice.") and name.endswith("_prob"):
        return "probability"
    return "unitless"


@dataclass(slots=True)
class FeatureTableBuilder:
    _cols: dict[str, list[float | int | bool]] = field(
        default_factory=lambda: {c: [] for c in FEATURE_COLUMNS}
    )

    def add_frame(
        self,
        *,
        frame_index: int,
        source_index: int,
        t_us: int,
        timestamp_estimated: bool,
        face_count: int,
        quality: float,
        bbox: tuple[float, float, float, float] | None,
        face_width_px: float,
        head: Sequence[float] | None,
        eyes: Sequence[float] | None,
        blendshapes: dict[str, float] | None,
        aus: Sequence[float] | npt.NDArray[np.floating] | None = None,
        speaking: bool = False,
    ) -> None:
        c = self._cols
        c["frame_index"].append(frame_index)
        c["source_index"].append(source_index)
        c["t_us"].append(t_us)
        c["timestamp_estimated"].append(timestamp_estimated)
        c["face_present"].append(face_count > 0)
        c["face_count"].append(face_count)
        c["quality"].append(quality)
        x0, y0, x1, y1 = bbox if bbox else (math.nan,) * 4
        c["face.bbox_x0"].append(x0)
        c["face.bbox_y0"].append(y0)
        c["face.bbox_x1"].append(x1)
        c["face.bbox_y1"].append(y1)
        c["face.width_px"].append(face_width_px)
        c["speaking"].append(speaking)
        hv = list(head) if head is not None else [math.nan] * len(HEAD_COLUMNS)
        for name, v in zip(HEAD_COLUMNS, hv, strict=True):
            c[name].append(v)
        ev = list(eyes) if eyes is not None else [math.nan] * len(EYE_COLUMNS)
        for name, v in zip(EYE_COLUMNS, ev, strict=True):
            c[name].append(v)
        for bs_name, col in zip(BLENDSHAPE_NAMES, BLENDSHAPE_COLUMNS, strict=True):
            c[col].append(blendshapes.get(bs_name, math.nan) if blendshapes else math.nan)
        av = list(aus) if aus is not None else [math.nan] * len(AU_COLUMNS)
        for name, v in zip(AU_COLUMNS, av, strict=True):
            c[name].append(v)

    def set_column(self, name: str, values: Sequence[bool] | npt.NDArray[np.bool_]) -> None:
        if name not in self._cols or len(values) != len(self):
            raise ValueError(f"cannot set column {name}")
        self._cols[name] = [bool(v) for v in values]

    def __len__(self) -> int:
        return len(self._cols["t_us"])

    def to_numpy(self) -> dict[str, npt.NDArray[np.generic]]:
        out: dict[str, npt.NDArray[np.generic]] = {}
        for name, values in self._cols.items():
            if name in ("frame_index", "source_index", "face_count"):
                out[name] = np.asarray(values, dtype=np.int32)
            elif name == "t_us":
                out[name] = np.asarray(values, dtype=np.int64)
            elif name in ("timestamp_estimated", "face_present", "speaking"):
                out[name] = np.asarray(values, dtype=np.bool_)
            else:
                out[name] = np.asarray(values, dtype=np.float32)
        return out

    def to_arrow(self) -> pa.Table:
        arrays = self.to_numpy()
        return pa.table({name: pa.array(arrays[name]) for name in FEATURE_COLUMNS})

    def write_parquet(self, path: Path) -> None:
        pq.write_table(self.to_arrow(), path, compression="zstd")


def read_feature_table(path: Path) -> dict[str, npt.NDArray[np.generic]]:
    table = pq.read_table(path)
    return {name: table.column(name).to_numpy() for name in table.column_names}
