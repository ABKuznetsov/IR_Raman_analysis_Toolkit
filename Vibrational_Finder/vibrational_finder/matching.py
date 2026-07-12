from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from finder_core.matching_base import weighted_score
from finder_core.models import MatchScore, SignalTrace
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands, extract_reference_band_set
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum, SpectralBand, VibrationalMatchResult
from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum


@dataclass(slots=True)
class MatchingOptions:
    tolerance_cm1: float = 12.0
    max_shift_cm1: float = 8.0
    shift_step_cm1: float = 1.0
    preprocessing: PreprocessingOptions | None = None
    band_detection: BandDetectionOptions | None = None


def _safe_corr(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 2 or len(b) < 2:
        return 0.0
    if float(np.nanstd(a)) == 0.0 or float(np.nanstd(b)) == 0.0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def _interpolated_correlation(observed: SignalTrace, reference: SignalTrace, shift: float) -> float:
    ox = np.asarray(observed.x, dtype=float)
    oy = np.asarray(observed.y, dtype=float)
    rx = np.asarray(reference.x, dtype=float) + shift
    ry = np.asarray(reference.y, dtype=float)
    mask = (ox >= float(np.nanmin(rx))) & (ox <= float(np.nanmax(rx)))
    if int(np.sum(mask)) < 3:
        return 0.0
    interp = np.interp(ox[mask], rx, ry)
    corr = _safe_corr(oy[mask], interp)
    return max(0.0, corr) * 100.0


def _best_shift(observed: SignalTrace, reference: SignalTrace, options: MatchingOptions) -> tuple[float, float]:
    if options.max_shift_cm1 <= 0:
        return 0.0, _interpolated_correlation(observed, reference, 0.0)
    shifts = np.arange(
        -abs(options.max_shift_cm1),
        abs(options.max_shift_cm1) + options.shift_step_cm1,
        max(options.shift_step_cm1, 0.1),
    )
    scored = [(float(shift), _interpolated_correlation(observed, reference, float(shift))) for shift in shifts]
    return max(scored, key=lambda item: item[1])


def _match_bands(
    observed_bands: list[SpectralBand],
    reference_bands: list[SpectralBand],
    shift: float,
    tolerance: float,
) -> tuple[list[tuple[SpectralBand, SpectralBand, float]], list[SpectralBand]]:
    unused_reference = set(range(len(reference_bands)))
    matches: list[tuple[SpectralBand, SpectralBand, float]] = []
    unassigned: list[SpectralBand] = []
    for observed in sorted(observed_bands, key=lambda band: band.intensity, reverse=True):
        best_index: int | None = None
        best_delta = tolerance
        for index in unused_reference:
            reference = reference_bands[index]
            delta = abs(observed.position - (reference.position + shift))
            if delta <= best_delta:
                best_index = index
                best_delta = delta
        if best_index is None:
            unassigned.append(observed)
            continue
        reference = reference_bands[best_index]
        unused_reference.remove(best_index)
        matches.append((observed, reference, best_delta))
    return matches, unassigned


def _best_band_shift(
    observed_bands: list[SpectralBand],
    reference_bands: list[SpectralBand],
    options: MatchingOptions,
) -> float:
    if not observed_bands or not reference_bands or options.max_shift_cm1 <= 0:
        return 0.0
    shifts = np.arange(
        -abs(options.max_shift_cm1),
        abs(options.max_shift_cm1) + options.shift_step_cm1,
        max(options.shift_step_cm1, 0.1),
    )
    scored = []
    for shift in shifts:
        matches, _unassigned = _match_bands(observed_bands, reference_bands, float(shift), options.tolerance_cm1)
        quality = sum(1.0 - delta / max(options.tolerance_cm1, 1.0e-9) for _obs, _ref, delta in matches)
        scored.append((len(matches), quality, -abs(float(shift)), float(shift)))
    return max(scored)[3]


def _has_informative_reference_intensity(reference_bands: list[SpectralBand]) -> bool:
    values = np.asarray([max(float(band.intensity), 0.0) for band in reference_bands], dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        return False
    scale = float(np.nanmax(values))
    if scale <= 0.0:
        return False
    return float(np.nanstd(values) / scale) > 0.05


def score_candidate(
    observed: SignalTrace,
    candidate: CompoundCandidate,
    options: MatchingOptions | None = None,
    *,
    observed_processed: SignalTrace | None = None,
    observed_bands: list[SpectralBand] | None = None,
) -> VibrationalMatchResult:
    options = options or MatchingOptions()
    reference_band_set = candidate.band_set
    if reference_band_set is None and candidate.reference is not None:
        reference_band_set = candidate.reference.band_set
    if candidate.reference is None and reference_band_set is None:
        score = MatchScore(total_features=0)
        return VibrationalMatchResult(candidate=candidate, score=score)
    if observed_processed is None:
        observed_processed = preprocess_spectrum(observed, options.preprocessing)
    if observed_bands is None:
        observed_bands = detect_bands(observed_processed, options.band_detection)
    reference_processed = None
    correlation_score = 0.0
    if candidate.reference is not None:
        reference_processed = preprocess_spectrum(candidate.reference, options.preprocessing)
        shift, correlation_score = _best_shift(observed_processed, reference_processed, options)
        if reference_band_set is None:
            origin = str(candidate.metadata.get("origin", "experimental") or "experimental")
            reference_band_set = extract_reference_band_set(reference_processed, options.band_detection, origin=origin)
            candidate.band_set = reference_band_set
            candidate.reference.band_set = reference_band_set
    else:
        shift = _best_band_shift(observed_bands, reference_band_set.bands, options)
    reference_bands = list(reference_band_set.bands) if reference_band_set is not None else []
    matches, unassigned = _match_bands(observed_bands, reference_bands, shift, options.tolerance_cm1)
    total = max(len(observed_bands), 1)
    coverage = len(matches) / total * 100.0
    has_reference_intensity = _has_informative_reference_intensity(reference_bands)
    if matches:
        position = 100.0 - np.mean([delta / options.tolerance_cm1 * 100.0 for _, _, delta in matches])
        if has_reference_intensity:
            intensity_errors = [
                abs(obs.intensity - ref.intensity) / max(abs(obs.intensity), abs(ref.intensity), 1e-9)
                for obs, ref, _ in matches
            ]
            intensity = 100.0 - float(np.mean(intensity_errors) * 100.0)
        else:
            intensity = float(position)
    else:
        position = 0.0
        intensity = 0.0
    weights = (0.35, 0.2, 0.3, 0.15)
    if not has_reference_intensity:
        weights = (0.45, 0.0, 0.35, 0.2) if reference_processed is not None else (0.75, 0.0, 0.0, 0.25)
    score = weighted_score(
        position=float(position),
        intensity=float(intensity),
        correlation=float(correlation_score),
        coverage=float(coverage),
        weights=weights,
    )
    score.matched_features = len(matches)
    score.total_features = len(observed_bands)
    score.x_shift = shift
    aligned = None
    if reference_processed is not None and candidate.reference is not None:
        aligned = ReferenceSpectrum(
            x=(np.asarray(reference_processed.x, dtype=float) + shift).tolist(),
            y=list(reference_processed.y),
            kind=candidate.reference.kind,
            name=candidate.reference.name,
            source_path=candidate.reference.source_path,
            record=candidate.reference.record,
            band_set=reference_band_set,
        )
    return VibrationalMatchResult(
        candidate=candidate,
        score=score,
        observed_bands=observed_bands,
        reference_bands=reference_bands,
        unassigned_bands=unassigned,
        aligned_reference=aligned,
    )


def rank_candidates(
    observed: SignalTrace,
    candidates: list[CompoundCandidate],
    options: MatchingOptions | None = None,
    *,
    observed_processed: SignalTrace | None = None,
    observed_bands: list[SpectralBand] | None = None,
) -> list[VibrationalMatchResult]:
    options = options or MatchingOptions()
    if observed_processed is None:
        observed_processed = preprocess_spectrum(observed, options.preprocessing)
    if observed_bands is None:
        observed_bands = detect_bands(observed_processed, options.band_detection)
    results = [
        score_candidate(
            observed,
            candidate,
            options,
            observed_processed=observed_processed,
            observed_bands=observed_bands,
        )
        for candidate in candidates
    ]
    return sorted(results, key=lambda result: result.score.combined, reverse=True)
