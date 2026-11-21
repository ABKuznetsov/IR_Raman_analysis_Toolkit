from __future__ import annotations


def band_has_literature_peak_metadata(band) -> bool:
    if str(getattr(band, "mode", "") or "").strip():
        return True
    if str(getattr(band, "symmetry", "") or "").strip():
        return True
    if str(getattr(band, "assignment", "") or "").strip():
        return True
    comment = str(getattr(band, "source_comment", "") or "").strip().lower()
    if not comment:
        return False
    return any(
        token in comment
        for token in (
            "doi",
            "article",
            "literature",
            "reported",
            "table",
            "figure",
            "journal",
            "reference",
            "ferre",
        )
    )


def reference_peak_label(
    band,
    *,
    show_mode: bool = True,
    show_assignment: bool = False,
) -> str:
    parts: list[str] = []
    if show_mode:
        symmetry = str(getattr(band, "symmetry", "") or "").strip()
        mode = str(getattr(band, "mode", "") or "").strip()
        mode_label = symmetry or mode
        if mode_label and len(mode_label) <= 22:
            parts.append(mode_label)
    if show_assignment:
        assignment = str(getattr(band, "assignment", "") or "").strip()
        if assignment:
            parts.append(assignment if len(assignment) <= 34 else f"{assignment[:31]}...")
    return "\n".join(parts)


def matched_reference_band_positions(
    result,
    reference_bands: list,
    shift: float,
    tolerance_cm1: float,
) -> dict[int, float]:
    if result is None or not result.observed_bands or not reference_bands:
        return {}
    tolerance = max(float(tolerance_cm1), 1.0e-9)
    unused_reference = set(range(len(reference_bands)))
    matched: dict[int, float] = {}
    observed_bands = sorted(result.observed_bands, key=lambda band: float(getattr(band, "intensity", 0.0)), reverse=True)
    for observed in observed_bands:
        try:
            observed_position = float(observed.position)
        except (TypeError, ValueError):
            continue
        best_index: int | None = None
        best_delta = tolerance
        for index in unused_reference:
            try:
                reference_position = float(reference_bands[index].position) + shift
            except (TypeError, ValueError):
                continue
            delta = abs(observed_position - reference_position)
            if delta <= best_delta:
                best_index = index
                best_delta = delta
        if best_index is None:
            continue
        reference = reference_bands[best_index]
        unused_reference.remove(best_index)
        matched[id(reference)] = observed_position
    return matched


def reference_band_plot_positions(
    band,
    shift: float,
    matched_positions: dict[int, float],
) -> tuple[float, float]:
    reference_cm1 = float(band.position) + shift
    return float(matched_positions.get(id(band), reference_cm1)), reference_cm1


def normalized_band_intensities(bands) -> list[float]:
    values = [max(float(getattr(band, "intensity", 0.0)), 0.0) for band in bands]
    scale = max(values) if values else 0.0
    if scale <= 0.0:
        return [1.0 for _band in bands]
    return [max(value / scale, 0.025) for value in values]
