from __future__ import annotations

from dataclasses import dataclass, field

from finder_core.models import CandidateRecord
from vibrational_finder.models import ObservedSpectrum, ReferenceSpectrum, SpectralBand
from vibrational_finder.profile_state import SpectrumProfileState
from vibrational_finder.project_series import ProjectSeries, new_project_object_id


@dataclass(slots=True)
class ProjectUiState:
    display_mode: str = "One"
    normalization_mode: str = "none"
    laser_nm: float = 532.0
    multi_offset: int = 10
    reference_origin: str = "both"
    reference_view: str = "profiles"
    include_raman: bool = True
    include_ftir: bool = True
    enabled_sources: dict[str, bool] = field(default_factory=dict)
    composition_mode: str = "only"
    composition_elements: list[str] = field(default_factory=list)
    selected_element_order: list[str] = field(default_factory=list)
    element_states: dict[str, str] = field(default_factory=dict)
    exclude_all_other_elements: bool = False
    plot_view_settings: dict[str, object] = field(default_factory=dict)
    tree_expansion_state: dict[str, bool] = field(default_factory=dict)


@dataclass(slots=True)
class VibrationalProjectState:
    project_id: str = field(default_factory=lambda: new_project_object_id("project"))
    project_name: str = "IR/Raman Phase Finder Project"
    series: list[ProjectSeries] = field(default_factory=list)
    spectrum_order_ids: list[str] = field(default_factory=list)
    active_spectrum_key: str | None = None
    active_profile_spectrum_key: str | None = None
    visible_observed_keys: set[str] = field(default_factory=set)
    raman_spectra: list[ObservedSpectrum] = field(default_factory=list)
    ftir_spectra: list[ObservedSpectrum] = field(default_factory=list)
    original_observed: dict[str, ObservedSpectrum] = field(default_factory=dict)
    reference_records: list[CandidateRecord] = field(default_factory=list)
    reference_spectra: list[ReferenceSpectrum] = field(default_factory=list)
    sample_metadata: dict[str, dict[str, str]] = field(default_factory=dict)
    sample_bands: dict[str, list[SpectralBand]] = field(default_factory=dict)
    profile_states: dict[str, SpectrumProfileState] = field(default_factory=dict)
    candidate_colors: dict[str, str] = field(default_factory=dict)
    ui: ProjectUiState = field(default_factory=ProjectUiState)
    extensions: dict[str, object] = field(default_factory=dict)

    def normalize(self) -> "VibrationalProjectState":
        from vibrational_finder.project_model import normalize_project_state

        return normalize_project_state(self)
