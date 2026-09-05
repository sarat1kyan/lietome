"""Environment snapshot for reproducibility. Detection only; never installs anything."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from importlib import metadata

from lightman.schema.provenance import EnvironmentSnapshot

_KEY_PACKAGES = ("numpy", "av", "mediapipe", "opencv-contrib-python", "pyarrow", "pydantic")


def _memory_gb() -> float:
    try:
        if hasattr(os, "sysconf"):
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round(pages * page_size / 1024**3, 1)
    except (ValueError, OSError):
        pass
    return 0.0


def _cpu_name() -> str:
    if platform.system() == "Darwin" and shutil.which("sysctl"):
        try:
            out = subprocess.run(  # argument list, no shell
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.processor() or platform.machine()


def detect_accelerators() -> list[str]:
    found: list[str] = []
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        found.append("apple-silicon-gpu (metal)")
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0:
                found.extend(
                    f"cuda: {line.strip()}" for line in out.stdout.splitlines() if line.strip()
                )
        except (OSError, subprocess.SubprocessError):
            pass
    return found


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _KEY_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return versions


def snapshot_environment() -> EnvironmentSnapshot:
    return EnvironmentSnapshot(
        os=platform.system(),
        os_version=platform.release(),
        machine=platform.machine(),
        cpu=_cpu_name(),
        cpu_count=os.cpu_count() or 0,
        memory_gb=_memory_gb(),
        python=platform.python_version(),
        accelerators=detect_accelerators(),
        packages=_package_versions(),
    )
