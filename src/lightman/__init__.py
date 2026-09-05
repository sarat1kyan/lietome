"""Lightman: open-source multimodal behavioral-analysis platform.

Lightman measures observable behavior (facial motion, head pose, blinks, and in later
phases voice and speech timing) and compares it against a subject-specific baseline.
It reports *deviations* with provenance and confidence. It does not, and must not,
claim to detect lies.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lightman")
except PackageNotFoundError:  # pragma: no cover - running from a source checkout
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
