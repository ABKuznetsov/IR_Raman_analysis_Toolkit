from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from finder_core.data_sources import SourceQuery
from vibrational_finder.models import ObservedSpectrum, SpectralBand
from vibrational_finder.profile_state import SpectrumProfileState
from vibrational_finder.project_document import ProjectDocument
from vibrational_finder.project_model import observed_by_id
from vibrational_finder.services.candidate_search_service import (
    CandidateSearchOptions,
    CandidateSearchResult,
    CandidateSearchService,
)


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _band_payload(bands: list[SpectralBand]) -> list[dict[str, object]]:
    return [
        {
            "position": float(band.position),
            "intensity": float(band.intensity),
            "width": float(band.width),
            "prominence": float(band.prominence),
            "assignment": band.assignment,
            "confidence": float(band.confidence),
            "assigned": list(band.assigned_candidate_keys),
        }
        for band in bands
    ]


@dataclass(frozen=True, slots=True)
class AnalysisRequestToken:
    spectrum_id: str
    document_revision: int
    processing_revision: int
    band_fingerprint: str
    enabled_sources: tuple[str, ...]
    query_fingerprint: str
    accepted_candidate_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisSearchRequest:
    token: AnalysisRequestToken
    observed: ObservedSpectrum
    sources: tuple[Any, ...]
    query: SourceQuery
    options: CandidateSearchOptions
    observed_bands: tuple[SpectralBand, ...]


@dataclass(frozen=True, slots=True)
class AnalysisSearchOutcome:
    request: AnalysisSearchRequest
    result: CandidateSearchResult


class AnalysisController:
    """Run spectroscopy search on snapshots and apply only still-current outcomes."""

    def __init__(self, document: ProjectDocument) -> None:
        self.document = document

    @property
    def project(self):
        return self.document.state

    def _spectrum(self, spectrum_id: str) -> ObservedSpectrum:
        spectrum = observed_by_id(self.project).get(spectrum_id)
        if spectrum is None:
            raise ValueError(f"Unknown observed spectrum: {spectrum_id!r}.")
        return spectrum

    def _enabled_source_names(self, sources: tuple[Any, ...]) -> tuple[str, ...]:
        configured = self.project.ui.enabled_sources
        if configured:
            return tuple(sorted(str(name) for name, enabled in configured.items() if enabled))
        return tuple(sorted(str(source.name) for source in sources))

    def _query_fingerprint(self, query: SourceQuery) -> str:
        ui = self.project.ui
        return _digest(
            {
                "text": query.text,
                "kind": query.kind.value,
                "formula": query.formula,
                "required_elements": sorted(query.required_elements),
                "excluded_elements": sorted(query.excluded_elements),
                "composition_mode": ui.composition_mode,
                "composition_elements": list(ui.composition_elements),
                "selected_element_order": list(ui.selected_element_order),
                "element_states": dict(ui.element_states),
                "exclude_all_other_elements": bool(ui.exclude_all_other_elements),
                "reference_origin": ui.reference_origin,
                "include_raman": ui.include_raman,
                "include_ftir": ui.include_ftir,
                "laser_nm": float(ui.laser_nm),
            }
        )

    def _token(
        self,
        spectrum_id: str,
        sources: tuple[Any, ...],
        query: SourceQuery,
    ) -> AnalysisRequestToken:
        self._spectrum(spectrum_id)
        profile = self.project.profile_states.get(spectrum_id)
        processing_revision = profile.processing.revision if profile is not None else 0
        accepted = tuple(
            sorted(result.candidate.key for result in profile.selected_results)
        ) if profile is not None else ()
        bands = self.project.sample_bands.get(spectrum_id, [])
        return AnalysisRequestToken(
            spectrum_id=spectrum_id,
            document_revision=self.document.revision,
            processing_revision=processing_revision,
            band_fingerprint=_digest(_band_payload(bands)),
            enabled_sources=self._enabled_source_names(sources),
            query_fingerprint=self._query_fingerprint(query),
            accepted_candidate_keys=accepted,
        )

    def make_request(
        self,
        spectrum_id: str,
        sources: list[Any] | tuple[Any, ...],
        query: SourceQuery,
        options: CandidateSearchOptions | None = None,
        *,
        use_sample_bands: bool = True,
    ) -> AnalysisSearchRequest:
        source_tuple = tuple(sources)
        enabled_names = set(self._enabled_source_names(source_tuple))
        enabled_sources = tuple(source for source in source_tuple if str(source.name) in enabled_names)
        observed = deepcopy(self._spectrum(spectrum_id))
        observed_bands = tuple(deepcopy(self.project.sample_bands.get(spectrum_id, []))) if use_sample_bands else ()
        query_copy = deepcopy(query)
        return AnalysisSearchRequest(
            token=self._token(spectrum_id, source_tuple, query_copy),
            observed=observed,
            sources=enabled_sources,
            query=query_copy,
            options=deepcopy(options or CandidateSearchOptions()),
            observed_bands=observed_bands,
        )

    def run(self, request: AnalysisSearchRequest) -> AnalysisSearchOutcome:
        result = CandidateSearchService(request.sources).search(
            deepcopy(request.query),
            deepcopy(request.observed),
            deepcopy(request.options),
            observed_bands=list(deepcopy(request.observed_bands)),
            prefilter_bands=list(deepcopy(request.observed_bands)) or None,
        )
        return AnalysisSearchOutcome(request=request, result=result)

    def apply_if_current(self, outcome: AnalysisSearchOutcome) -> bool:
        request = outcome.request
        if not self.is_current(request):
            return False
        spectrum = self._spectrum(request.token.spectrum_id)
        profile = self.project.profile_states.get(spectrum.id)
        if profile is None:
            profile = SpectrumProfileState(spectrum=spectrum)
            self.project.profile_states[spectrum.id] = profile
        result = deepcopy(outcome.result)
        profile.spectrum = spectrum
        merged_results = list(result.matches)
        result_keys = {item.candidate.key for item in merged_results}
        merged_results.extend(
            selected for selected in profile.selected_results if selected.candidate.key not in result_keys
        )
        profile.results = merged_results
        profile.residual_results.clear()
        profile.browse_records = result.shortlist_records
        self.document.mark_changed()
        return True

    def is_current(self, request: AnalysisSearchRequest) -> bool:
        return self._token(request.token.spectrum_id, request.sources, request.query) == request.token
