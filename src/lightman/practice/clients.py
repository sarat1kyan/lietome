"""Client registry: pseudonymous codes that group sessions, with export and erasure.

A client is identified by a short code chosen by the practitioner (for example "C-014").
The code is what sessions store as their subject id. An optional label (a first name, a case
number) stays on this machine in `<output root>/_clients/<code>.json`; use codes, not names,
whenever a session or report may leave the machine.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
SESSION_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$")


class ClientError(ValueError):
    pass


class Client(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str = Field(pattern=CODE_RE.pattern)
    label: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=2000)
    created_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    updated_utc: str = ""


class ClientStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.dir = root / "_clients"

    def _path(self, code: str) -> Path:
        if not CODE_RE.match(code):
            raise ClientError("invalid client code")
        return self.dir / f"{code}.json"

    def _sessions_of(self, code: str) -> list[Path]:
        out: list[Path] = []
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            if not (SESSION_RE.match(d.name) and (d / "manifest.json").is_file()):
                continue
            try:
                m = json.loads((d / "manifest.json").read_text("utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (m.get("subject_ids") or [None])[0] == code:
                out.append(d)
        return out

    def session_dirs(self, code: str) -> list[Path]:
        self._path(code)
        return self._sessions_of(code)

    def get(self, code: str) -> Client | None:
        p = self._path(code)
        if not p.is_file():
            return None
        return Client.model_validate_json(p.read_text("utf-8"))

    def save(self, client: Client) -> Client:
        p = self._path(client.code)
        p.parent.mkdir(parents=True, exist_ok=True)
        c = client.model_copy(
            update={"updated_utc": datetime.now(UTC).isoformat(timespec="seconds")}
        )
        p.write_text(c.model_dump_json(indent=1))
        return c

    def list(self) -> list[dict[str, Any]]:
        """Registered clients plus codes that only appear in sessions (older data)."""
        codes: dict[str, Client] = {}
        if self.dir.is_dir():
            for p in self.dir.glob("*.json"):
                try:
                    c = Client.model_validate_json(p.read_text("utf-8"))
                except ValueError:
                    continue
                codes[c.code] = c
        counts: dict[str, list[str]] = {}
        if self.root.is_dir():
            for d in self.root.iterdir():
                if not (SESSION_RE.match(d.name) and (d / "manifest.json").is_file()):
                    continue
                try:
                    m = json.loads((d / "manifest.json").read_text("utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                code = (m.get("subject_ids") or [None])[0]
                if code:
                    counts.setdefault(code, []).append(d.name)
        out = []
        for code in sorted(set(codes) | set(counts)):
            entry: Client | None = codes.get(code)
            sess = sorted(counts.get(code, []))
            out.append(
                {
                    "code": code,
                    "label": entry.label if entry else "",
                    "note": entry.note if entry else "",
                    "registered": entry is not None,
                    "created_utc": entry.created_utc if entry else None,
                    "sessions": len(sess),
                    "last_session": sess[-1] if sess else None,
                }
            )
        return out

    def export_zip(self, code: str) -> bytes:
        """Everything Lightman holds about a client, as a zip archive."""
        self._path(code)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            p = self._path(code)
            if p.is_file():
                z.write(p, f"{code}/client.json")
            norms = self.root / "_subjects" / f"{code}.json"
            if norms.is_file():
                z.write(norms, f"{code}/norms.json")
            for d in self._sessions_of(code):
                for f in d.rglob("*"):
                    if f.is_file():
                        z.write(f, f"{code}/sessions/{d.name}/{f.relative_to(d)}")
            z.writestr(
                f"{code}/README.txt",
                "Lightman export. client.json: registry entry; norms.json: baseline norms across "
                "sessions; sessions/: one folder per session (features, events, notes, consent, "
                "reports). Contains measurements of a person; store and share accordingly.\n",
            )
        return buf.getvalue()

    def erase(self, code: str) -> dict[str, Any]:
        """Delete the client entry, their norms and every session recorded under the code."""
        p = self._path(code)
        removed = []
        for d in self._sessions_of(code):
            shutil.rmtree(d)
            removed.append(d.name)
        norms = self.root / "_subjects" / f"{code}.json"
        had_norms = norms.is_file()
        if had_norms:
            norms.unlink()
        had_entry = p.is_file()
        if had_entry:
            p.unlink()
        return {"code": code, "sessions_removed": removed, "norms": had_norms, "entry": had_entry}
