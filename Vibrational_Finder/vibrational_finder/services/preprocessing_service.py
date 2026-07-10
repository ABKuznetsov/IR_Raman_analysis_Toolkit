from __future__ import annotations

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.signal import savgol_filter

try:
    from pybaselines import Baseline
except Exception:
    Baseline = None


PYBASELINES_METHODS = {"auto", "arpls", "asls", "snip", "rolling_ball"}


def auto_smoothing_window(x: np.ndarray, y: np.ndarray) -> int:
    if len(y) < 9:
        return 5
    diffs = np.diff(np.asarray(x, dtype=float))
    diffs = diffs[np.isfinite(diffs) & (diffs > 0)]
    if len(diffs):
        step = float(np.nanmedian(diffs))
        by_step = int(round(7.0 / max(step, 1.0e-6)))
    else:
        by_step = len(y) // 500 * 2 + 5
    by_points = len(y) // 650 * 2 + 5
    window = max(5, min(21, by_step, by_points))
    return window if window % 2 else window + 1


def smooth_spectrum_curve(
    y: np.ndarray,
    method: str = "savgol",
    window: int = 9,
    polyorder: int = 2,
    gaussian_sigma: float = 1.0,
) -> np.ndarray:
    if window <= 2 or len(y) < 5:
        return np.asarray(y, dtype=float)
    window = min(int(window), len(y) - 1 if len(y) % 2 == 0 else len(y))
    if window % 2 == 0:
        window -= 1
    if window < 3:
        return np.asarray(y, dtype=float)
    values = np.asarray(y, dtype=float)
    if method == "moving":
        kernel = np.ones(window, dtype=float) / float(window)
        padded = np.pad(values, window // 2, mode="edge")
        return np.convolve(padded, kernel, mode="valid")
    if method == "gaussian":
        sigma = max(0.1, float(gaussian_sigma))
        radius = max(1, int(round(sigma * 4)))
        grid = np.arange(-radius, radius + 1, dtype=float)
        kernel = np.exp(-0.5 * (grid / sigma) ** 2)
        kernel /= float(np.sum(kernel))
        padded = np.pad(values, (radius, radius), mode="edge")
        return np.convolve(padded, kernel, mode="same")[radius:-radius]
    order = max(1, min(int(polyorder), window - 2))
    try:
        return np.asarray(savgol_filter(values, window_length=window, polyorder=order, mode="interp"), dtype=float)
    except Exception:
        kernel = np.ones(window, dtype=float) / float(window)
        padded = np.pad(values, window // 2, mode="edge")
        return np.convolve(padded, kernel, mode="valid")


def estimate_background(x, y, degree: int = 10, method: str = "auto") -> np.ndarray:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(y) < 15:
        return np.full_like(y, float(np.nanpercentile(y, 5)))
    try:
        if method == "polynomial":
            background = _chebyshev_background(x, y, degree=degree)
        elif method in PYBASELINES_METHODS:
            background = _pybaselines_background(x, y, method=method)
        else:
            background = _local_envelope_background(x, y)
    except Exception:
        try:
            background = _chebyshev_background(x, y, degree=degree)
        except Exception:
            background = np.full_like(y, float(np.nanpercentile(y, 15)))
    floor = float(np.nanpercentile(y, 1))
    ceiling = float(np.nanpercentile(y, 99.5))
    return np.clip(background, floor, ceiling)


def _pybaselines_background(x: np.ndarray, y: np.ndarray, method: str = "auto") -> np.ndarray:
    if Baseline is None:
        return _local_envelope_background(x, y)
    if np.all(np.diff(x) >= 0):
        order = None
        xs = x
        ys = y
    else:
        order = np.argsort(x)
        xs = x[order]
        ys = y[order]
    if len(xs) < 15:
        return np.full_like(y, float(np.nanpercentile(y, 5)))

    baseline = Baseline(x_data=xs, check_finite=False)
    lam = float(np.clip(len(ys) ** 2.15, 1.0e4, 1.0e8))
    if method in {"auto", "arpls"}:
        background_sorted, _params = baseline.arpls(ys, lam=lam)
    elif method == "asls":
        background_sorted, _params = baseline.asls(ys, lam=lam, p=0.01)
    elif method == "snip":
        max_half_window = max(8, min(80, len(ys) // 90))
        background_sorted, _params = baseline.snip(ys, max_half_window=max_half_window)
    elif method == "rolling_ball":
        half_window = max(8, min(120, len(ys) // 60))
        background_sorted, _params = baseline.rolling_ball(ys, half_window=half_window)
    else:
        return _local_envelope_background(x, y)

    background_sorted = np.asarray(background_sorted, dtype=float)
    background_sorted = np.minimum(background_sorted, ys + max(float(np.nanstd(ys)) * 0.05, 1.0e-9))
    if order is None:
        return background_sorted
    background = np.empty_like(background_sorted)
    background[order] = background_sorted
    return background


def _local_envelope_background(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    order = np.argsort(x)
    xs = np.asarray(x[order], dtype=float)
    ys = np.asarray(y[order], dtype=float)
    xmin = float(xs[0])
    xmax = float(xs[-1])
    if xmax <= xmin:
        return np.full_like(y, float(np.nanpercentile(y, 15)))

    bin_count = min(140, max(30, len(ys) // 55))
    edges = np.linspace(xmin, xmax, bin_count + 1)
    node_x = [float(xs[0])]
    edge_points = max(8, len(ys) // 120)
    node_y = [float(np.nanmedian(ys[:edge_points]))]

    for left, right in zip(edges[:-1], edges[1:]):
        mask = (xs >= left) & (xs < right)
        if not np.any(mask):
            continue
        local_x = xs[mask]
        local_y = ys[mask]
        peak_cut = float(np.nanpercentile(local_y, 72))
        local_y = local_y[local_y <= peak_cut]
        if len(local_y) == 0:
            continue
        node_x.append(float(np.nanmean(local_x)))
        node_y.append(float(np.nanpercentile(local_y, 55)))

    node_x.append(float(xs[-1]))
    node_y.append(float(np.nanmedian(ys[-edge_points:])))

    node_x = np.asarray(node_x, dtype=float)
    node_y = np.asarray(node_y, dtype=float)
    if len(node_x) < 4:
        return np.full_like(y, float(np.nanpercentile(y, 15)))

    unique_x, unique_indices = np.unique(node_x, return_index=True)
    node_y = node_y[unique_indices]
    if len(unique_x) < 4:
        return np.full_like(y, float(np.nanpercentile(y, 15)))

    node_y = _smooth_nodes(node_y, window=7)
    interpolator = PchipInterpolator(unique_x, node_y, extrapolate=True)
    background_sorted = np.asarray(interpolator(xs), dtype=float)
    background_sorted = np.minimum(background_sorted, ys + max(float(np.nanstd(ys)) * 0.08, 1.0e-9))

    background = np.empty_like(background_sorted)
    background[order] = background_sorted
    return background


def _smooth_nodes(values: np.ndarray, window: int = 7) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if len(values) < window:
        return values
    half = window // 2
    smoothed = np.copy(values)
    for index in range(1, len(values) - 1):
        left = max(0, index - half)
        right = min(len(values), index + half + 1)
        smoothed[index] = float(np.nanmedian(values[left:right]))
    smoothed[0] = values[0]
    smoothed[-1] = values[-1]
    return smoothed


def _chebyshev_background(x: np.ndarray, y: np.ndarray, degree: int = 10) -> np.ndarray:
    xmin = float(np.nanmin(x))
    xmax = float(np.nanmax(x))
    if xmax <= xmin:
        return np.full_like(y, float(np.nanpercentile(y, 15)))
    xn = 2.0 * (x - xmin) / (xmax - xmin) - 1.0
    bin_count = min(90, max(18, len(y) // 80))
    edges = np.linspace(xmin, xmax, bin_count + 1)
    node_x = []
    node_y = []
    node_weights = []
    edge_points = max(8, len(y) // 40)
    anchor_points = max(5, len(y) // 180)
    left_anchor = float(np.nanmedian(y[:anchor_points]))
    right_anchor = float(np.nanmedian(y[-anchor_points:]))
    node_x.append(float(x[0]))
    node_y.append(left_anchor)
    node_weights.append(25.0)
    node_x.append(float(np.nanmean(x[:edge_points])))
    node_y.append(float(np.nanpercentile(y[:edge_points], 55)))
    node_weights.append(8.0)
    for left, right in zip(edges[:-1], edges[1:]):
        mask = (x >= left) & (x < right)
        if not np.any(mask):
            continue
        node_x.append(float(np.nanmean(x[mask])))
        node_y.append(float(np.nanpercentile(y[mask], 38)))
        node_weights.append(1.0)
    node_x.append(float(np.nanmean(x[-edge_points:])))
    node_y.append(float(np.nanpercentile(y[-edge_points:], 55)))
    node_weights.append(8.0)
    node_x.append(float(x[-1]))
    node_y.append(right_anchor)
    node_weights.append(25.0)
    if len(node_x) <= 3:
        return np.full_like(y, float(np.nanpercentile(y, 15)))
    node_x = np.asarray(node_x, dtype=float)
    node_y = np.asarray(node_y, dtype=float)
    node_weights = np.asarray(node_weights, dtype=float)
    node_xn = 2.0 * (node_x - xmin) / (xmax - xmin) - 1.0
    fit_degree = min(degree, len(node_x) - 2)
    vandermonde = np.polynomial.chebyshev.chebvander(node_xn, fit_degree)
    hard_anchor_mask = node_weights >= 20.0
    weights = np.copy(node_weights)
    coeffs = np.zeros(fit_degree + 1)
    for _iteration in range(8):
        coeffs, *_rest = np.linalg.lstsq(vandermonde * weights[:, None], node_y * weights, rcond=None)
        residual = node_y - vandermonde @ coeffs
        sigma = max(float(np.nanmedian(np.abs(residual))) * 1.4826, 1.0e-9)
        robust_weights = np.where(residual > sigma * 0.8, 0.35, 1.0)
        robust_weights = np.where(residual < -sigma * 2.0, 0.65, robust_weights)
        robust_weights = np.where(hard_anchor_mask, 1.0, robust_weights)
        weights = node_weights * robust_weights
    return np.asarray(np.polynomial.chebyshev.chebval(xn, coeffs), dtype=float)
