from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Sequence


RUNTIME_PROBE = "import numpy, scipy, pyqtgraph, PySide6"


def apple_silicon_available() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        result = subprocess.run(
            ["/usr/sbin/sysctl", "-in", "hw.optional.arm64"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and result.stdout.strip() == "1"


def native_python_command(
    python: Path,
    *arguments: str,
    apple_silicon: bool | None = None,
) -> list[str]:
    if apple_silicon is None:
        apple_silicon = apple_silicon_available()
    prefix = ["/usr/bin/arch", "-arm64"] if apple_silicon else []
    return [*prefix, str(python), *arguments]


def runtime_is_usable(
    python: Path,
    *,
    apple_silicon: bool | None = None,
    probe: Sequence[str] = ("-c", RUNTIME_PROBE),
) -> bool:
    if not python.exists():
        return False
    try:
        result = subprocess.run(
            native_python_command(python, *probe, apple_silicon=apple_silicon),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0
