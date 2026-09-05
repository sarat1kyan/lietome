import hashlib
from pathlib import Path

import httpx
import pytest

from lightman.core.errors import ModelError, ModelIntegrityError
from lightman.models.registry import ModelEntry, ModelRegistry

PAYLOAD = b"fake-model-bytes" * 100
SHA = hashlib.sha256(PAYLOAD).hexdigest()


def _registry(tmp_path: Path, payload: bytes = PAYLOAD, size: int | None = None) -> ModelRegistry:
    reg = ModelRegistry(cache_dir=tmp_path / "cache")
    reg._entries = {
        "test/model": ModelEntry(
            model_id="test/model",
            filename="m.bin",
            url="https://example.invalid/m.bin",
            sha256=SHA,
            size_bytes=size if size is not None else len(payload),
            task="t",
            runtime="r",
            license="Apache-2.0",
            source="s",
        )
    }
    return reg


def _client(body: bytes) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body))
    )


def test_manifest_loads_and_pins_hashes() -> None:
    reg = ModelRegistry(cache_dir=Path("/nonexistent"))
    e = reg.get("mediapipe/face_landmarker")
    assert len(e.sha256) == 64 and e.size_bytes > 0 and e.license == "Apache-2.0"
    with pytest.raises(ModelError, match="unknown model id"):
        reg.get("nope")


def test_download_verifies_and_caches(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    path = reg.ensure("test/model", client=_client(PAYLOAD))
    assert path.read_bytes() == PAYLOAD
    assert reg.is_cached("test/model")
    assert reg.verify("test/model") == path
    assert not list(path.parent.glob(".partial-*"))


def test_download_hash_mismatch_rejected(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    with pytest.raises(ModelIntegrityError, match="SHA-256"):
        reg.download("test/model", client=_client(b"x" * len(PAYLOAD)))
    assert not reg.is_cached("test/model")
    assert not [p for p in (tmp_path / "cache").rglob("*") if p.is_file()]  # no files left


def test_download_oversize_aborted(tmp_path: Path) -> None:
    reg = _registry(tmp_path, size=10)
    with pytest.raises(ModelIntegrityError, match="exceeded declared size"):
        reg.download("test/model", client=_client(PAYLOAD))


def test_corrupt_cache_is_redownloaded(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    p = reg.local_path("test/model")
    p.parent.mkdir(parents=True)
    p.write_bytes(b"c" * len(PAYLOAD))  # same length as PAYLOAD, wrong hash
    assert len(p.read_bytes()) == len(PAYLOAD)
    path = reg.ensure("test/model", client=_client(PAYLOAD))
    assert path.read_bytes() == PAYLOAD


def test_offline_mode_refuses_download(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    reg.allow_download = False
    with pytest.raises(ModelError, match="downloads are disabled"):
        reg.ensure("test/model")


def test_import_file_verifies(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    src = tmp_path / "m.bin"
    src.write_bytes(PAYLOAD)
    assert reg.import_file("test/model", src).read_bytes() == PAYLOAD
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"z" * len(PAYLOAD))
    with pytest.raises(ModelIntegrityError):
        reg.import_file("test/model", bad)
