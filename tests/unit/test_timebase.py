from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from lightman.core.timebase import format_timecode, pts_to_us, s_to_us, us_to_s


def test_pts_exact_conversion() -> None:
    assert pts_to_us(90000, Fraction(1, 90000)) == 1_000_000
    assert pts_to_us(1, Fraction(1001, 30000)) == 33366  # 29.97 fps, floor to us
    assert pts_to_us(0, Fraction(1, 25)) == 0


@given(st.integers(min_value=0, max_value=10**12))
def test_round_trip_us(t: int) -> None:
    assert s_to_us(us_to_s(t)) == t


def test_format_timecode() -> None:
    assert format_timecode(0) == "00:00:00.000"
    assert format_timecode(12_483_000) == "00:00:12.483"
    assert format_timecode(3_661_000_500) == "01:01:01.000"
