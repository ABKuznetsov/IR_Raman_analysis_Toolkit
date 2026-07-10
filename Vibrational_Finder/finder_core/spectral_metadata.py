from __future__ import annotations

from pathlib import Path


def infer_orientation(text: str | Path) -> str:
    value = str(text).lower()
    if "unoriented" in value or "un_oriented" in value or "powder" in value:
        return "unoriented"
    if "oriented" in value:
        return "oriented"
    if "single_crystal" in value or "single-crystal" in value:
        return "oriented"
    return "unknown"


def infer_polarization(text: str | Path) -> str:
    value = str(text).lower()
    if "unpolarized" in value or "nonpolarized" in value or "non-polarized" in value:
        return "unpolarized"
    if "polarized" in value:
        return "polarized"
    if "xx" in value or "xy" in value or "xz" in value or "yy" in value or "yz" in value or "zz" in value:
        return "polarized"
    return "unknown"


def spectrum_geometry_metadata(text: str | Path, *, library_type: str = "") -> dict[str, str]:
    orientation = infer_orientation(text)
    polarization = infer_polarization(text)
    if library_type == "dft":
        orientation = "calculated"
        polarization = "calculated"
    return {
        "orientation": orientation,
        "polarization": polarization,
        "geometry": f"{orientation}, {polarization}",
    }
