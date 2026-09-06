"""Optional OpenCV preview window for live mode: bounding box, a few landmarks, quality and
the most recent events. Clearly labelled as live analysis. Returns False when the user presses
q or Esc."""

from __future__ import annotations

from collections import deque

import numpy as np

from lightman.core.timebase import format_timecode
from lightman.live.analyzer import LiveStats
from lightman.live.sources import LiveFrame
from lightman.schema import Event

WINDOW = "Lightman live analysis"


class Preview:
    def __init__(self, *, max_events: int = 6) -> None:
        import cv2

        self.cv2 = cv2
        self.recent: deque[Event] = deque(maxlen=max_events)
        cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)

    def __call__(
        self, fr: LiveFrame, values: dict[str, float], new_events: list[Event], stats: LiveStats
    ) -> bool:
        cv2 = self.cv2
        for e in new_events:
            self.recent.appendleft(e)
        img = cv2.cvtColor(fr.rgb, cv2.COLOR_RGB2BGR)
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w, 28), (20, 20, 20), -1)
        cv2.putText(
            img,
            "LIVE ANALYSIS  (q to stop)",
            (10, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (90, 200, 255),
            1,
        )
        cv2.putText(
            img,
            format_timecode(fr.t_us),
            (w - 130, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (200, 200, 200),
            1,
        )
        lines = []
        if "head.yaw_deg" in values:
            lines.append(
                f"yaw {values['head.yaw_deg']:+.0f}  pitch {values['head.pitch_deg']:+.0f}  "
                f"roll {values['head.roll_deg']:+.0f}"
            )
        if "eye.aspect_ratio_mean" in values:
            lines.append(f"EAR {values['eye.aspect_ratio_mean']:.2f}")
        aus = sorted(
            ((v, k) for k, v in values.items() if k.startswith("au.") and v > 0.5), reverse=True
        )[:5]
        if aus:
            lines.append("AU " + " ".join(f"{k[3:]}:{v:.2f}" for v, k in aus))
        s = stats.summary()
        lines.append(
            f"{s['analyzed_fps']:.1f} fps  latency p50 {s['latency_ms_p50'] or 0:.0f} ms  "
            f"dropped {s['frames_dropped']}"
        )
        y = 50
        for line in lines:
            cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1)
            y += 20
        y = h - 12
        for e in list(self.recent)[:6]:
            color = (90, 200, 255) if e.event_type != "blink" else (160, 160, 160)
            cv2.putText(
                img,
                f"{format_timecode(e.start_us)} {e.label}",
                (10, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )
            y -= 20
        cv2.imshow(WINDOW, img)
        key = cv2.waitKey(1) & 0xFF
        return key not in (ord("q"), 27)

    def close(self) -> None:
        self.cv2.destroyAllWindows()


def draw_nothing(*_: object) -> bool:
    return True


__all__ = ["Preview", "draw_nothing", "np"]
