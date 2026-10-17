"""Verbal markers on a transcript and their alignment with face and body events.

Two small English lexicons: hedges (qualifiers that soften a claim) and denials. In the
deception literature verbal cues are also weak (DePaulo et al. 2003); what makes them useful
here is timing: a denial word with a face or body change within a second is a moment an
interviewer would replay. Other languages are transcribed but not marked.
"""

from __future__ import annotations

import re
from typing import Any

HEDGE_PHRASES: tuple[str, ...] = (
    "i think", "i guess", "i believe", "maybe", "probably", "kind of", "sort of", "i suppose",
    "to be honest", "honestly", "to tell the truth", "i don't remember", "i can't remember",
    "i don't recall", "not sure", "as far as i know", "basically", "perhaps", "i mean",
)  # fmt: skip
DENIAL_PHRASES: tuple[str, ...] = (
    "no", "never", "nope", "not", "didn't", "did not", "don't", "do not", "wasn't", "was not",
    "haven't", "have not", "hasn't", "isn't", "nothing", "nobody", "no one", "of course not",
)  # fmt: skip
FACE_TYPES = frozenset(
    {"expression_pattern", "episode", "au_novelty", "gaze_away", "self_touch", "shrug",
     "head_gesture", "baseline_deviation"}
)  # fmt: skip
ALIGN_US = 1_000_000
RIGHT_QUOTE = chr(0x2019)  # typographic apostrophe from the transcriber


def _norm(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower().replace(RIGHT_QUOTE, "'"))


def mark_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return markers {kind, phrase, start_us, end_us, word_index} for hedges and denials."""
    toks = [_norm(w["word"]) for w in words]
    out: list[dict[str, Any]] = []
    for kind, phrases in (("hedge", HEDGE_PHRASES), ("denial", DENIAL_PHRASES)):
        for ph in phrases:
            parts = ph.split()
            n = len(parts)
            out.extend(
                {
                    "kind": kind,
                    "phrase": ph,
                    "start_us": words[i]["start_us"],
                    "end_us": words[i + n - 1]["end_us"],
                    "word_index": i,
                }
                for i in range(len(toks) - n + 1)
                if toks[i : i + n] == parts
            )
    # longer phrases win over their parts ("did not" over "not")
    out.sort(key=lambda m: (m["word_index"], -(m["end_us"] - m["start_us"])))
    kept: list[dict[str, Any]] = []
    covered: set[int] = set()
    for m in out:
        span = set(range(m["word_index"], m["word_index"] + len(m["phrase"].split())))
        if span & covered and m["kind"] == "denial":
            continue
        covered |= span if m["kind"] == "denial" else set()
        kept.append(m)
    return sorted(kept, key=lambda m: m["start_us"])


def align_with_events(
    markers: list[dict[str, Any]], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """For each denial, the face and body events within one second of it."""
    out = []
    for m in markers:
        if m["kind"] != "denial":
            continue
        near = [
            e
            for e in events
            if e["event_type"] in FACE_TYPES
            and e["start_us"] <= m["end_us"] + ALIGN_US
            and e["end_us"] >= m["start_us"] - ALIGN_US
        ]
        if not near:
            continue
        near.sort(key=lambda e: -e["severity"])
        out.append(
            {
                "phrase": m["phrase"],
                "start_us": m["start_us"],
                "end_us": m["end_us"],
                "events": [
                    {"event_id": e["event_id"], "event_type": e["event_type"], "label": e["label"]}
                    for e in near[:4]
                ],
            }
        )
    return out


def answers_text(
    words: list[dict[str, Any]], questions: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Per question id: answer text, word count, words per minute, hedges and denials."""
    out: dict[str, dict[str, Any]] = {}
    for q in questions:
        a, b = q["start_us"], q["end_us"]
        ws = [w for w in words if a <= w["start_us"] < b]
        if not ws:
            out[q["id"]] = {"text": "", "words": 0, "wpm": None, "hedges": 0, "denials": 0}
            continue
        marks = mark_words(ws)
        dur_min = max(1e-6, (ws[-1]["end_us"] - ws[0]["start_us"]) / 60e6)
        out[q["id"]] = {
            "text": " ".join(w["word"] for w in ws),
            "words": len(ws),
            "wpm": round(len(ws) / dur_min, 1),
            "hedges": sum(1 for m in marks if m["kind"] == "hedge"),
            "denials": sum(1 for m in marks if m["kind"] == "denial"),
        }
    return out


def annotate(
    transcript: dict[str, Any],
    events: list[dict[str, Any]],
    questions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Transcript plus markers, denial-event alignments and per-answer text."""
    words = transcript.get("words", [])
    english = (transcript.get("language") or "en") == "en"
    markers = mark_words(words) if english else []
    return {
        **transcript,
        "markers": markers,
        "denial_moments": align_with_events(markers, events) if english else [],
        "answers": answers_text(words, questions or []),
        "marking": "english lexicon" if english else "not marked: lexicons are English only",
    }
