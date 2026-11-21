from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.optimize import nnls

from vibrational_finder.models import ObservedSpectrum, VibrationalMatchResult


@dataclass(frozen=True, slots=True)
class ProfileResidualFit:
    candidate_keys: tuple[str, ...]
    coefficients: tuple[float, ...]
    reconstruction: tuple[float, ...]
    residual: ObservedSpectrum
    explained_fraction: float


def _aligned_column(x: np.ndarray, result: VibrationalMatchResult) -> np.ndarray:
    reference = result.aligned_reference or result.candidate.reference
    if reference is None or not reference.x or not reference.y:
        return np.zeros_like(x)
    reference_x = np.asarray(reference.x, dtype=float)
    reference_y = np.asarray(reference.y, dtype=float)
    finite = np.isfinite(reference_x) & np.isfinite(reference_y)
    if result.aligned_reference is None:
        reference_x = reference_x + float(result.score.x_shift)
    reference_x = reference_x[finite]
    reference_y = reference_y[finite]
    if reference_x.size == 0:
        return np.zeros_like(x)
    order = np.argsort(reference_x, kind="stable")
    reference_x = reference_x[order]
    reference_y = reference_y[order]
    unique_x, unique_indices = np.unique(reference_x, return_index=True)
    unique_y = reference_y[unique_indices]
    if unique_x.size == 1:
        column = np.zeros_like(x)
        nearest = int(np.argmin(np.abs(x - unique_x[0])))
        column[nearest] = unique_y[0]
        return column
    return np.interp(x, unique_x, unique_y, left=0.0, right=0.0)


def fit_profile_residual(
    observed: ObservedSpectrum,
    accepted_results: Iterable[VibrationalMatchResult],
) -> ProfileResidualFit:
    """Fit accepted reference profiles and return a non-negative residual trace.

    Coefficients describe spectral contributions on the supplied profile scale; they
    are not quantitative concentrations or phase fractions.
    """

    results = list(accepted_results)
    if not results:
        raise ValueError("At least one accepted reference profile is required.")
    x = np.asarray(observed.x, dtype=float)
    y = np.asarray(observed.y, dtype=float)
    if x.size == 0 or x.size != y.size:
        raise ValueError("Observed spectrum must contain equally sized x and y arrays.")
    finite_y = np.where(np.isfinite(y), y, 0.0)
    matrix = np.column_stack([_aligned_column(x, result) for result in results])
    matrix = np.where(np.isfinite(matrix), matrix, 0.0)
    if not np.any(np.abs(matrix) > 1.0e-15):
        raise ValueError("No accepted reference profile overlaps the observed spectrum.")
    coefficients, _norm = nnls(matrix, finite_y)
    reconstruction = matrix @ coefficients
    raw_residual = finite_y - reconstruction
    residual_y = np.maximum(raw_residual, 0.0)
    observed_norm = float(np.linalg.norm(finite_y))
    residual_norm = float(np.linalg.norm(raw_residual))
    explained = 1.0 if observed_norm == 0.0 and residual_norm == 0.0 else (
        max(0.0, min(1.0, 1.0 - residual_norm / observed_norm)) if observed_norm else 0.0
    )
    residual = ObservedSpectrum(
        id=observed.id,
        x=x.tolist(),
        y=residual_y.tolist(),
        kind=observed.kind,
        name=f"{observed.name or observed.id} — residual",
        source_path=observed.source_path,
        x_unit=observed.x_unit,
        y_unit=observed.y_unit,
    )
    return ProfileResidualFit(
        candidate_keys=tuple(result.candidate.key for result in results),
        coefficients=tuple(float(value) for value in coefficients),
        reconstruction=tuple(float(value) for value in reconstruction),
        residual=residual,
        explained_fraction=explained,
    )
