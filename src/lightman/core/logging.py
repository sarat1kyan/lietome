"""Structured logging via structlog.

Policy (see docs/privacy.md): log *events about processing*, never biometric payloads.
Landmark arrays, embeddings, transcripts, and subject names must not be passed as log
fields. Log counts, durations, ids, versions, and quality summaries instead.
"""

from __future__ import annotations

import logging
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", *, json: bool = False) -> None:
    """Configure structlog once. ``json=True`` emits machine-readable lines."""
    global _CONFIGURED  # noqa: PLW0603 - module-level idempotence guard
    if _CONFIGURED:
        return
    renderer: structlog.types.Processor
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for ``name`` (module path recommended)."""
    return structlog.get_logger(name)  # type: ignore[no-any-return]
