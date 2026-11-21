from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from collections.abc import Sequence

import numpy as np

from finder_core.models import SignalKind
from vibrational_finder.models import spectrum_kind


@dataclass(slots=True, frozen=True)
class SpectrumImportGuess:
    kind: SignalKind = SignalKind.UNKNOWN
    x_unit: str = "cm-1"
    y_unit: str = "a.u."
    peak_direction: str = "positive"
    x_reversed: bool = False
    confidence: float = 0.0
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _read_text_sample(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:120_000]
    except OSError:
        return ""


def _numeric_rows_from_text(text: str, *, max_rows: int = 4096) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//", "$$")):
            continue
        if line.upper().startswith("##"):
            continue
        parts = re.split(r"[\s,;]+", line)
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
        if len(rows) >= max_rows:
            break
    return rows


def _contains_any(text: str, tokens: Sequence[str]) -> bool:
    return any(token in text for token in tokens)


def _infer_x_unit(text: str, x_values: np.ndarray) -> tuple[str, float]:
    normalized = text.lower()
    if _contains_any(normalized, ("raman shift", "raman_shift", "1/cm", "cm-1", "cm^-1", "wavenumber")):
        return "cm-1", 0.95
    if _contains_any(normalized, ("xunits=1/cm", "xunits=cm", "x units=1/cm")):
        return "cm-1", 0.95
    if _contains_any(normalized, ("wavelength", "lambda", "xunits=nm", "x units=nm", " nanometer", " nm")):
        return "nm", 0.8
    if _contains_any(normalized, ("xunits=ev", "x units=ev", "energy", " ev")):
        return "eV", 0.8
    finite = x_values[np.isfinite(x_values)]
    if finite.size:
        x_min = float(np.nanmin(finite))
        x_max = float(np.nanmax(finite))
        if 0.0 <= x_min and x_max <= 20.0:
            return "eV", 0.55
    return "cm-1", 0.35


def _infer_y_unit_and_direction(text: str) -> tuple[str, str, float]:
    normalized = text.lower()
    if _contains_any(normalized, ("transmittance", "%t", "percent t", "transmission")):
        return "%T", "negative", 0.95
    if _contains_any(normalized, ("reflectance", "%r")):
        return "%R", "negative", 0.75
    if _contains_any(normalized, ("absorbance", "absorption")):
        return "absorbance", "positive", 0.9
    if _contains_any(normalized, ("intensity", "counts", "a.u.", "arbitrary")):
        return "a.u.", "positive", 0.55
    return "a.u.", "positive", 0.3


def _kind_scores(text: str, x_values: np.ndarray, y_unit: str, direction: str) -> dict[SignalKind, float]:
    normalized = text.lower()
    scores = {SignalKind.RAMAN: 0.0, SignalKind.FTIR: 0.0}
    if _contains_any(normalized, ("raman", "raman shift", "532", "633", "785", "488 nm", "514 nm")):
        scores[SignalKind.RAMAN] += 4.0
    if _contains_any(normalized, ("ftir", "infrared", "ir spectrum", "atr", "transmittance", "absorbance")):
        scores[SignalKind.FTIR] += 4.0
    if y_unit in {"%T", "%R"} or direction == "negative":
        scores[SignalKind.FTIR] += 2.0
    finite = x_values[np.isfinite(x_values)]
    if finite.size:
        x_min = float(np.nanmin(finite))
        x_max = float(np.nanmax(finite))
        if 40.0 <= x_min <= 250.0 and 700.0 <= x_max <= 1800.0:
            scores[SignalKind.RAMAN] += 1.0
        if x_min <= 800.0 and x_max >= 1800.0:
            scores[SignalKind.FTIR] += 1.0
    return scores


def _x_reversed_from_rows(rows: list[tuple[float, float]], x_values: np.ndarray) -> bool:
    if len(rows) >= 3:
        diffs = np.diff(np.asarray([row[0] for row in rows], dtype=float))
    else:
        diffs = np.diff(x_values)
    finite = diffs[np.isfinite(diffs)]
    if finite.size == 0:
        return False
    return int(np.sum(finite < 0.0)) > int(np.sum(finite > 0.0))


def guess_spectrum_metadata(
    path: str | Path,
    *,
    x: Sequence[float] | None = None,
    y: Sequence[float] | None = None,
    kind_hint: str | SignalKind | None = None,
) -> SpectrumImportGuess:
    source = Path(path)
    explicit_kind = spectrum_kind(kind_hint)
    raw_text = _read_text_sample(source)
    identity_text = " ".join([source.name, *source.parts[-4:], raw_text[:20_000]]).lower()
    rows = _numeric_rows_from_text(raw_text)
    x_values = np.asarray(x if x is not None else [row[0] for row in rows], dtype=float)
    y_values = np.asarray(y if y is not None else [row[1] for row in rows], dtype=float)

    warnings: list[str] = []
    finite_x = x_values[np.isfinite(x_values)]
    finite_y = y_values[np.isfinite(y_values)]
    if finite_x.size < 3 or finite_y.size < 3:
        warnings.append("too few numeric x/y points")
    if finite_x.size and len(np.unique(finite_x)) < finite_x.size:
        warnings.append("duplicate x values")
    if finite_y.size and float(np.nanmax(np.abs(finite_y))) == 0.0:
        warnings.append("zero intensity")
    x_reversed = _x_reversed_from_rows(rows, x_values)
    if x_reversed:
        warnings.append("x axis appears reversed")

    x_unit, x_confidence = _infer_x_unit(identity_text, x_values)
    y_unit, direction, y_confidence = _infer_y_unit_and_direction(identity_text)
    scores = _kind_scores(identity_text, x_values, y_unit, direction)
    if explicit_kind != SignalKind.UNKNOWN:
        kind = explicit_kind
        kind_confidence = 1.0
    else:
        best_kind, best_score = max(scores.items(), key=lambda item: item[1])
        other_score = min(scores.values())
        if best_score <= 0.0 or best_score - other_score < 0.75:
            kind = SignalKind.UNKNOWN
            kind_confidence = 0.0
            warnings.append("spectrum type is ambiguous")
        else:
            kind = best_kind
            kind_confidence = min(0.95, 0.35 + 0.12 * (best_score - other_score))

    confidence = min(1.0, max(kind_confidence, 0.0) * 0.65 + x_confidence * 0.2 + y_confidence * 0.15)
    return SpectrumImportGuess(
        kind=kind,
        x_unit=x_unit,
        y_unit=y_unit,
        peak_direction=direction,
        x_reversed=x_reversed,
        confidence=float(confidence),
        warnings=tuple(dict.fromkeys(warnings)),
    )
