import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from lightman.features.head_pose import head_pose_from_matrix, rotation_matrix


def _mat(yaw: float, pitch: float, roll: float, t=(0.1, -0.2, -40.0)) -> np.ndarray:
    m = np.eye(4)
    m[:3, :3] = rotation_matrix(yaw, pitch, roll)
    m[:3, 3] = t
    return m


@settings(max_examples=200)
@given(
    yaw=st.floats(-80, 80),
    pitch=st.floats(-80, 80),
    roll=st.floats(-170, 170),
)
def test_decomposition_round_trip(yaw: float, pitch: float, roll: float) -> None:
    hp = head_pose_from_matrix(_mat(yaw, pitch, roll))
    assert hp.yaw_deg == pytest.approx(yaw, abs=1e-6)
    assert hp.pitch_deg == pytest.approx(pitch, abs=1e-6)
    assert hp.roll_deg == pytest.approx(roll, abs=1e-6)


def test_translation_passthrough() -> None:
    hp = head_pose_from_matrix(_mat(0, 0, 0, t=(1.5, 2.5, -30.0)))
    assert (hp.tx, hp.ty, hp.tz) == (1.5, 2.5, -30.0)


def test_rejects_wrong_shape() -> None:
    with pytest.raises(ValueError, match="4x4"):
        head_pose_from_matrix(np.eye(3))


def test_non_orthonormal_input_is_reorthonormalized() -> None:
    m = _mat(20, -10, 5)
    m[:3, :3] *= 1.02  # scaled rotation (regression noise)
    hp = head_pose_from_matrix(m)
    assert hp.yaw_deg == pytest.approx(20, abs=1e-6)
