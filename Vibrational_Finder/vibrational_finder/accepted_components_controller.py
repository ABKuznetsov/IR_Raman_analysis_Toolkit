from __future__ import annotations

from vibrational_finder.models import VibrationalMatchResult
from vibrational_finder.profile_state import SpectrumProfileState
from vibrational_finder.project_document import ProjectDocument
from vibrational_finder.project_model import observed_by_id
from vibrational_finder.unassigned_bands import cumulative_unassigned_bands


REFERENCE_COLORS = ("#1a73e8", "#d93025", "#188038", "#f9ab00", "#8e24aa", "#00acc1", "#c5221f")


class AcceptedComponentsController:
    def __init__(self, document: ProjectDocument) -> None:
        self.document = document

    @property
    def project(self):
        return self.document.state

    def profile(self, spectrum_id: str) -> SpectrumProfileState:
        profile = self.project.profile_states.get(spectrum_id)
        if profile is None:
            spectrum = observed_by_id(self.project).get(spectrum_id)
            if spectrum is None:
                raise ValueError(f"Unknown observed spectrum: {spectrum_id!r}.")
            profile = SpectrumProfileState(spectrum=spectrum)
            self.project.profile_states[spectrum_id] = profile
        return profile

    def ensure_color(self, key: str) -> str:
        existing = self.project.candidate_colors.get(key)
        if existing:
            return existing
        used = set(self.project.candidate_colors.values())
        color = next((item for item in REFERENCE_COLORS if item not in used), None)
        if color is None:
            color = REFERENCE_COLORS[len(self.project.candidate_colors) % len(REFERENCE_COLORS)]
        self.project.candidate_colors[key] = color
        return color

    def add(self, spectrum_id: str, result: VibrationalMatchResult) -> bool:
        profile = self.profile(spectrum_id)
        key = result.candidate.key
        existing = next((item for item in profile.selected_results if item.candidate.key == key), None)
        changed = False
        if existing is None:
            if all(item.candidate.key != key for item in profile.results):
                profile.results.append(result)
            profile.selected_results.append(result)
            changed = True
        if key not in profile.visible_selected_candidate_keys:
            profile.visible_selected_candidate_keys.add(key)
            changed = True
        had_color = key in self.project.candidate_colors
        self.ensure_color(key)
        changed = changed or not had_color
        if changed:
            profile.residual_results.clear()
            profile.cumulative_unassigned_bands = cumulative_unassigned_bands(profile.selected_results)
            self.document.mark_changed()
        return existing is None

    def set_visible(self, spectrum_id: str, key: str, visible: bool) -> bool:
        profile = self.profile(spectrum_id)
        if all(item.candidate.key != key for item in profile.selected_results):
            return False
        before = key in profile.visible_selected_candidate_keys
        if visible:
            profile.visible_selected_candidate_keys.add(key)
        else:
            profile.visible_selected_candidate_keys.discard(key)
        if before != visible:
            self.document.mark_changed()
            return True
        return False

    def remove(self, spectrum_id: str, key: str) -> bool:
        profile = self.profile(spectrum_id)
        retained = [item for item in profile.selected_results if item.candidate.key != key]
        if len(retained) == len(profile.selected_results):
            return False
        profile.selected_results = retained
        profile.residual_results.clear()
        profile.visible_selected_candidate_keys.discard(key)
        profile.cumulative_unassigned_bands = cumulative_unassigned_bands(retained)
        self._drop_unused_color(key)
        self.document.mark_changed()
        return True

    def clear(self, spectrum_id: str) -> int:
        profile = self.profile(spectrum_id)
        keys = [item.candidate.key for item in profile.selected_results]
        if not keys:
            return 0
        profile.selected_results.clear()
        profile.residual_results.clear()
        profile.visible_selected_candidate_keys.clear()
        profile.cumulative_unassigned_bands.clear()
        for key in keys:
            self._drop_unused_color(key)
        self.document.mark_changed()
        return len(keys)

    def _drop_unused_color(self, key: str) -> None:
        if any(
            result.candidate.key == key
            for profile in self.project.profile_states.values()
            for result in profile.selected_results
        ):
            return
        self.project.candidate_colors.pop(key, None)

