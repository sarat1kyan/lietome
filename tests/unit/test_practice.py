import json
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lightman.api.app import create_app
from lightman.practice.clients import Client, ClientError, ClientStore
from lightman.practice.consent import ConsentRecord
from lightman.practice.notes import delete, read_notes, upsert


def _session(root: Path, sid: str, code: str) -> Path:
    d = root / sid
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"subject_ids": [code]}))
    (d / "analysis.json").write_text(json.dumps({"mode": "live"}))
    (d / "events.json").write_text(json.dumps({"events": []}))
    return d


def test_consent_record_scope() -> None:
    c = ConsentRecord(given_by="client", scope=["video_analysis", "recording"])
    assert c.allows("recording") and not c.allows("transcription")
    assert c.at_utc.endswith("+00:00")
    with pytest.raises(ValueError):
        ConsentRecord(given_by="client", scope=[])
    with pytest.raises(ValueError):
        ConsentRecord.model_validate({"given_by": "client", "scope": ["mind_reading"]})


def test_client_store_lists_exports_and_erases(tmp_path: Path) -> None:
    store = ClientStore(tmp_path)
    store.save(Client(code="C-014", label="first visit", note="referral"))
    _session(tmp_path, "20260101T000000Z-aaaaaa", "C-014")
    _session(tmp_path, "20260102T000000Z-bbbbbb", "C-014")
    _session(tmp_path, "20260103T000000Z-cccccc", "other")
    (tmp_path / "_subjects").mkdir()
    (tmp_path / "_subjects" / "C-014.json").write_text("{}")
    rows = {r["code"]: r for r in store.list()}
    assert rows["C-014"]["sessions"] == 2 and rows["C-014"]["registered"]
    assert rows["other"]["sessions"] == 1 and not rows["other"]["registered"]
    names = zipfile.ZipFile(BytesIO(store.export_zip("C-014"))).namelist()
    assert "C-014/client.json" in names and "C-014/norms.json" in names
    assert any(n.startswith("C-014/sessions/20260101T000000Z-aaaaaa/") for n in names)
    assert not any("cccccc" in n for n in names)
    res = store.erase("C-014")
    assert sorted(res["sessions_removed"]) == ["20260101T000000Z-aaaaaa", "20260102T000000Z-bbbbbb"]
    assert not (tmp_path / "20260101T000000Z-aaaaaa").exists()
    assert (tmp_path / "20260103T000000Z-cccccc").exists()
    assert not (tmp_path / "_subjects" / "C-014.json").exists() and store.get("C-014") is None
    with pytest.raises(ClientError):
        store.erase("../x")


def test_notes_crud(tmp_path: Path) -> None:
    a = upsert(tmp_path, None, "client mentioned work stress", 12_000_000)
    b = upsert(tmp_path, None, "general impression", None)
    upsert(tmp_path, a.id, "client mentioned stress at work", 12_500_000)
    notes = read_notes(tmp_path)
    assert [n.text for n in notes] == ["client mentioned stress at work", "general impression"]
    assert notes[0].updated_utc
    assert delete(tmp_path, b.id) and not delete(tmp_path, "missing")
    with pytest.raises(KeyError):
        upsert(tmp_path, "missing", "x", None)


def test_practice_api(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    s = client.get("/api/settings").json()
    assert s["profile"] == "practice" and s["require_consent"] is True and not s["onboarded"]
    s2 = client.put("/api/settings", json={"profile": "research", "onboarded": True}).json()
    assert s2["profile"] == "research" and s2["onboarded"]
    assert client.put("/api/settings", json={"profile": "nope"}).status_code == 422
    c = client.put("/api/clients/C-1", json={"label": "case 1"}).json()
    assert c["code"] == "C-1" and c["label"] == "case 1"
    assert client.put("/api/clients/bad code", json={}).status_code in (404, 422)
    sid = "20260101T000000Z-dddddd"
    _session(tmp_path, sid, "C-1")
    n = client.post(
        f"/api/sessions/{sid}/notes", json={"text": "pause before answering", "t_us": 5_000_000}
    ).json()
    assert client.get(f"/api/sessions/{sid}/notes").json()["notes"][0]["id"] == n["id"]
    assert (
        client.put(f"/api/sessions/{sid}/notes/{n['id']}", json={"text": "long pause"}).json()[
            "text"
        ]
        == "long pause"
    )
    assert client.delete(f"/api/sessions/{sid}/notes/{n['id']}").status_code == 204
    assert client.get("/api/clients").json()[0]["sessions"] == 1
    z = client.get("/api/clients/C-1/export")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"
    assert client.delete("/api/clients/C-1").status_code == 409  # confirmation missing
    gone = client.delete("/api/clients/C-1", params={"confirm": "C-1"}).json()
    assert gone["sessions_removed"] == [sid] and client.get("/api/clients").json() == []
    r = client.post("/api/analyze", files={"file": ("v.mp4", b"x" * 100)})
    assert r.status_code == 428  # no consent, no analysis


def test_live_refuses_to_start_without_consent(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    with client.websocket_connect("/api/live") as ws:
        ws.send_text(json.dumps({"type": "start", "au": False, "audio": False}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error" and "consent" in msg["detail"]
