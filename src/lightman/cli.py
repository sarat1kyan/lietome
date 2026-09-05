"""Command-line interface: `lightman analyze|probe|models|doctor|version`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from lightman import __version__
from lightman.config import LightmanConfig
from lightman.core.errors import LightmanError
from lightman.core.logging import configure_logging

app = typer.Typer(
    name="lightman",
    help="Lightman: observable-behavior analysis against subject-specific baselines. "
    "Not a lie detector.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
models_app = typer.Typer(help="Manage model assets (manifest-pinned, SHA-256 verified).")
app.add_typer(models_app, name="models")


def _fail(exc: Exception) -> None:
    typer.secho(f"error: {exc}", err=True, fg=typer.colors.RED)
    raise typer.Exit(code=2)


@app.callback()
def _root(
    log_level: Annotated[str, typer.Option(help="DEBUG, INFO, WARNING, ERROR")] = "INFO",
    log_json: Annotated[bool, typer.Option("--log-json", help="Machine-readable logs")] = False,
) -> None:
    configure_logging(log_level, json=log_json)


@app.command()
def version() -> None:
    """Print the Lightman version."""
    typer.echo(__version__)


@app.command()
def probe(
    media: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Print container/stream metadata as JSON (no decoding)."""
    from lightman.media import probe_media

    try:
        info = probe_media(media)
    except LightmanError as exc:
        _fail(exc)
        return
    typer.echo(json.dumps(info.model_dump(mode="json"), indent=2))


@app.command()
def analyze(
    media: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    out: Annotated[Path, typer.Option("--out", "-o", help="Output root directory")] = Path(
        "output"
    ),
    config: Annotated[
        Path | None, typer.Option("--config", "-c", exists=True, dir_okay=False)
    ] = None,
    fps: Annotated[
        float | None, typer.Option(help="Analyze at most this many frames per second")
    ] = None,
    no_report: Annotated[bool, typer.Option("--no-report", help="Skip report.html")] = False,
    no_thumbnails: Annotated[bool, typer.Option("--no-thumbnails")] = False,
    subject: Annotated[str, typer.Option(help="Anonymous subject id")] = "subject_001",
) -> None:
    """Analyze a prerecorded video and write a session directory of machine-readable results."""
    from lightman.pipeline import analyze_video

    try:
        cfg = LightmanConfig.load(config)
        updates: dict[str, object] = {}
        if fps is not None:
            updates["video"] = cfg.video.model_copy(update={"target_fps": fps})
        storage_updates: dict[str, object] = {}
        if no_report:
            storage_updates["write_report"] = False
        if no_thumbnails:
            storage_updates["event_thumbnails"] = False
        if storage_updates:
            updates["storage"] = cfg.storage.model_copy(update=storage_updates)
        if updates:
            cfg = cfg.model_copy(update=updates)
        result = analyze_video(media, out, cfg, subject_id=subject)
    except LightmanError as exc:
        _fail(exc)
        return
    typer.echo(f"session:  {result.session_id}")
    typer.echo(f"output:   {result.session_dir}")
    typer.echo(
        f"frames:   {result.summary['frames_analyzed']}  "
        f"face coverage {result.summary['face_coverage']:.0%}"
    )
    typer.echo(f"baseline: quality {result.baseline.quality:.2f}")
    typer.echo(f"events:   {json.dumps(result.summary['event_counts'])}")
    for note in result.manifest.quality.notes:
        typer.secho(f"note:     {note}", fg=typer.colors.YELLOW)
    if cfg.storage.write_report:
        typer.echo(f"report:   {result.session_dir / 'report.html'}")


@app.command()
def doctor() -> None:
    """Inspect the runtime environment (OS, CPU, accelerators, key package versions)."""
    from lightman.core.env import snapshot_environment
    from lightman.models import ModelRegistry

    env = snapshot_environment()
    typer.echo(json.dumps(env.model_dump(mode="json"), indent=2))
    reg = ModelRegistry()
    typer.echo(f"model cache: {reg.cache_dir}")
    for e in reg.entries():
        state = "cached" if reg.is_cached(e.model_id) else "missing"
        typer.echo(f"  {e.model_id}: {state} ({e.license})")


@models_app.command("list")
def models_list() -> None:
    """List models in the manifest and their cache state."""
    from lightman.models import ModelRegistry

    reg = ModelRegistry()
    for e in reg.entries():
        state = "cached" if reg.is_cached(e.model_id) else "missing"
        typer.echo(f"{e.model_id}\t{state}\t{e.license}\t{e.size_bytes} bytes\t{e.task}")


@models_app.command("download")
def models_download(model_id: str) -> None:
    """Download and verify a model asset into the local cache."""
    from lightman.models import ModelRegistry

    try:
        path = ModelRegistry().ensure(model_id)
    except LightmanError as exc:
        _fail(exc)
        return
    typer.echo(str(path))


@models_app.command("verify")
def models_verify(model_id: str) -> None:
    """Verify a cached model against its pinned SHA-256."""
    from lightman.models import ModelRegistry

    try:
        path = ModelRegistry().verify(model_id)
    except LightmanError as exc:
        _fail(exc)
        return
    typer.echo(f"ok {path}")


@models_app.command("import")
def models_import(
    model_id: str,
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Offline install: copy a manually obtained model file into the cache (hash-verified)."""
    from lightman.models import ModelRegistry

    try:
        path = ModelRegistry().import_file(model_id, source)
    except LightmanError as exc:
        _fail(exc)
        return
    typer.echo(str(path))


if __name__ == "__main__":  # pragma: no cover
    app()
