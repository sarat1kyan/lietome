"""Exception hierarchy. Every Lightman-raised error derives from :class:`LightmanError`."""

from __future__ import annotations


class LightmanError(Exception):
    """Base class for all Lightman errors."""


class ConfigError(LightmanError):
    """Invalid or unreadable configuration."""


class MediaError(LightmanError):
    """Media file cannot be probed or decoded."""


class UnsupportedMediaError(MediaError):
    """Media is valid but has no stream Lightman can analyze (e.g. audio-only in video mode)."""


class SecurityLimitError(LightmanError):
    """Input exceeded a configured safety limit (size, duration, resolution, frame count)."""


class ModelError(LightmanError):
    """Model asset missing, corrupt, or failed integrity verification."""


class ModelIntegrityError(ModelError):
    """Downloaded/cached model does not match the manifest SHA-256."""


class PipelineError(LightmanError):
    """A pipeline stage failed in a way that invalidates the session output."""
