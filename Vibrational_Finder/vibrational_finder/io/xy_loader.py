from __future__ import annotations

from pathlib import Path
import re

import numpy as np

from finder_core.models import SignalKind
from vibrational_finder.models import ObservedSpectrum, ReferenceSpectrum, spectrum_kind


TEXT_SPECTRUM_SUFFIXES = {".txt", ".xy", ".csv", ".tsv", ".dat", ".asc", ".ascii", ".prn"}
JCAMP_SUFFIXES = {".jdx", ".dx"}
OPTIONAL_BINARY_SUFFIXES = {".spc", ".spa", ".0", ".1", ".2"}


def supported_spectrum_extensions() -> tuple[str, ...]:
    return tuple(sorted(TEXT_SPECTRUM_SUFFIXES | JCAMP_SUFFIXES | OPTIONAL_BINARY_SUFFIXES))


def _read_xy_text(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    rows: list[tuple[float, float]] = []
    for raw_line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        if line.startswith("##"):
            continue
        parts = re.split(r"[\s,;]+", line)
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"No numeric x/y data found in {source}")
    data = np.asarray(rows, dtype=float)
    order = np.argsort(data[:, 0])
    data = data[order]
    return data[:, 0].tolist(), data[:, 1].tolist()


def _metadata_value(lines: list[str], key: str) -> str:
    prefix = f"##{key.upper()}="
    for line in lines:
        if line.upper().startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def _metadata_float(lines: list[str], key: str, default: float) -> float:
    value = _metadata_value(lines, key)
    try:
        return float(value)
    except ValueError:
        return default


def _read_jcamp_dx(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    lines = [line.strip() for line in source.read_text(encoding="utf-8", errors="ignore").splitlines()]
    x_factor = _metadata_float(lines, "XFACTOR", 1.0)
    y_factor = _metadata_float(lines, "YFACTOR", 1.0)
    delta_x = _metadata_float(lines, "DELTAX", 0.0)
    rows: list[tuple[float, float]] = []
    in_xydata = False
    in_peak_table = False

    for line in lines:
        upper = line.upper()
        if upper.startswith("##XYDATA="):
            in_xydata = True
            in_peak_table = False
            continue
        if upper.startswith("##PEAK TABLE=") or upper.startswith("##PEAKTABLE="):
            in_peak_table = True
            in_xydata = False
            continue
        if upper.startswith("##"):
            in_xydata = False
            in_peak_table = False
            continue
        if not line or line.startswith(("$$", "#", ";")):
            continue

        numbers = [float(value) for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", line)]
        if len(numbers) < 2:
            continue
        if in_xydata:
            x0 = numbers[0] * x_factor
            ys = [value * y_factor for value in numbers[1:]]
            step = delta_x if delta_x else 1.0
            rows.extend((x0 + index * step, y) for index, y in enumerate(ys))
        elif in_peak_table or len(numbers) == 2:
            rows.append((numbers[0] * x_factor, numbers[1] * y_factor))

    if not rows:
        raise ValueError(f"No JCAMP-DX x/y data found in {source}")
    data = np.asarray(rows, dtype=float)
    order = np.argsort(data[:, 0])
    data = data[order]
    return data[:, 0].tolist(), data[:, 1].tolist()


def _read_optional_binary(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".spc":
        raise ValueError(
            "Binary SPC import needs an optional SPC parser. Export the spectrum as CSV/TXT/JCAMP-DX "
            "or install a compatible SPC reader before loading this file."
        )
    raise ValueError(
        f"Binary vendor format {suffix or source.name!r} is recognized but not decoded yet. "
        "Please export the spectrum as CSV/TXT/JCAMP-DX for this build."
    )


def read_spectrum_xy(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in JCAMP_SUFFIXES:
        return _read_jcamp_dx(source)
    if suffix in OPTIONAL_BINARY_SUFFIXES:
        return _read_optional_binary(source)
    return _read_xy_text(source)


def load_xy_spectrum(
    path: str | Path,
    *,
    kind: str | SignalKind | None = None,
    name: str = "",
    reference: bool = False,
) -> ObservedSpectrum | ReferenceSpectrum:
    x, y = read_spectrum_xy(path)
    source = Path(path)
    kwargs = {
        "x": x,
        "y": y,
        "kind": spectrum_kind(kind),
        "name": name or source.stem,
        "source_path": str(source),
    }
    if reference:
        return ReferenceSpectrum(**kwargs)
    return ObservedSpectrum(**kwargs)
