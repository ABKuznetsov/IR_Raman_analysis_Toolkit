from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finder_core.models import SignalTrace
from vibrational_finder.models import SpectralBand

try:
    from scipy.signal import find_peaks, peak_widths
except Exception:  # pragma: no cover - optional runtime fallback
    find_peaks = None
    peak_widths = None


@dataclass(slots=True)
class BandDetectionOptions:
    min_prominence: float = 0.05
    min_distance_cm1: float = 8.0


def detect_bands(trace: SignalTrace, options: BandDetectionOptions | None = None) -> list[SpectralBand]:
    options = options or BandDetectionOptions()
    x = np.asarray(trace.x, dtype=float)
    y = np.asarray(trace.y, dtype=float)
    if len(x) < 3:
        return []
    step = float(np.nanmedian(np.abs(np.diff(x)))) or 1.0
    min_distance_points = max(1, int(round(options.min_distance_cm1 / step)))
    if find_peaks is not None:
        peak_indices, props = find_peaks(
            y,
            prominence=options.min_prominence,
            distance=min_distance_points,
        )
        widths = np.zeros_like(peak_indices, dtype=float)
        if peak_widths is not None and len(peak_indices):
            widths = peak_widths(y, peak_indices, rel_height=0.5)[0] * step
        return [
            SpectralBand(position=float(x[index]), intensity=float(y[index]), width=float(widths[i]))
            for i, index in enumerate(peak_indices)
        ]
    bands: list[SpectralBand] = []
    threshold = float(np.nanmin(y) + options.min_prominence * (np.nanmax(y) - np.nanmin(y)))
    for i in range(1, len(y) - 1):
        if y[i] > y[i - 1] and y[i] >= y[i + 1] and y[i] >= threshold:
            bands.append(SpectralBand(position=float(x[i]), intensity=float(y[i])))
    return bands
