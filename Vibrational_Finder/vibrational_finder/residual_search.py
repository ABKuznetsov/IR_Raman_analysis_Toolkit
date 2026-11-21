from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from finder_core.data_sources import SourceQuery

from vibrational_finder.analysis_controller import AnalysisController, AnalysisSearchRequest
from vibrational_finder.band_detection import detect_bands
from vibrational_finder.models import SpectralBand
from vibrational_finder.preprocessing import preprocess_spectrum
from vibrational_finder.profile_residual import ProfileResidualFit, fit_profile_residual
from vibrational_finder.services.candidate_search_service import CandidateSearchOptions, CandidateSearchResult


class ResidualSearchUnavailable(ValueError):
    pass


class ResidualEvidenceMode(str, Enum):
    BANDS = "bands"
    NNLS_PROFILE = "nnls_profile"


@dataclass(frozen=True, slots=True)
class ResidualSearchRequest:
    search_request: AnalysisSearchRequest
    accepted_candidate_keys: tuple[str, ...]
    evidence_bands: tuple[SpectralBand, ...]
    evidence_mode: ResidualEvidenceMode = ResidualEvidenceMode.BANDS
    profile_fit: ProfileResidualFit | None = None


@dataclass(frozen=True, slots=True)
class ResidualSearchOutcome:
    request: ResidualSearchRequest
    result: CandidateSearchResult


def build_residual_request(
    controller: AnalysisController,
    spectrum_id: str,
    sources: list[Any] | tuple[Any, ...],
    query: SourceQuery,
    options: CandidateSearchOptions | None = None,
    *,
    evidence_mode: ResidualEvidenceMode = ResidualEvidenceMode.BANDS,
) -> ResidualSearchRequest:
    profile = controller.project.profile_states.get(spectrum_id)
    if profile is None or not profile.selected_results:
        raise ResidualSearchUnavailable("No accepted component is available; accept one before searching for the next component.")
    evidence = tuple(deepcopy(profile.cumulative_unassigned_bands))
    if evidence_mode is ResidualEvidenceMode.BANDS and not evidence:
        raise ResidualSearchUnavailable("No meaningful unexplained bands remain for next-component search.")
    accepted = tuple(sorted(result.candidate.key for result in profile.selected_results))
    configured = deepcopy(options or CandidateSearchOptions())
    previous_gate = configured.candidate_gate
    configured.candidate_gate = lambda candidate: (
        candidate.key not in accepted and (previous_gate(candidate) if previous_gate is not None else True)
    )
    request = controller.make_request(spectrum_id, sources, query, configured)
    profile_fit = None
    if evidence_mode is ResidualEvidenceMode.NNLS_PROFILE:
        processed = preprocess_spectrum(request.observed, configured.matching_options.preprocessing)
        processed_observed = replace(
            request.observed,
            x=list(processed.x),
            y=list(processed.y),
        )
        try:
            profile_fit = fit_profile_residual(processed_observed, profile.selected_results)
        except ValueError as exc:
            raise ResidualSearchUnavailable(str(exc)) from exc
        detected = detect_bands(profile_fit.residual, configured.matching_options.band_detection)
        detected_positions = [float(band.position) for band in detected]
        residual_x = list(profile_fit.residual.x)
        residual_y = list(profile_fit.residual.y)
        for band in evidence:
            if any(abs(float(band.position) - position) <= 1.0e-6 for position in detected_positions):
                continue
            nearest = min(range(len(residual_x)), key=lambda index: abs(residual_x[index] - float(band.position)))
            if residual_y[nearest] > 1.0e-12:
                detected.append(replace(band, intensity=float(residual_y[nearest])))
        evidence = tuple(sorted(detected, key=lambda band: float(band.position)))
        if not evidence:
            raise ResidualSearchUnavailable("No meaningful profile residual remains for next-component search.")
        request = replace(request, observed=profile_fit.residual)
    request = replace(request, observed_bands=evidence)
    return ResidualSearchRequest(request, accepted, evidence, evidence_mode, profile_fit)


class ResidualSearchController:
    def __init__(self, analysis_controller: AnalysisController) -> None:
        self.analysis_controller = analysis_controller

    def run(self, request: ResidualSearchRequest) -> ResidualSearchOutcome:
        outcome = self.analysis_controller.run(request.search_request)
        return ResidualSearchOutcome(request, outcome.result)

    def apply_if_current(self, outcome: ResidualSearchOutcome) -> bool:
        request = outcome.request.search_request
        if not self.analysis_controller.is_current(request):
            return False
        profile = self.analysis_controller.project.profile_states.get(request.token.spectrum_id)
        if profile is None:
            return False
        profile.residual_results = deepcopy(outcome.result.matches)
        self.analysis_controller.document.mark_changed()
        return True

