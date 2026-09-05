"""FACS Action Unit vocabulary used by AU detectors (OpenGraphAU ordering).

Kept free of heavy imports so the feature table can import it cheaply.
"""

from __future__ import annotations

OPENGRAPHAU_NAMES: tuple[str, ...] = (
    "AU1", "AU2", "AU4", "AU5", "AU6", "AU7", "AU9", "AU10", "AU11", "AU12", "AU13", "AU14",
    "AU15", "AU16", "AU17", "AU18", "AU19", "AU20", "AU22", "AU23", "AU24", "AU25", "AU26",
    "AU27", "AU32", "AU38", "AU39",
    "AUL1", "AUR1", "AUL2", "AUR2", "AUL4", "AUR4", "AUL6", "AUR6", "AUL10", "AUR10",
    "AUL12", "AUR12", "AUL14", "AUR14",
)  # fmt: skip

AU_DESCRIPTIONS: dict[str, str] = {
    "AU1": "inner brow raiser", "AU2": "outer brow raiser", "AU4": "brow lowerer",
    "AU5": "upper lid raiser", "AU6": "cheek raiser", "AU7": "lid tightener",
    "AU9": "nose wrinkler", "AU10": "upper lip raiser", "AU11": "nasolabial deepener",
    "AU12": "lip corner puller", "AU13": "sharp lip puller", "AU14": "dimpler",
    "AU15": "lip corner depressor", "AU16": "lower lip depressor", "AU17": "chin raiser",
    "AU18": "lip pucker", "AU19": "tongue show", "AU20": "lip stretcher",
    "AU22": "lip funneler", "AU23": "lip tightener", "AU24": "lip pressor",
    "AU25": "lips part", "AU26": "jaw drop", "AU27": "mouth stretch", "AU32": "lip bite",
    "AU38": "nostril dilator", "AU39": "nostril compressor",
}  # fmt: skip


def au_description(name: str) -> str | None:
    base = name.replace("AUL", "AU").replace("AUR", "AU")
    d = AU_DESCRIPTIONS.get(base)
    if d is None:
        return None
    if name.startswith("AUL"):
        return f"left {d}"
    if name.startswith("AUR"):
        return f"right {d}"
    return d
