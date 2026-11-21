from __future__ import annotations

from dataclasses import replace
from typing import Mapping

import numpy as np

from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.preprocessing import normalize_y
from vibrational_finder.processing_state import ProcessingOperation, SpectrumProcessingState
from vibrational_finder.services.preprocessing_service import (
    estimate_background,
    remove_narrow_spikes,
    smooth_spectrum_curve,
)


SUPPORTED_PROCESSING_OPERATIONS = {
    "smooth",
    "background",
    "despike",
    "crop",
    "normalize",
    "axis_offset",
    "phase_subtraction",
}


def _finite_number(parameters: Mapping[str, object], name: str, default: float | None = None) -> float:
    value = parameters.get(name, default)
    if value is None:
        raise ValueError(f"Processing parameter {name!r} is required.")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Processing parameter {name!r} must be numeric.") from exc
    if not np.isfinite(number):
        raise ValueError(f"Processing parameter {name!r} must be finite.")
    return number


def _positive_integer(parameters: Mapping[str, object], name: str, default: int) -> int:
    number = _finite_number(parameters, name, float(default))
    integer = int(number)
    if number != integer or integer < 1:
        raise ValueError(f"Processing parameter {name!r} must be a positive integer.")
    return integer


def _aligned_phase(x: np.ndarray, phase_x: object, phase_y: object) -> tuple[np.ndarray, np.ndarray]:
    reference_x = np.asarray(phase_x, dtype=float)
    reference_y = np.asarray(phase_y, dtype=float)
    if (
        reference_x.ndim != 1 or reference_x.shape != reference_y.shape or reference_x.size < 2
        or not np.all(np.isfinite(reference_x)) or not np.all(np.isfinite(reference_y))
    ):
        raise ValueError("The phase reference needs at least two finite spectral points.")
    order = np.argsort(reference_x)
    reference_x, reference_y = reference_x[order], reference_y[order]
    if np.any(np.diff(reference_x) <= 0):
        raise ValueError("The phase reference contains duplicate spectral coordinates.")
    overlap = (x >= reference_x[0]) & (x <= reference_x[-1])
    if np.count_nonzero(overlap) < 2:
        raise ValueError("The spectra do not overlap over at least two input points.")
    return overlap, np.interp(x[overlap], reference_x, reference_y)


def build_phase_subtraction_operation(
    spectrum: ObservedSpectrum,
    reference: ObservedSpectrum,
    *,
    factor: float | None = None,
    fit_range: tuple[float, float] | None = None,
) -> ProcessingOperation:
    if spectrum.id == reference.id:
        raise ValueError("Select a different spectrum as the phase reference.")
    if spectrum.kind != reference.kind:
        raise ValueError("The input and phase reference must use the same method.")
    if spectrum.x_unit != reference.x_unit or spectrum.y_unit != reference.y_unit:
        raise ValueError("The input and phase reference must use the same axis units.")
    x, y = np.asarray(spectrum.x, dtype=float), np.asarray(spectrum.y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("The input spectrum must contain finite paired spectral points.")
    overlap, aligned = _aligned_phase(x, reference.x, reference.y)
    parameters = {
        "input_id": spectrum.id,
        "phase_id": reference.id,
        "phase_name": reference.name or reference.id,
        "phase_x": reference.x,
        "phase_y": reference.y,
    }
    if factor is None:
        fit_x = x[overlap]
        lower, upper = sorted(fit_range) if fit_range is not None else (float(fit_x.min()), float(fit_x.max()))
        if not np.isfinite(lower) or not np.isfinite(upper):
            raise ValueError("The fit range must be finite.")
        fit = (fit_x >= lower) & (fit_x <= upper)
        if np.count_nonzero(fit) < 2:
            raise ValueError("Select a fit range with at least two overlapping points.")
        phase, observed = aligned[fit], y[overlap][fit]
        # A free constant in the fit keeps an intensity offset from biasing the scale.
        # It is not subtracted from the measured spectrum.
        centered = phase - phase.mean()
        norm = float(np.dot(centered, centered))
        if norm <= 0:
            raise ValueError("The selected fit range has no variation in the phase reference.")
        factor = max(0.0, float(np.dot(centered, observed - observed.mean()) / norm))
        parameters["fit_range"] = [lower, upper]
    if not np.isfinite(factor) or factor < 0:
        raise ValueError("The subtraction factor must be finite and nonnegative.")
    parameters["factor"] = float(factor)
    return ProcessingOperation("phase_subtraction", parameters)


def _apply_operation(
    x: np.ndarray,
    y: np.ndarray,
    operation: ProcessingOperation,
) -> tuple[np.ndarray, np.ndarray]:
    kind = operation.kind
    parameters = operation.parameters
    if kind not in SUPPORTED_PROCESSING_OPERATIONS:
        raise ValueError(f"Unsupported processing operation: {kind!r}.")

    if kind == "smooth":
        method = str(parameters.get("method", "savgol")).strip().lower()
        if method not in {"savgol", "moving", "gaussian"}:
            raise ValueError(f"Unsupported smoothing method: {method!r}.")
        window = _positive_integer(parameters, "window", 9)
        passes = _positive_integer(parameters, "passes", 1)
        polyorder = _positive_integer(parameters, "polyorder", 2)
        sigma = _finite_number(parameters, "gaussian_sigma", 1.0)
        if sigma <= 0:
            raise ValueError("Gaussian sigma must be positive.")
        result = y.copy()
        for _ in range(passes):
            result = smooth_spectrum_curve(
                result,
                method=method,
                window=window,
                polyorder=polyorder,
                gaussian_sigma=sigma,
            )
        return x, np.asarray(result, dtype=float)

    if kind == "background":
        method = str(parameters.get("method", "auto")).strip().lower()
        if method == "constant":
            percentile = _finite_number(parameters, "percentile", 15.0)
            if not 0 <= percentile <= 100:
                raise ValueError("Background percentile must be between 0 and 100.")
            background = np.full_like(y, float(np.nanpercentile(y, percentile)))
        else:
            if method not in {"auto", "arpls", "asls", "snip", "rolling_ball", "polynomial"}:
                raise ValueError(f"Unsupported background method: {method!r}.")
            degree = _positive_integer(parameters, "degree", 10)
            lam_value = parameters.get("lam")
            lam = None if lam_value is None else _finite_number(parameters, "lam")
            asymmetry = _finite_number(parameters, "asymmetry", 0.01)
            half_window_value = parameters.get("half_window")
            half_window = (
                None
                if half_window_value is None
                else _positive_integer(parameters, "half_window", 40)
            )
            background = estimate_background(
                x,
                y,
                degree=degree,
                method=method,
                lam=lam,
                asymmetry=asymmetry,
                half_window=half_window,
            )
        return x, y - np.asarray(background, dtype=float)

    if kind == "despike":
        threshold = _finite_number(parameters, "threshold", 8.0)
        max_width = _positive_integer(parameters, "max_width", 2)
        median_window = _positive_integer(parameters, "median_window", 5)
        passes = _positive_integer(parameters, "passes", 1)
        result = y.copy()
        for _ in range(passes):
            result = remove_narrow_spikes(
                result,
                threshold=threshold,
                max_width=max_width,
                median_window=median_window,
            )
        return x, np.asarray(result, dtype=float)

    if kind == "crop":
        lower = _finite_number(parameters, "minimum")
        upper = _finite_number(parameters, "maximum")
        lower, upper = sorted((lower, upper))
        mask = (x >= lower) & (x <= upper)
        if not np.any(mask):
            raise ValueError("Crop range does not contain any spectrum points.")
        return x[mask], y[mask]

    if kind == "normalize":
        mode = str(parameters.get("mode", "max")).strip().lower()
        if mode not in {"none", "max", "vector", "area", "snv"}:
            raise ValueError(f"Unsupported normalization mode: {mode!r}.")
        return x, np.asarray(normalize_y(y.copy(), mode, x), dtype=float)

    if kind == "phase_subtraction":
        factor = _finite_number(parameters, "factor")
        if factor < 0:
            raise ValueError("The subtraction factor must be nonnegative.")
        overlap, aligned = _aligned_phase(x, parameters.get("phase_x"), parameters.get("phase_y"))
        result = y.copy()
        result[overlap] -= aligned * factor
        return x, result

    offset = _finite_number(parameters, "offset", 0.0)
    return x + offset, y


def apply_processing_recipe(
    original: ObservedSpectrum,
    state: SpectrumProcessingState,
) -> ObservedSpectrum:
    """Replay committed processing without mutating the embedded original spectrum."""
    x = np.asarray(original.x, dtype=float).copy()
    y = np.asarray(original.y, dtype=float).copy()
    if x.ndim != 1 or y.ndim != 1 or len(x) != len(y) or not len(x):
        raise ValueError("Spectrum coordinates and intensities must be equally sized non-empty arrays.")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise ValueError("Spectrum coordinates and intensities must be finite.")
    for operation in state.operations:
        x, y = _apply_operation(x, y, operation)
        if not len(x) or len(x) != len(y) or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError(f"Processing operation {operation.kind!r} produced invalid spectrum data.")
    return replace(original, x=x.tolist(), y=y.tolist())
