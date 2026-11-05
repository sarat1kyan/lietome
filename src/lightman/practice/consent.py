"""Consent records.

A practitioner confirms, before any analysis starts, that the person in front of the camera
agreed to what is about to happen. The record is stored with the session (consent.json) and
gates the optional parts: video recording and transcription only run when they are in scope.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Scope = Literal["video_analysis", "audio_analysis", "recording", "transcription"]


class ConsentRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    given_by: Literal["client", "guardian", "self"] = Field(
        description="Who agreed: the client, a legal guardian, or the user analysing themselves"
    )
    method: Literal["verbal", "written", "electronic"] = "verbal"
    scope: list[Scope] = Field(min_length=1)
    confirmed_by: str = Field(default="", max_length=64, description="Practitioner initials")
    note: str = Field(default="", max_length=500)
    at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def allows(self, scope: Scope) -> bool:
        return scope in self.scope


CLI_CONSENT_NOTE = "analysis started from the command line; consent was not recorded in Lightman"
