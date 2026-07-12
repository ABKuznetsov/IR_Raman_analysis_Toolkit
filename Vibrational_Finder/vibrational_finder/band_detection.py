from __future__ import annotations

from dataclasses import dataclass
import importlib.util

import numpy as np

from finder_core.models import SignalKind, SignalTrace
from vibrational_finder.models import ReferenceBandSet, SpectralBand

try:
    from scipy.signal import find_peaks, peak_widths
except Exception:  # pragma: no cover - optional runtime fallback
    find_peaks = None
    peak_widths = None


@dataclass(slots=True)
class BandDetectionOptions:
    min_prominence: float = 0.05
    min_distance_cm1: float = 8.0
    min_width_cm1: float = 0.0
    max_bands: int = 80
    direction: str = "auto"
    backend: str = "auto"
    fit_peaks: bool = False
    fit_profile: str = "PseudoVoigt"


def ramanchada2_available() -> bool:
    return importlib.util.find_spec("ramanchada2") is not None


def _normalize_band_intensities(bands: list[SpectralBand]) -> list[SpectralBand]:
    scale = max((max(float(band.intensity), 0.0) for band in bands), default=0.0)
    if scale <= 0.0:
        return bands
    for band in bands:
        band.intensity = max(0.0, float(band.intensity)) / scale
    return bands


def _detect_raman_bands(
    x: np.ndarray,
    normalized: np.ndarray,
    options: BandDetectionOptions,
) -> list[SpectralBand] | None:
    if not ramanchada2_available():
        return None
    try:
        from ramanchada2.spectrum import Spectrum

        spectrum = Spectrum(x=x.astype(float), y=normalized.astype(float))
        step = float(np.nanmedian(np.abs(np.diff(x)))) or 1.0
        width_points = max(1, int(round(options.min_width_cm1 / step))) if options.min_width_cm1 > 0 else 2
        candidates = spectrum.find_peak_multipeak(
            prominence=float(options.min_prominence),
            width=width_points,
            strategy="topo",
        )
        if options.fit_peaks and candidates.root:
            fitted = spectrum.fit_peak_multimodel(
                profile=options.fit_profile,
                candidates=candidates,
                bound_centers_to_group=True,
            )
            bands: list[SpectralBand] = []
            for group in fitted:
                for parameter_name, center in group.params.items():
                    if not parameter_name.endswith("_center"):
                        continue
                    prefix = parameter_name[:-6]
                    fwhm = group.params.get(f"{prefix}fwhm")
                    height = group.params.get(f"{prefix}height")
                    amplitude = group.params.get(f"{prefix}amplitude")
                    center_error = float(center.stderr) if center.stderr is not None else 0.0
                    bands.append(
                        SpectralBand(
                            position=float(center.value),
                            intensity=float(height.value if height is not None else amplitude.value),
                            width=float(fwhm.value if fwhm is not None else 0.0),
                            prominence=float(amplitude.value if amplitude is not None else 0.0),
                            confidence=1.0 / (1.0 + max(center_error, 0.0)),
                        )
                    )
        else:
            bands = []
            for group in candidates.root:
                for peak in group.peaks:
                    index = int(np.argmin(np.abs(x - float(peak.position))))
                    bands.append(
                        SpectralBand(
                            position=float(peak.position),
                            intensity=float(normalized[index]),
                            width=float(peak.sigma) * 2.355,
                            prominence=float(peak.amplitude),
                        )
                    )
        bands.sort(key=lambda band: band.prominence, reverse=True)
        bands = bands[: max(1, int(options.max_bands))]
        return sorted(_normalize_band_intensities(bands), key=lambda band: band.position)
    except Exception:
        return None


def detect_bands(trace: SignalTrace, options: BandDetectionOptions | None = None) -> list[SpectralBand]:
    options = options or BandDetectionOptions()
    x = np.asarray(trace.x, dtype=float)
    y = np.asarray(trace.y, dtype=float)
    if len(x) < 3:
        return []
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) < 3:
        return []
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    direction = options.direction.strip().lower()
    if direction == "auto":
        direction = "negative" if "transmit" in str(trace.y_unit).lower() else "positive"
    signal_y = -y if direction in {"negative", "minima", "down"} else y
    y_span = float(np.nanmax(signal_y) - np.nanmin(signal_y))
    if y_span <= 0.0:
        return []
    normalized = (signal_y - float(np.nanmin(signal_y))) / y_span
    backend = options.backend.strip().lower()
    if trace.kind == SignalKind.RAMAN and backend in {"auto", "ramanchada2", "ramanchada"}:
        raman_bands = _detect_raman_bands(x, normalized, options)
        if raman_bands is not None:
            return raman_bands
    step = float(np.nanmedian(np.abs(np.diff(x)))) or 1.0
    min_distance_points = max(1, int(round(options.min_distance_cm1 / step)))
    if find_peaks is not None:
        peak_indices, props = find_peaks(
            normalized,
            prominence=options.min_prominence,
            distance=min_distance_points,
        )
        widths = np.zeros_like(peak_indices, dtype=float)
        if peak_widths is not None and len(peak_indices):
            widths = peak_widths(normalized, peak_indices, rel_height=0.5)[0] * step
        prominences = np.asarray(props.get("prominences", np.zeros_like(peak_indices)), dtype=float)
        bands = [
            SpectralBand(
                position=float(x[index]),
                intensity=float(normalized[index]),
                width=float(widths[i]),
                prominence=float(prominences[i]),
            )
            for i, index in enumerate(peak_indices)
            if float(widths[i]) >= options.min_width_cm1
        ]
        bands.sort(key=lambda band: band.prominence, reverse=True)
        bands = bands[: max(1, int(options.max_bands))]
        return sorted(_normalize_band_intensities(bands), key=lambda band: band.position)
    bands: list[SpectralBand] = []
    threshold = float(options.min_prominence)
    for i in range(1, len(normalized) - 1):
        if normalized[i] > normalized[i - 1] and normalized[i] >= normalized[i + 1] and normalized[i] >= threshold:
            bands.append(SpectralBand(position=float(x[i]), intensity=float(normalized[i])))
    return _normalize_band_intensities(bands)


def extract_reference_band_set(
    trace: SignalTrace,
    options: BandDetectionOptions | None = None,
    *,
    origin: str = "experimental",
) -> ReferenceBandSet:
    options = options or BandDetectionOptions()
    return ReferenceBandSet(
        bands=detect_bands(trace, options),
        origin=origin,
        extraction_method=(
            "ramanchada2.fit_peak_multimodel (SciPy fallback enabled)"
            if trace.kind == SignalKind.RAMAN and options.fit_peaks and ramanchada2_available()
            else "ramanchada2.find_peak_multipeak (SciPy fallback enabled)"
            if trace.kind == SignalKind.RAMAN and options.backend in {"auto", "ramanchada2", "ramanchada"} and ramanchada2_available()
            else "scipy.find_peaks"
        ),
        processing_recipe={
            "min_prominence": float(options.min_prominence),
            "min_distance_cm1": float(options.min_distance_cm1),
            "min_width_cm1": float(options.min_width_cm1),
            "max_bands": int(options.max_bands),
            "direction": options.direction,
            "backend": options.backend,
            "fit_peaks": bool(options.fit_peaks),
            "fit_profile": options.fit_profile,
        },
    )
