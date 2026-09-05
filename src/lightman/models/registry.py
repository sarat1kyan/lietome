"""Model registry: a JSON manifest of assets with pinned SHA-256, plus a local cache.

Security properties:
* Every asset has a pinned SHA-256 and size. Downloads that exceed the declared size are
  aborted; a hash mismatch deletes the file and raises :class:`ModelIntegrityError`.
* Downloads are written to a temp file in the cache dir and renamed atomically, so a
  half-written asset is never mistaken for a valid one.
* Assets are opaque bytes to this module: nothing is deserialized here.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from importlib import resources
from pathlib import Path

import httpx
from platformdirs import user_cache_dir
from pydantic import BaseModel, ConfigDict, Field

from lightman.core.errors import ModelError, ModelIntegrityError
from lightman.core.logging import get_logger

log = get_logger(__name__)

ENV_MODEL_DIR = "LIGHTMAN_MODEL_DIR"


class ModelEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: str
    filename: str
    url: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    task: str
    runtime: str
    license: str
    source: str
    input: str = ""
    output: str = ""
    notes: str = ""


def default_cache_dir() -> Path:
    override = os.environ.get(ENV_MODEL_DIR)
    if override:
        return Path(override).expanduser()
    return Path(user_cache_dir("lightman", appauthor=False)) / "models"


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


class ModelRegistry:
    def __init__(self, cache_dir: Path | None = None, *, allow_download: bool = True) -> None:
        self.cache_dir = cache_dir or default_cache_dir()
        self.allow_download = allow_download
        self._entries = self._load_manifest()

    @staticmethod
    def _load_manifest() -> dict[str, ModelEntry]:
        raw = json.loads(
            resources.files("lightman.models").joinpath("manifest.json").read_text("utf-8")
        )
        return {mid: ModelEntry(model_id=mid, **spec) for mid, spec in raw["models"].items()}

    def entries(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def get(self, model_id: str) -> ModelEntry:
        try:
            return self._entries[model_id]
        except KeyError:
            raise ModelError(f"unknown model id: {model_id}") from None

    def local_path(self, model_id: str) -> Path:
        entry = self.get(model_id)
        return self.cache_dir / model_id.replace("/", "__") / entry.filename

    def is_cached(self, model_id: str) -> bool:
        return self.local_path(model_id).is_file()

    def verify(self, model_id: str) -> Path:
        """Return the cached path after verifying size and SHA-256; raise otherwise."""
        entry = self.get(model_id)
        path = self.local_path(model_id)
        if not path.is_file():
            raise ModelError(f"model {model_id} is not cached at {path}")
        if path.stat().st_size != entry.size_bytes:
            raise ModelIntegrityError(f"model {model_id} has unexpected size")
        digest = _sha256_of(path)
        if digest != entry.sha256:
            raise ModelIntegrityError(f"model {model_id} SHA-256 mismatch")
        return path

    def ensure(self, model_id: str, *, client: httpx.Client | None = None) -> Path:
        """Return a verified local path, downloading if permitted and necessary."""
        if self.is_cached(model_id):
            try:
                return self.verify(model_id)
            except ModelIntegrityError:
                log.warning("model_cache_corrupt_redownload", model_id=model_id)
                self.local_path(model_id).unlink(missing_ok=True)
        if not self.allow_download:
            raise ModelError(
                f"model {model_id} not cached and downloads are disabled; "
                f"run `lightman models download {model_id}` or import it offline"
            )
        return self.download(model_id, client=client)

    def download(self, model_id: str, *, client: httpx.Client | None = None) -> Path:
        entry = self.get(model_id)
        dest = self.local_path(model_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        log.info("model_download_start", model_id=model_id, size_bytes=entry.size_bytes)
        own_client = client is None
        client = client or httpx.Client(timeout=httpx.Timeout(60.0), follow_redirects=True)
        tmp_fd, tmp_name = tempfile.mkstemp(dir=dest.parent, prefix=".partial-")
        tmp_path = Path(tmp_name)
        try:
            h = hashlib.sha256()
            received = 0
            with os.fdopen(tmp_fd, "wb") as fh, client.stream("GET", entry.url) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    received += len(chunk)
                    if received > entry.size_bytes:
                        raise ModelIntegrityError(
                            f"model {model_id} download exceeded declared size"
                        )
                    h.update(chunk)
                    fh.write(chunk)
            if received != entry.size_bytes:
                raise ModelIntegrityError(
                    f"model {model_id} download size {received} != {entry.size_bytes}"
                )
            if h.hexdigest() != entry.sha256:
                raise ModelIntegrityError(f"model {model_id} SHA-256 mismatch after download")
            tmp_path.replace(dest)
        except httpx.HTTPError as exc:
            raise ModelError(f"model {model_id} download failed: {exc}") from exc
        finally:
            tmp_path.unlink(missing_ok=True)
            if own_client:
                client.close()
        log.info("model_download_ok", model_id=model_id)
        return dest

    def import_file(self, model_id: str, source: Path) -> Path:
        """Offline install: copy a locally obtained file into the cache after verification."""
        entry = self.get(model_id)
        if not source.is_file():
            raise ModelError(f"source file not found: {source}")
        if source.stat().st_size != entry.size_bytes or _sha256_of(source) != entry.sha256:
            raise ModelIntegrityError(f"file does not match manifest for {model_id}")
        dest = self.local_path(model_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())
        return dest
