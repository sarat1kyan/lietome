"""Practitioner notes for a session, optionally pinned to a moment of the timeline."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Note(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: secrets.token_hex(4))
    t_us: int | None = Field(default=None, ge=0, description="Pinned moment, or None")
    text: str = Field(min_length=1, max_length=4000)
    created_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    updated_utc: str = ""


def read_notes(session_dir: Path) -> list[Note]:
    p = session_dir / "notes.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [Note.model_validate(n) for n in data.get("notes", [])]


def write_notes(session_dir: Path, notes: list[Note]) -> None:
    ordered = sorted(notes, key=lambda n: (n.t_us is None, n.t_us or 0, n.created_utc))
    (session_dir / "notes.json").write_text(
        json.dumps({"notes": [n.model_dump() for n in ordered]}, indent=1)
    )


def upsert(session_dir: Path, note_id: str | None, text: str, t_us: int | None) -> Note:
    notes = read_notes(session_dir)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    if note_id:
        for i, n in enumerate(notes):
            if n.id == note_id:
                notes[i] = n.model_copy(update={"text": text, "t_us": t_us, "updated_utc": now})
                write_notes(session_dir, notes)
                return notes[i]
        raise KeyError(note_id)
    note = Note(text=text, t_us=t_us)
    write_notes(session_dir, [*notes, note])
    return note


def delete(session_dir: Path, note_id: str) -> bool:
    notes = read_notes(session_dir)
    kept = [n for n in notes if n.id != note_id]
    if len(kept) == len(notes):
        return False
    write_notes(session_dir, kept)
    return True


def notes_payload(session_dir: Path) -> dict[str, Any]:
    return {"notes": [n.model_dump() for n in read_notes(session_dir)]}
