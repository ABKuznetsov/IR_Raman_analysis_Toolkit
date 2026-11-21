from __future__ import annotations

import math

from PySide6.QtCore import QSize


INTERFACE_SCALE_PERCENTAGES = (75, 85, 100, 115, 125, 150)


def interface_density_factor(width: int, height: int, percent: int) -> float:
    if percent not in INTERFACE_SCALE_PERCENTAGES:
        raise ValueError(f"Unsupported interface scale: {percent}")
    compact_factor = min(1.0, max(1, int(width)) / 1600.0, max(1, int(height)) / 900.0)
    return max(0.3, compact_factor * percent / 100.0)


def bounded_density_factor(logical_dpi: float, available_size: QSize) -> float:
    dpi_factor = float(logical_dpi) / 96.0 if math.isfinite(float(logical_dpi)) else 1.0
    width_factor = max(1, available_size.width()) / 1600.0
    height_factor = max(1, available_size.height()) / 900.0
    workspace_factor = min(width_factor, height_factor)
    return min(1.35, max(0.80, dpi_factor * workspace_factor))
