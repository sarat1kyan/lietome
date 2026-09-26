import json
from pathlib import Path

from fastapi.testclient import TestClient

from lightman.api.app import create_app
from lightman.api.subject import clean_state
from lightman.protocol.summary import auroc_ci


def test_clean_state_keeps_known_bounded_fields() -> None:
    s = clean_state(
        {
            "status": "question",
            "question": {"id": "q3", "text": "Did you?", "number": 3, "secret": "x"},
            "card": "LIE on this answer",
            "remaining_s": 4,
            "numbers": [1, 2],
            "instruction": "x" * 5000,
        }
    )
    assert s["status"] == "question" and s["card"].startswith("LIE")
    assert s["question"] == {"id": "q3", "text": "Did you?", "number": "3"}
    assert "numbers" not in s and len(s["instruction"]) == 1200
    assert clean_state("nope") == {}


def test_subject_screen_receives_operator_state(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    with client.websocket_connect("/api/subject") as sub:
        first = json.loads(sub.receive_text())
        assert first == {"type": "subject", "status": "idle"}
        with client.websocket_connect("/api/live") as op:
            op.send_text(
                json.dumps(
                    {"type": "subject", "state": {"status": "question", "question": {"text": "Q?"}}}
                )
            )
            got = json.loads(sub.receive_text())
            assert got["status"] == "question" and got["question"]["text"] == "Q?"
            ack = json.loads(op.receive_text())
            assert ack == {"type": "subject_screens", "n": 1}
    # a screen that connects later gets the latest state
    with client.websocket_connect("/api/subject") as late:
        assert json.loads(late.receive_text())["status"] == "question"


def test_auroc_ci_separates_and_brackets_chance() -> None:
    perfect = auroc_ci([70.0, 75, 80, 72, 50, 48, 52, 49], [1, 1, 1, 1, 0, 0, 0, 0])
    assert perfect["auroc"] == 1.0 and perfect["ci95"] is not None and perfect["ci95"][0] >= 0.75
    noise = auroc_ci([50.0, 52, 48, 51, 50, 49, 53, 47], [1, 0, 1, 0, 1, 0, 1, 0])
    assert noise["ci95"] is not None and noise["ci95"][0] < 0.5 < noise["ci95"][1]
    assert auroc_ci([1.0], [1])["auroc"] is None


def test_subject_validation_pools_labelled_answers(tmp_path: Path) -> None:
    for k, (sid, lies) in enumerate(
        [("20260101T000000Z-aaaaaa", [80.0, 75.0]), ("20260102T000000Z-bbbbbb", [70.0, 78.0])]
    ):
        d = tmp_path / sid
        d.mkdir()
        (d / "manifest.json").write_text(
            json.dumps({"subject_ids": ["anna"], "created_utc": f"2026-01-0{k + 1}T00:00:00"})
        )
        (d / "analysis.json").write_text(json.dumps({"mode": "live", "duration_us": 1}))
        qs = [
            {"id": f"q{i}", "category": "relevant", "expected": "lie", "score": 5.0,
             "cue_index": {"value": v}, "control_index": {"value": v}}
            for i, v in enumerate(lies)
        ] + [
            {"id": f"t{i}", "category": "relevant", "expected": "truth", "score": 5.0,
             "cue_index": {"value": v}, "control_index": {"value": v}}
            for i, v in enumerate([50.0, 55.0])
        ]  # fmt: skip
        (d / "protocol.json").write_text(json.dumps({"questions": qs}))
    client = TestClient(create_app(tmp_path))
    v = client.get("/api/subjects/anna/validation").json()
    assert v["n_items"] == 8 and len(v["sessions"]) == 2
    assert v["by_score"]["control_index"]["auroc"] == 1.0
    assert client.get("/api/subjects/..%2Fx/validation").status_code in (404, 422)
