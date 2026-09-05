"""Time representation.

Design (see ADR-004):

* **Media time** is stored as ``int`` microseconds (``t_us``) relative to the start of the
  analyzed stream. Integers avoid floating-point drift/equality problems in long recordings
  and survive JSON round-trips exactly. Microseconds are finer than any camera frame period
  (1 us << 1/240 s) and than audio sample periods at 48 kHz (~20.8 us), so alignment of
  audio and video events never loses information.
* **Wall-clock time** (when the analysis ran, or when a live frame was captured) is stored
  separately as timezone-aware ISO-8601 UTC strings. The two are never mixed.

Helpers below are deliberately tiny and pure so they are trivially testable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from fractions import Fraction

US_PER_S = 1_000_000


def s_to_us(seconds: float) -> int:
    """Convert seconds to integer microseconds (round-half-even)."""
    return round(seconds * US_PER_S)


def us_to_s(t_us: int) -> float:
    """Convert integer microseconds to float seconds (for display / plotting only)."""
    return t_us / US_PER_S


def pts_to_us(pts: int, time_base: Fraction) -> int:
    """Convert a container PTS in ``time_base`` units to integer microseconds, exactly."""
    return int(Fraction(pts) * time_base * US_PER_S)


def format_timecode(t_us: int) -> str:
    """Render ``t_us`` as ``HH:MM:SS.mmm`` for human-facing output."""
    total_ms, _ = divmod(t_us, 1000)
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def utc_now_iso() -> str:
    """Current wall-clock time as ISO-8601 UTC with second precision."""
    return datetime.now(UTC).isoformat(timespec="seconds")
