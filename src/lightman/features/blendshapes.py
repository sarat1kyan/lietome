"""MediaPipe/ARKit-style blendshape coefficient names and their *proxy* relation to FACS.

IMPORTANT: blendshapes are rig-animation coefficients predicted by a regression model. They
are correlated with, but are NOT, FACS Action Units. The mapping below is a semantic
correspondence used only for human-readable hints in reports. It has not been validated
against FACS-coded ground truth inside Lightman, and every label derived from it must be
suffixed "(proxy)". A real AU detector is planned as a separate backend (see roadmap).
"""

from __future__ import annotations

BLENDSHAPE_NAMES: tuple[str, ...] = (
    "_neutral",
    "browDownLeft",
    "browDownRight",
    "browInnerUp",
    "browOuterUpLeft",
    "browOuterUpRight",
    "cheekPuff",
    "cheekSquintLeft",
    "cheekSquintRight",
    "eyeBlinkLeft",
    "eyeBlinkRight",
    "eyeLookDownLeft",
    "eyeLookDownRight",
    "eyeLookInLeft",
    "eyeLookInRight",
    "eyeLookOutLeft",
    "eyeLookOutRight",
    "eyeLookUpLeft",
    "eyeLookUpRight",
    "eyeSquintLeft",
    "eyeSquintRight",
    "eyeWideLeft",
    "eyeWideRight",
    "jawForward",
    "jawLeft",
    "jawOpen",
    "jawRight",
    "mouthClose",
    "mouthDimpleLeft",
    "mouthDimpleRight",
    "mouthFrownLeft",
    "mouthFrownRight",
    "mouthFunnel",
    "mouthLeft",
    "mouthLowerDownLeft",
    "mouthLowerDownRight",
    "mouthPressLeft",
    "mouthPressRight",
    "mouthPucker",
    "mouthRight",
    "mouthRollLower",
    "mouthRollUpper",
    "mouthShrugLower",
    "mouthShrugUpper",
    "mouthSmileLeft",
    "mouthSmileRight",
    "mouthStretchLeft",
    "mouthStretchRight",
    "mouthUpperUpLeft",
    "mouthUpperUpRight",
    "noseSneerLeft",
    "noseSneerRight",
)
assert len(BLENDSHAPE_NAMES) == 52  # noqa: S101 - structural invariant, not input validation

# Semantic (unvalidated) correspondence to FACS Action Units. Values are hints only.
AU_PROXY_HINTS: dict[str, str] = {
    "browInnerUp": "AU1 inner brow raiser (proxy)",
    "browOuterUpLeft": "AU2 outer brow raiser (proxy)",
    "browOuterUpRight": "AU2 outer brow raiser (proxy)",
    "browDownLeft": "AU4 brow lowerer (proxy)",
    "browDownRight": "AU4 brow lowerer (proxy)",
    "eyeWideLeft": "AU5 upper lid raiser (proxy)",
    "eyeWideRight": "AU5 upper lid raiser (proxy)",
    "cheekSquintLeft": "AU6 cheek raiser (proxy)",
    "cheekSquintRight": "AU6 cheek raiser (proxy)",
    "eyeSquintLeft": "AU7 lid tightener (proxy)",
    "eyeSquintRight": "AU7 lid tightener (proxy)",
    "noseSneerLeft": "AU9 nose wrinkler (proxy)",
    "noseSneerRight": "AU9 nose wrinkler (proxy)",
    "mouthUpperUpLeft": "AU10 upper lip raiser (proxy)",
    "mouthUpperUpRight": "AU10 upper lip raiser (proxy)",
    "mouthSmileLeft": "AU12 lip corner puller (proxy)",
    "mouthSmileRight": "AU12 lip corner puller (proxy)",
    "mouthDimpleLeft": "AU14 dimpler (proxy)",
    "mouthDimpleRight": "AU14 dimpler (proxy)",
    "mouthFrownLeft": "AU15 lip corner depressor (proxy)",
    "mouthFrownRight": "AU15 lip corner depressor (proxy)",
    "mouthShrugLower": "AU17 chin raiser (proxy)",
    "mouthPucker": "AU18 lip pucker (proxy)",
    "mouthStretchLeft": "AU20 lip stretcher (proxy)",
    "mouthStretchRight": "AU20 lip stretcher (proxy)",
    "mouthFunnel": "AU22 lip funneler (proxy)",
    "mouthPressLeft": "AU24 lip pressor (proxy)",
    "mouthPressRight": "AU24 lip pressor (proxy)",
    "jawOpen": "AU26/27 jaw drop / mouth stretch (proxy)",
    "mouthRollLower": "AU28 lip suck (proxy)",
    "mouthRollUpper": "AU28 lip suck (proxy)",
    "eyeBlinkLeft": "AU45 blink (proxy)",
    "eyeBlinkRight": "AU45 blink (proxy)",
}


def au_hint(blendshape: str) -> str | None:
    return AU_PROXY_HINTS.get(blendshape)
