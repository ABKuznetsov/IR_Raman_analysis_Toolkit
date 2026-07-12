from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finder_core.models import SignalTrace
from vibrational_finder.services.preprocessing_service import estimate_background, remove_narrow_spikes, smooth_spectrum_curve


@dataclass(slots=True)
class PreprocessingOptions:
    baseline_order: int = 0
    baseline_method: str = "none"
    smoothing_window: int = 0
    smoothing_method: str = "moving"
    gaussian_sigma: float = 1.0
    despike: bool = False
    normalize: str = "max"


def moving_average(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    window = int(window)
    if window % 2 == 0:
        window += 1
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window, dtype=float) / float(window)
    return np.convolve(padded, kernel, mode="valid")


def polynomial_baseline(x: np.ndarray, y: np.ndarray, order: int) -> np.ndarray:
    if order <= 0 or len(x) <= order + 1:
        return np.zeros_like(y)
    coeff = np.polyfit(x, y, order)
    return np.polyval(coeff, x)


def normalize_y(y: np.ndarray, mode: str, x: np.ndarray | None = None) -> np.ndarray:
    if mode == "none":
        return y
    if mode == "vector":
        norm = float(np.linalg.norm(y))
        return y / norm if norm else y
    if mode == "area":
        coordinates = np.asarray(x, dtype=float) if x is not None else np.arange(len(y), dtype=float)
        area = float(np.trapezoid(np.abs(y), coordinates)) if len(y) > 1 else float(np.abs(y[0]))
        return y / area if area else y
    if mode == "snv":
        centered = y - float(np.nanmean(y))
        deviation = float(np.nanstd(centered))
        return centered / deviation if deviation else centered
    y = y - float(np.nanmin(y))
    maximum = float(np.nanmax(np.abs(y)))
    return y / maximum if maximum else y


def preprocess_spectrum(trace: SignalTrace, options: PreprocessingOptions | None = None) -> SignalTrace:
    options = options or PreprocessingOptions()
    x = np.asarray(trace.x, dtype=float)
    y = np.asarray(trace.y, dtype=float)
    if options.despike:
        y = remove_narrow_spikes(y)
    if options.baseline_method != "none":
        y = y - estimate_background(x, y, degree=max(options.baseline_order, 10), method=options.baseline_method)
    elif options.baseline_order > 0:
        y = y - polynomial_baseline(x, y, options.baseline_order)
    if options.smoothing_window > 1:
        y = smooth_spectrum_curve(
            y,
            method=options.smoothing_method,
            window=options.smoothing_window,
            gaussian_sigma=options.gaussian_sigma,
        )
    y = normalize_y(y, options.normalize, x)
    return SignalTrace(
        x=x.tolist(),
        y=y.tolist(),
        kind=trace.kind,
        name=trace.name,
        source_path=trace.source_path,
        x_unit=trace.x_unit,
        y_unit=trace.y_unit,
    )
