from __future__ import annotations

from dataclasses import dataclass, field

from finder_core.models import CandidateRecord
from vibrational_finder.models import ObservedSpectrum, SpectralBand, VibrationalMatchResult
from vibrational_finder.processing_state import SpectrumProcessingState


@dataclass
class SpectrumProfileState:
    spectrum: ObservedSpectrum | None = None
    results: list[VibrationalMatchResult] = field(default_factory=list)
    residual_results: list[VibrationalMatchResult] = field(default_factory=list)
    browse_records: list[CandidateRecord] = field(default_factory=list)
    selected_results: list[VibrationalMatchResult] = field(default_factory=list)
    visible_selected_candidate_keys: set[str] = field(default_factory=set)
    cumulative_unassigned_bands: list[SpectralBand] = field(default_factory=list)
    processing: SpectrumProcessingState = field(default_factory=SpectrumProcessingState)
