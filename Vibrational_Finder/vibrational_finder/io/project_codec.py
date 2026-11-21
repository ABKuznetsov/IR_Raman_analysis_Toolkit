from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from typing import Protocol, TypeVar, cast

from finder_core.models import CandidateRecord, MatchScore, SignalKind, SignalTrace
from vibrational_finder.models import (
    CompoundCandidate,
    ObservedSpectrum,
    ReferenceBandSet,
    ReferenceSpectrum,
    SpectralBand,
    VibrationalMatchResult,
)
from vibrational_finder.profile_state import SpectrumProfileState
from vibrational_finder.processing_state import (
    ProcessingOperation,
    SpectrumProcessingState,
    mutable_processing_value,
)
from vibrational_finder.project_model import normalize_project_state, stable_spectrum_id
from vibrational_finder.project_state import ProjectUiState, VibrationalProjectState
from vibrational_finder.project_series import ProjectSeries


class ProjectAssetWriter(Protocol):
    def store_trace(self, folder: str, key: str, trace: SignalTrace) -> str: ...


class ProjectAssetReader(Protocol):
    def load_trace(self, member: str, cls: type[SignalTrace]) -> SignalTrace: ...


_TraceT = TypeVar("_TraceT", bound=SignalTrace)


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object.")
    return cast(dict[str, object], value)


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array.")
    return value


def _kind(value: object, path: str) -> SignalKind:
    try:
        return SignalKind(str(value))
    except ValueError as exc:
        raise ValueError(f"{path} contains an invalid signal kind: {value!r}.") from exc


def _encode_band(band: SpectralBand) -> dict[str, object]:
    return {
        "position": float(band.position),
        "intensity": float(band.intensity),
        "width": float(band.width),
        "assigned_candidate_keys": list(band.assigned_candidate_keys),
        "prominence": float(band.prominence),
        "mode": band.mode,
        "assignment": band.assignment,
        "symmetry": band.symmetry,
        "polarization": band.polarization,
        "orientation": band.orientation,
        "source_comment": band.source_comment,
        "confidence": float(band.confidence),
    }


def _decode_band(value: object, path: str) -> SpectralBand:
    data = _object(value, path)
    assigned = data.get("assigned_candidate_keys", [])
    if not isinstance(assigned, list):
        raise ValueError(f"{path}.assigned_candidate_keys must be an array.")
    try:
        return SpectralBand(
            position=float(data.get("position", 0.0)),
            intensity=float(data.get("intensity", 0.0)),
            width=float(data.get("width", 0.0)),
            assigned_candidate_keys=[str(item) for item in assigned],
            prominence=float(data.get("prominence", 0.0)),
            mode=str(data.get("mode", "")),
            assignment=str(data.get("assignment", "")),
            symmetry=str(data.get("symmetry", "")),
            polarization=str(data.get("polarization", "")),
            orientation=str(data.get("orientation", "")),
            source_comment=str(data.get("source_comment", "")),
            confidence=float(data.get("confidence", 1.0)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} contains invalid band values.") from exc


def _encode_band_set(band_set: ReferenceBandSet | None) -> dict[str, object] | None:
    if band_set is None:
        return None
    return {
        "bands": [_encode_band(band) for band in band_set.bands],
        "origin": band_set.origin,
        "extraction_method": band_set.extraction_method,
        "processing_recipe": deepcopy(band_set.processing_recipe),
    }


def _decode_band_set(value: object, path: str) -> ReferenceBandSet | None:
    if value is None:
        return None
    data = _object(value, path)
    bands = _array(data.get("bands", []), f"{path}.bands")
    recipe = data.get("processing_recipe", {})
    if not isinstance(recipe, dict):
        raise ValueError(f"{path}.processing_recipe must be an object.")
    return ReferenceBandSet(
        bands=[_decode_band(item, f"{path}.bands[{index}]") for index, item in enumerate(bands)],
        origin=str(data.get("origin", "experimental")),
        extraction_method=str(data.get("extraction_method", "scipy")),
        processing_recipe=cast(dict[str, str | float | int | bool], deepcopy(recipe)),
    )


def _encode_record(record: CandidateRecord) -> dict[str, object]:
    return {
        "key": record.key,
        "source": record.source,
        "entry_id": record.entry_id,
        "name": record.name,
        "formula": record.formula,
        "kind": record.kind.value,
        "metadata": dict(record.metadata),
    }


def _decode_record(value: object, path: str) -> CandidateRecord:
    data = _object(value, path)
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}.metadata must be an object.")
    return CandidateRecord(
        key=str(data.get("key", "")),
        source=str(data.get("source", "")),
        entry_id=str(data.get("entry_id", "")),
        name=str(data.get("name", "")),
        formula=str(data.get("formula", "")),
        kind=_kind(data.get("kind", SignalKind.UNKNOWN.value), f"{path}.kind"),
        metadata={str(key): str(item) for key, item in metadata.items()},
    )


def _encode_reference(
    reference: ReferenceSpectrum | None,
    assets: ProjectAssetWriter,
    key: str,
) -> dict[str, object] | None:
    if reference is None:
        return None
    return {
        "asset": assets.store_trace("references", key, reference),
        "record": _encode_record(reference.record) if reference.record is not None else None,
        "band_set": _encode_band_set(reference.band_set),
    }


def _decode_reference(
    value: object,
    assets: ProjectAssetReader,
    path: str,
) -> ReferenceSpectrum | None:
    if value is None:
        return None
    data = _object(value, path)
    member = str(data.get("asset", ""))
    if not member:
        raise ValueError(f"{path}.asset is required.")
    trace = assets.load_trace(member, ReferenceSpectrum)
    return ReferenceSpectrum(
        x=list(trace.x),
        y=list(trace.y),
        kind=trace.kind,
        name=trace.name,
        source_path=trace.source_path,
        x_unit=trace.x_unit,
        y_unit=trace.y_unit,
        record=_decode_record(data["record"], f"{path}.record") if data.get("record") is not None else None,
        band_set=_decode_band_set(data.get("band_set"), f"{path}.band_set"),
    )


def _encode_candidate(
    candidate: CompoundCandidate,
    assets: ProjectAssetWriter,
) -> dict[str, object]:
    data = _encode_record(candidate)
    data["reference"] = _encode_reference(candidate.reference, assets, candidate.key)
    data["band_set"] = _encode_band_set(candidate.band_set)
    return data


def _decode_candidate(
    value: object,
    assets: ProjectAssetReader,
    path: str,
) -> CompoundCandidate:
    data = _object(value, path)
    record = _decode_record(data, path)
    return CompoundCandidate(
        key=record.key,
        source=record.source,
        entry_id=record.entry_id,
        name=record.name,
        formula=record.formula,
        kind=record.kind,
        metadata=dict(record.metadata),
        reference=_decode_reference(data.get("reference"), assets, f"{path}.reference"),
        band_set=_decode_band_set(data.get("band_set"), f"{path}.band_set"),
    )


def _encode_score(score: MatchScore) -> dict[str, object]:
    return {field.name: getattr(score, field.name) for field in fields(MatchScore)}


def _decode_score(value: object, path: str) -> MatchScore:
    data = _object(value, path)
    try:
        return MatchScore(
            combined=float(data.get("combined", 0.0)),
            position=float(data.get("position", 0.0)),
            intensity=float(data.get("intensity", 0.0)),
            correlation=float(data.get("correlation", 0.0)),
            coverage=float(data.get("coverage", 0.0)),
            matched_features=int(data.get("matched_features", 0)),
            total_features=int(data.get("total_features", 0)),
            x_shift=float(data.get("x_shift", 0.0)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} contains invalid score values.") from exc


def _encode_result(
    result: VibrationalMatchResult,
    assets: ProjectAssetWriter,
) -> dict[str, object]:
    key = result.candidate.key
    return {
        "candidate": _encode_candidate(result.candidate, assets),
        "score": _encode_score(result.score),
        "observed_bands": [_encode_band(band) for band in result.observed_bands],
        "reference_bands": [_encode_band(band) for band in result.reference_bands],
        "unassigned_bands": [_encode_band(band) for band in result.unassigned_bands],
        "aligned_reference": _encode_reference(result.aligned_reference, assets, f"{key}-aligned"),
        **({"matched_peak_pairs": result.matched_peak_pairs} if result.matched_peak_pairs is not None else {}),
    }


def _decode_result(
    value: object,
    assets: ProjectAssetReader,
    path: str,
) -> VibrationalMatchResult:
    data = _object(value, path)

    def bands(name: str) -> list[SpectralBand]:
        values = _array(data.get(name, []), f"{path}.{name}")
        return [_decode_band(item, f"{path}.{name}[{index}]") for index, item in enumerate(values)]

    if "candidate" not in data:
        raise ValueError(f"{path}.candidate is required.")
    reference_bands = bands("reference_bands")
    pairs = None
    if data.get("matched_peak_pairs") is not None:
        pairs = []
        for value in _array(data["matched_peak_pairs"], f"{path}.matched_peak_pairs"):
            entry = _array(value, f"{path}.matched_peak_pairs entry")
            if len(entry) != 2 or type(entry[0]) is not int or not 0 <= entry[0] < len(reference_bands):
                raise ValueError(f"{path}.matched_peak_pairs contains an invalid reference band index.")
            pairs.append((entry[0], float(entry[1])))
    return VibrationalMatchResult(
        candidate=_decode_candidate(data["candidate"], assets, f"{path}.candidate"),
        score=_decode_score(data.get("score", {}), f"{path}.score"),
        observed_bands=bands("observed_bands"),
        reference_bands=reference_bands,
        unassigned_bands=bands("unassigned_bands"),
        aligned_reference=_decode_reference(data.get("aligned_reference"), assets, f"{path}.aligned_reference"),
        matched_peak_pairs=pairs,
    )


def _encode_observed(
    spectrum: ObservedSpectrum,
    assets: ProjectAssetWriter,
    folder: str,
    key: str,
) -> dict[str, object]:
    return {"id": spectrum.id, "asset": assets.store_trace(folder, key, spectrum)}


def _decode_observed(value: object, assets: ProjectAssetReader, path: str) -> ObservedSpectrum:
    data = _object(value, path)
    member = str(data.get("asset", ""))
    if not member:
        raise ValueError(f"{path}.asset is required.")
    spectrum = cast(ObservedSpectrum, assets.load_trace(member, ObservedSpectrum))
    stored_id = str(data.get("id", "")).strip()
    spectrum.id = stored_id or stable_spectrum_id("schema1", path, member)
    return spectrum


def _encode_profile_state(
    state: SpectrumProfileState,
    assets: ProjectAssetWriter,
    profile_key: str,
) -> dict[str, object]:
    result_by_key: dict[str, VibrationalMatchResult] = {}
    for result in state.results:
        key = result.candidate.key
        if key in result_by_key:
            raise ValueError(f"profile_states[{profile_key!r}] contains duplicate result key {key!r}.")
        result_by_key[key] = result
    selected_keys: list[str] = []
    for result in state.selected_results:
        key = result.candidate.key
        if key in result_by_key and key not in selected_keys:
            selected_keys.append(key)
    return {
        "spectrum": (
            _encode_observed(state.spectrum, assets, "spectra/processed", f"{profile_key}-profile")
            if state.spectrum is not None
            else None
        ),
        "results": [_encode_result(result, assets) for result in state.results],
        "residual_results": [_encode_result(result, assets) for result in state.residual_results],
        "browse_records": [_encode_record(record) for record in state.browse_records],
        "selected_result_keys": selected_keys,
        "visible_selected_candidate_keys": sorted(state.visible_selected_candidate_keys),
        "cumulative_unassigned_bands": [_encode_band(band) for band in state.cumulative_unassigned_bands],
        "processing": {
            "revision": state.processing.revision,
            "operations": [
                {"kind": operation.kind, "parameters": mutable_processing_value(operation.parameters)}
                for operation in state.processing.operations
            ],
        },
    }


def _decode_profile_state(
    value: object,
    assets: ProjectAssetReader,
    path: str,
) -> SpectrumProfileState:
    data = _object(value, path)
    raw_results = _array(data.get("results", []), f"{path}.results")
    results = [_decode_result(item, assets, f"{path}.results[{index}]") for index, item in enumerate(raw_results)]
    raw_residual = _array(data.get("residual_results", []), f"{path}.residual_results")
    residual_results = [
        _decode_result(item, assets, f"{path}.residual_results[{index}]")
        for index, item in enumerate(raw_residual)
    ]
    result_by_key: dict[str, VibrationalMatchResult] = {}
    for result in results:
        key = result.candidate.key
        if key in result_by_key:
            raise ValueError(f"{path}.results contains duplicate candidate key {key!r}.")
        result_by_key[key] = result
    raw_selected = _array(data.get("selected_result_keys", []), f"{path}.selected_result_keys")
    selected: list[VibrationalMatchResult] = []
    for item in raw_selected:
        key = str(item)
        if key not in result_by_key:
            raise ValueError(f"{path}.selected_result_keys references missing result {key!r}.")
        selected.append(result_by_key[key])
    raw_browse = _array(data.get("browse_records", []), f"{path}.browse_records")
    raw_visible = _array(
        data.get("visible_selected_candidate_keys", []),
        f"{path}.visible_selected_candidate_keys",
    )
    raw_cumulative = _array(
        data.get("cumulative_unassigned_bands", []),
        f"{path}.cumulative_unassigned_bands",
    )
    spectrum_value = data.get("spectrum")
    raw_processing = data.get("processing", {})
    processing_data = _object(raw_processing, f"{path}.processing")
    raw_operations = _array(processing_data.get("operations", []), f"{path}.processing.operations")
    operations: list[ProcessingOperation] = []
    for index, item in enumerate(raw_operations):
        operation_data = _object(item, f"{path}.processing.operations[{index}]")
        parameters = _object(
            operation_data.get("parameters", {}),
            f"{path}.processing.operations[{index}].parameters",
        )
        kind = str(operation_data.get("kind", "")).strip()
        if not kind:
            raise ValueError(f"{path}.processing.operations[{index}].kind is required.")
        operations.append(ProcessingOperation(kind, deepcopy(parameters)))
    try:
        processing = SpectrumProcessingState(
            operations=operations,
            revision=int(processing_data.get("revision", 0)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path}.processing contains invalid values.") from exc
    return SpectrumProfileState(
        spectrum=_decode_observed(spectrum_value, assets, f"{path}.spectrum") if spectrum_value is not None else None,
        results=results,
        residual_results=residual_results,
        browse_records=[_decode_record(item, f"{path}.browse_records[{index}]") for index, item in enumerate(raw_browse)],
        selected_results=selected,
        visible_selected_candidate_keys={str(item) for item in raw_visible},
        cumulative_unassigned_bands=[
            _decode_band(item, f"{path}.cumulative_unassigned_bands[{index}]")
            for index, item in enumerate(raw_cumulative)
        ],
        processing=processing,
    )


def _encode_ui_state(state: ProjectUiState) -> dict[str, object]:
    return {
        "display_mode": state.display_mode,
        "normalization_mode": state.normalization_mode,
        "laser_nm": float(state.laser_nm),
        "multi_offset": int(state.multi_offset),
        "reference_origin": state.reference_origin,
        "reference_view": state.reference_view,
        "include_raman": bool(state.include_raman),
        "include_ftir": bool(state.include_ftir),
        "enabled_sources": dict(state.enabled_sources),
        "composition_mode": state.composition_mode,
        "composition_elements": list(state.composition_elements),
        "selected_element_order": list(state.selected_element_order),
        "element_states": dict(state.element_states),
        "exclude_all_other_elements": bool(state.exclude_all_other_elements),
        "plot_view_settings": deepcopy(state.plot_view_settings),
        "tree_expansion_state": dict(state.tree_expansion_state),
    }


def _decode_ui_state(value: object, path: str) -> ProjectUiState:
    data = _object(value, path)
    enabled_sources = data.get("enabled_sources", {})
    plot_settings = data.get("plot_view_settings", {})
    composition_elements = data.get("composition_elements", [])
    selected_element_order = data.get("selected_element_order", [])
    element_states = data.get("element_states", {})
    tree_expansion_state = data.get("tree_expansion_state", {})
    if not isinstance(enabled_sources, dict):
        raise ValueError(f"{path}.enabled_sources must be an object.")
    if not isinstance(plot_settings, dict):
        raise ValueError(f"{path}.plot_view_settings must be an object.")
    if not isinstance(composition_elements, list):
        raise ValueError(f"{path}.composition_elements must be an array.")
    if not isinstance(selected_element_order, list):
        raise ValueError(f"{path}.selected_element_order must be an array.")
    if not isinstance(element_states, dict):
        raise ValueError(f"{path}.element_states must be an object.")
    if not isinstance(tree_expansion_state, dict):
        raise ValueError(f"{path}.tree_expansion_state must be an object.")
    try:
        return ProjectUiState(
            display_mode=str(data.get("display_mode", "One")),
            normalization_mode=str(data.get("normalization_mode", "none")),
            laser_nm=float(data.get("laser_nm", 532.0)),
            multi_offset=int(data.get("multi_offset", 10)),
            reference_origin=str(data.get("reference_origin", "both")),
            reference_view=str(data.get("reference_view", "profiles")),
            include_raman=bool(data.get("include_raman", True)),
            include_ftir=bool(data.get("include_ftir", True)),
            enabled_sources={str(key): bool(item) for key, item in enabled_sources.items()},
            composition_mode=str(data.get("composition_mode", "only")),
            composition_elements=[str(item) for item in composition_elements],
            selected_element_order=[str(item) for item in selected_element_order],
            element_states={str(key): str(item) for key, item in element_states.items()},
            exclude_all_other_elements=bool(data.get("exclude_all_other_elements", False)),
            plot_view_settings=deepcopy(plot_settings),
            tree_expansion_state={str(key): bool(item) for key, item in tree_expansion_state.items()},
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} contains invalid UI settings.") from exc


def encode_project_state(
    state: VibrationalProjectState,
    assets: ProjectAssetWriter,
) -> dict[str, object]:
    return {
        "project_id": state.project_id,
        "project_name": state.project_name,
        "series": [
            {"id": item.id, "name": item.name, "spectrum_ids": list(item.spectrum_ids)}
            for item in state.series
        ],
        "spectrum_order_ids": list(state.spectrum_order_ids),
        "active_spectrum_key": state.active_spectrum_key,
        "active_profile_spectrum_key": state.active_profile_spectrum_key,
        "visible_observed_keys": sorted(state.visible_observed_keys),
        "spectra": {
            "raman": [
                _encode_observed(spectrum, assets, "spectra/processed", f"raman-{index}")
                for index, spectrum in enumerate(state.raman_spectra)
            ],
            "ftir": [
                _encode_observed(spectrum, assets, "spectra/processed", f"ftir-{index}")
                for index, spectrum in enumerate(state.ftir_spectra)
            ],
        },
        "original_observed": [
            {
                "source_key": source_key,
                "spectrum": _encode_observed(spectrum, assets, "spectra/observed", source_key),
            }
            for source_key, spectrum in state.original_observed.items()
        ],
        "reference_records": [_encode_record(record) for record in state.reference_records],
        "reference_spectra": [
            _encode_reference(reference, assets, f"library-{index}")
            for index, reference in enumerate(state.reference_spectra)
        ],
        "sample_metadata": deepcopy(state.sample_metadata),
        "sample_bands": {
            key: [_encode_band(band) for band in bands]
            for key, bands in state.sample_bands.items()
        },
        "profile_states": {
            key: _encode_profile_state(profile, assets, key)
            for key, profile in state.profile_states.items()
        },
        "candidate_colors": dict(state.candidate_colors),
        "ui": _encode_ui_state(state.ui),
        "extensions": deepcopy(state.extensions),
    }


def decode_project_state(
    value: object,
    assets: ProjectAssetReader,
) -> VibrationalProjectState:
    data = _object(value, "project")
    spectra = _object(data.get("spectra", {}), "project.spectra")
    raw_raman = _array(spectra.get("raman", []), "project.spectra.raman")
    raw_ftir = _array(spectra.get("ftir", []), "project.spectra.ftir")
    raw_originals = _array(data.get("original_observed", []), "project.original_observed")
    raw_records = _array(data.get("reference_records", []), "project.reference_records")
    raw_references = _array(data.get("reference_spectra", []), "project.reference_spectra")
    raw_visible = _array(data.get("visible_observed_keys", []), "project.visible_observed_keys")
    raw_metadata = _object(data.get("sample_metadata", {}), "project.sample_metadata")
    raw_bands = _object(data.get("sample_bands", {}), "project.sample_bands")
    raw_profiles = _object(data.get("profile_states", {}), "project.profile_states")
    raw_colors = _object(data.get("candidate_colors", {}), "project.candidate_colors")
    raw_series = _array(data.get("series", []), "project.series")
    raw_order = _array(data.get("spectrum_order_ids", []), "project.spectrum_order_ids")
    extensions = data.get("extensions", {})
    if not isinstance(extensions, dict):
        raise ValueError("project.extensions must be an object.")

    originals: dict[str, ObservedSpectrum] = {}
    for index, item in enumerate(raw_originals):
        record = _object(item, f"project.original_observed[{index}]")
        source_key = str(record.get("source_key", ""))
        if not source_key:
            raise ValueError(f"project.original_observed[{index}].source_key is required.")
        originals[source_key] = _decode_observed(
            record.get("spectrum"),
            assets,
            f"project.original_observed[{index}].spectrum",
        )

    sample_metadata: dict[str, dict[str, str]] = {}
    for key, item in raw_metadata.items():
        metadata = _object(item, f"project.sample_metadata[{key!r}]")
        sample_metadata[str(key)] = {str(field): str(field_value) for field, field_value in metadata.items()}

    sample_bands: dict[str, list[SpectralBand]] = {}
    for key, item in raw_bands.items():
        values = _array(item, f"project.sample_bands[{key!r}]")
        sample_bands[str(key)] = [
            _decode_band(band, f"project.sample_bands[{key!r}][{index}]")
            for index, band in enumerate(values)
        ]

    raman_spectra = [
        _decode_observed(item, assets, f"project.spectra.raman[{index}]")
        for index, item in enumerate(raw_raman)
    ]
    ftir_spectra = [
        _decode_observed(item, assets, f"project.spectra.ftir[{index}]")
        for index, item in enumerate(raw_ftir)
    ]
    decoded_series: list[ProjectSeries] = []
    for index, item in enumerate(raw_series):
        record = _object(item, f"project.series[{index}]")
        series_id = str(record.get("id", "")).strip()
        name = str(record.get("name", "")).strip()
        spectrum_ids = _array(record.get("spectrum_ids", []), f"project.series[{index}].spectrum_ids")
        if not series_id:
            raise ValueError(f"project.series[{index}].id is required.")
        decoded_series.append(
            ProjectSeries(id=series_id, name=name or "Series", spectrum_ids=[str(value) for value in spectrum_ids])
        )
    state = VibrationalProjectState(
        project_id=str(data.get("project_id", "")).strip() or VibrationalProjectState().project_id,
        project_name=str(data.get("project_name", "")).strip() or "IR/Raman Phase Finder Project",
        series=decoded_series,
        spectrum_order_ids=[str(item) for item in raw_order],
        active_spectrum_key=(str(data["active_spectrum_key"]) if data.get("active_spectrum_key") is not None else None),
        active_profile_spectrum_key=(
            str(data["active_profile_spectrum_key"])
            if data.get("active_profile_spectrum_key") is not None
            else None
        ),
        visible_observed_keys={str(item) for item in raw_visible},
        raman_spectra=raman_spectra,
        ftir_spectra=ftir_spectra,
        original_observed=originals,
        reference_records=[
            _decode_record(item, f"project.reference_records[{index}]")
            for index, item in enumerate(raw_records)
        ],
        reference_spectra=[
            reference
            for index, item in enumerate(raw_references)
            if (reference := _decode_reference(item, assets, f"project.reference_spectra[{index}]")) is not None
        ],
        sample_metadata=sample_metadata,
        sample_bands=sample_bands,
        profile_states={
            str(key): _decode_profile_state(item, assets, f"project.profile_states[{key!r}]")
            for key, item in raw_profiles.items()
        },
        candidate_colors={str(key): str(item) for key, item in raw_colors.items()},
        ui=_decode_ui_state(data.get("ui", {}), "project.ui"),
        extensions=cast(dict[str, object], deepcopy(extensions)),
    )
    return normalize_project_state(state)
