from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import nnls

from vibrational_finder.models import ObservedSpectrum


@dataclass(frozen=True, slots=True)
class PhaseDeconvolutionFit:
    x: np.ndarray
    measured: np.ndarray
    main: np.ndarray
    additional: np.ndarray
    scales: tuple[float, float]
    offset: float

    def difference(self, additional_multiplier: float = 1.0) -> np.ndarray:
        """Measured minus the whole model, including the fitted constant."""
        return self.measured - (self.main + self.additional * additional_multiplier + self.offset)


def _ordered_points(spectrum: ObservedSpectrum) -> tuple[np.ndarray, np.ndarray]:
    x, y = np.asarray(spectrum.x, dtype=float), np.asarray(spectrum.y, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or x.size < 2 or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError(f"{spectrum.name or spectrum.id} must contain at least two finite paired points.")
    order = np.argsort(x)
    x, y = x[order], y[order]
    if np.any(np.diff(x) == 0):
        raise ValueError(f"{spectrum.name or spectrum.id} contains duplicate coordinates.")
    return x, y


def fit_phase_deconvolution(
    observed: ObservedSpectrum,
    main_reference: ObservedSpectrum,
    additional_reference: ObservedSpectrum,
) -> PhaseDeconvolutionFit:
    """Fit one constant and two nonnegative profile scales over common measured coordinates."""
    traces = (observed, main_reference, additional_reference)
    if len({item.id for item in traces}) != 3:
        raise ValueError("Choose two distinct phase references other than the measured spectrum.")
    if any(item.kind != observed.kind for item in traces[1:]):
        raise ValueError("Both references must use the same method as the measured spectrum.")
    if any((item.x_unit, item.y_unit) != (observed.x_unit, observed.y_unit) for item in traces[1:]):
        raise ValueError("Both references must use the same coordinate and intensity units.")

    x, y = _ordered_points(observed)
    reference_data = [_ordered_points(item) for item in traces[1:]]
    lower = max(rx[0] for rx, _ in reference_data)
    upper = min(rx[-1] for rx, _ in reference_data)
    mask = (x >= lower) & (x <= upper)
    if np.count_nonzero(mask) < 4:
        raise ValueError("The spectra need at least four measured points in their common range.")
    x, y = x[mask], y[mask]
    profiles = np.column_stack([np.interp(x, rx, ry) for rx, ry in reference_data])
    means = profiles.mean(axis=0)
    centered = profiles - means
    norms = np.linalg.norm(centered, axis=0)
    if np.any(norms <= 0) or not np.all(np.isfinite(norms)):
        raise ValueError("Both references must have varying intensity within the common range.")
    design = centered / norms
    # Close to proportional shapes cannot support distinct phase assignments reliably.
    if np.linalg.matrix_rank(design, tol=1e-6) < 2:
        raise ValueError("The reference profiles are too similar to separate in the common range.")
    mean_y = float(y.mean())
    coefficients, _ = nnls(design, y - mean_y)
    scales = coefficients / norms
    offset = mean_y - float(means @ scales)
    return PhaseDeconvolutionFit(
        x, y, profiles[:, 0] * scales[0], profiles[:, 1] * scales[1],
        (float(scales[0]), float(scales[1])), offset,
    )
