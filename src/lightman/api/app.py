"""FastAPI application: session browsing, feature/event data, upload-and-analyze, static UI.

Security posture: session/event ids are pattern-validated; uploads are size-capped and written
to a temp file under the output root; analysis runs in a worker thread; the original file is
retained inside the session directory only when the caller asks (``keep_media``), otherwise it
is deleted after analysis. No absolute paths are returned.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import uuid
from importlib import resources
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from lightman import __version__
from lightman.api.live_ws import AUFactory, LandmarkerFactory, live_endpoint
from lightman.api.sessions import SessionNotFoundError, SessionStore
from lightman.config import LightmanConfig
from lightman.core.errors import LightmanError
from lightman.core.logging import get_logger
from lightman.models import ModelRegistry

log = get_logger(__name__)

MAX_FEATURE_POINTS = 4000


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create(self) -> str:
        jid = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[jid] = {"job_id": jid, "state": "queued", "session_id": None, "error": None}
        return jid

    def update(self, jid: str, **fields: Any) -> None:
        with self._lock:
            self._jobs[jid].update(fields)

    def get(self, jid: str) -> dict[str, Any] | None:
        with self._lock:
            j = self._jobs.get(jid)
            return dict(j) if j else None


def create_app(
    output_root: Path,
    cfg: LightmanConfig | None = None,
    *,
    landmarker_factory: LandmarkerFactory | None = None,
    au_factory: AUFactory | None = None,
) -> FastAPI:
    cfg = cfg or LightmanConfig()
    store = SessionStore(output_root)
    registry = ModelRegistry(
        cache_dir=cfg.models.cache_dir, allow_download=cfg.models.allow_download
    )
    from lightman.pipeline.analyze import default_au_factory, default_landmarker_factory

    lm_factory = landmarker_factory or default_landmarker_factory
    au_fact = au_factory or default_au_factory
    jobs = JobRegistry()
    app = FastAPI(title="Lightman", version=__version__, docs_url="/api/docs", redoc_url=None)

    @app.exception_handler(SessionNotFoundError)
    async def _nf(_req: Any, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        return store.list_sessions()

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        return {
            "manifest": store.read_json(session_id, "manifest.json"),
            "analysis": store.read_json(session_id, "analysis.json"),
            "baseline": store.read_json(session_id, "baseline.json"),
            "audio_baseline": store.read_json(session_id, "audio_baseline.json"),
            "segments": store.read_json(session_id, "speech_segments.json"),
        }

    @app.get("/api/sessions/{session_id}/events")
    def get_events(session_id: str) -> Any:
        return store.read_json(session_id, "events.json") or {"schema_version": 1, "events": []}

    @app.get("/api/sessions/{session_id}/features")
    def get_features(
        session_id: str,
        table: Annotated[str, Query(pattern="^(video|audio)$")] = "video",
        signals: Annotated[str, Query(max_length=4000)] = "",
        max_points: Annotated[int, Query(ge=10, le=MAX_FEATURE_POINTS)] = 2000,
    ) -> dict[str, Any]:
        wanted = [s for s in signals.split(",") if s]
        return store.features(session_id, table=table, signals=wanted, max_points=max_points)

    @app.get("/api/sessions/{session_id}/thumbnails/{event_id}")
    def get_thumbnail(session_id: str, event_id: str) -> FileResponse:
        p = store.thumbnail(session_id, event_id)
        return FileResponse(p, media_type="image/jpeg" if p.suffix == ".jpg" else "image/png")

    @app.get("/api/sessions/{session_id}/media")
    def get_media(session_id: str) -> FileResponse:
        return FileResponse(store.media(session_id), media_type="video/mp4")

    @app.post("/api/analyze", status_code=202)
    def analyze(
        file: Annotated[UploadFile, File()],
        keep_media: Annotated[bool, Form()] = False,
        target_fps: Annotated[float | None, Form()] = None,
        au: Annotated[bool, Form()] = True,
    ) -> dict[str, Any]:
        output_root.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix=".upload-", dir=output_root))
        dest = tmp_dir / "upload.bin"
        limit = cfg.limits.max_file_bytes
        received = 0
        with dest.open("wb") as fh:
            while chunk := file.file.read(4 * 1024 * 1024):
                received += len(chunk)
                if received > limit:
                    fh.close()
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    raise HTTPException(
                        status_code=413, detail="file exceeds configured size limit"
                    )
                fh.write(chunk)
        if received == 0:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="empty upload")
        run_cfg = cfg
        updates: dict[str, Any] = {}
        if target_fps:
            updates["video"] = cfg.video.model_copy(update={"target_fps": target_fps})
        if not au:
            updates["au"] = cfg.au.model_copy(update={"enabled": False})
        if updates:
            run_cfg = cfg.model_copy(update=updates)
        jid = jobs.create()

        def work() -> None:
            from lightman.pipeline import analyze_video

            jobs.update(jid, state="running")
            try:
                result = analyze_video(dest, output_root, run_cfg)
                if keep_media:
                    shutil.move(str(dest), result.session_dir / "media.mp4")
                jobs.update(jid, state="done", session_id=result.session_id)
            except LightmanError as exc:
                jobs.update(jid, state="failed", error=str(exc))
            except Exception as exc:
                log.exception("analyze_job_crashed")
                jobs.update(jid, state="failed", error=f"internal error: {type(exc).__name__}")
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)

        threading.Thread(target=work, name=f"analyze-{jid}", daemon=True).start()
        return {"job_id": jid, "state": "queued"}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        j = jobs.get(job_id)
        if j is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return j

    @app.websocket("/api/live")
    async def live(ws: WebSocket) -> None:
        await live_endpoint(
            ws,
            cfg=cfg,
            registry=registry,
            output_root=output_root,
            landmarker_factory=lm_factory,
            au_factory=au_fact,
        )

    static_dir = Path(str(resources.files("lightman.api").joinpath("static")))
    if (static_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    else:

        @app.get("/")
        def no_ui() -> JSONResponse:
            return JSONResponse(
                {
                    "detail": "UI not built. Run `npm install && npm run build` in frontend/ "
                    "(outputs to src/lightman/api/static). API docs at /api/docs."
                }
            )

    return app
