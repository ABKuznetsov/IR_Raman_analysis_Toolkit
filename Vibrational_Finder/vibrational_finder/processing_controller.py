from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from finder_core.models import SignalKind
from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.processing_state import ProcessingOperation, SpectrumProcessingState
from vibrational_finder.profile_state import SpectrumProfileState
from vibrational_finder.project_document import ProjectDocument
from vibrational_finder.project_model import observed_by_id, original_observed_for
from vibrational_finder.project_series import new_project_object_id
from vibrational_finder.services.phase_deconvolution import PhaseDeconvolutionFit
from vibrational_finder.services.spectrum_processing import apply_processing_recipe, build_phase_subtraction_operation


MAX_PROCESSING_OPERATIONS = 50


class SpectrumProcessingController:
    """Apply per-spectrum recipes as atomic project-document transactions."""

    def __init__(self, document: ProjectDocument) -> None:
        self.document = document

    @property
    def project(self):
        return self.document.state

    def _current(self, spectrum_id: str) -> ObservedSpectrum:
        spectrum = observed_by_id(self.project).get(str(spectrum_id))
        if spectrum is None:
            raise ValueError(f"Unknown observed spectrum: {spectrum_id!r}.")
        return spectrum

    def _profile(self, spectrum_id: str) -> SpectrumProfileState | None:
        return self.project.profile_states.get(spectrum_id)

    def _original(self, spectrum_id: str) -> tuple[ObservedSpectrum, bool]:
        current = self._current(spectrum_id)
        original = original_observed_for(self.project, spectrum_id)
        if original is not None:
            return original, spectrum_id not in self.project.original_observed
        return deepcopy(current), True

    def _state_with_operation(
        self,
        spectrum_id: str,
        operation: ProcessingOperation,
    ) -> SpectrumProcessingState:
        profile = self._profile(spectrum_id)
        current_state = profile.processing if profile is not None else SpectrumProcessingState()
        operations = [*current_state.operations, operation][-MAX_PROCESSING_OPERATIONS:]
        return SpectrumProcessingState(operations, revision=current_state.revision + 1)

    def _display_result(
        self,
        spectrum_id: str,
        state: SpectrumProcessingState,
    ) -> tuple[ObservedSpectrum, ObservedSpectrum, bool]:
        current = self._current(spectrum_id)
        original, needs_embed = self._original(spectrum_id)
        result = apply_processing_recipe(original, state)
        result = replace(
            result,
            id=current.id,
            kind=current.kind,
            name=current.name,
            source_path=current.source_path,
            x_unit=current.x_unit,
            y_unit=current.y_unit,
        )
        return result, original, needs_embed

    def preview(self, spectrum_id: str, operation: ProcessingOperation) -> ObservedSpectrum:
        state = self._state_with_operation(spectrum_id, operation)
        result, _original, _needs_embed = self._display_result(spectrum_id, state)
        return result

    def phase_subtraction_operation(
        self,
        spectrum_id: str,
        reference_id: str,
        *,
        factor: float | None = None,
        fit_range: tuple[float, float] | None = None,
    ) -> ProcessingOperation:
        return build_phase_subtraction_operation(
            self._current(spectrum_id), self._current(reference_id), factor=factor, fit_range=fit_range,
        )

    def preview_phase_subtraction(self, spectrum_id: str, operation: ProcessingOperation) -> ObservedSpectrum:
        if operation.kind != "phase_subtraction" or operation.parameters.get("input_id") != spectrum_id:
            raise ValueError("The subtraction does not belong to the selected spectrum.")
        return apply_processing_recipe(self._current(spectrum_id), SpectrumProcessingState([operation]))

    def save_phase_residual(self, spectrum_id: str, operation: ProcessingOperation) -> ObservedSpectrum:
        preview = self.preview_phase_subtraction(spectrum_id, operation)
        current = self._current(spectrum_id)
        identity = new_project_object_id("spectrum")
        name = f"{current.name or current.id} − {operation.parameters['phase_name']}"
        residual = replace(preview, id=identity, name=name, source_path="")
        # The residual's recipe starts at the exact processed input used in the fit.
        original = replace(deepcopy(current), id=identity, name=name, source_path="")
        collection = self.project.ftir_spectra if current.kind == SignalKind.FTIR else self.project.raman_spectra
        collection.append(residual)
        self.project.spectrum_order_ids.append(identity)
        self.project.visible_observed_keys.add(identity)
        self.project.original_observed[identity] = original
        self.project.profile_states[identity] = SpectrumProfileState(
            spectrum=residual, processing=SpectrumProcessingState([operation], revision=1),
        )
        self.document.mark_changed()
        return residual

    def save_deconvolved_phase(
        self,
        spectrum_id: str,
        main_reference_id: str,
        additional_reference_id: str,
        fit: PhaseDeconvolutionFit,
        multiplier: float,
        *,
        difference: bool = False,
    ) -> ObservedSpectrum:
        observed = self._current(spectrum_id)
        main_reference = self._current(main_reference_id)
        reference = self._current(additional_reference_id)
        identity = new_project_object_id("spectrum")
        if difference:
            suffix = "fit difference"
            values = fit.difference(multiplier)
        else:
            suffix = f"{reference.name or reference.id} (fitted)"
            values = fit.additional * multiplier
        derived = replace(
            observed, id=identity, name=f"{observed.name or observed.id} — {suffix}",
            source_path="", x=fit.x.tolist(), y=values.tolist(),
        )
        collection = self.project.ftir_spectra if observed.kind == SignalKind.FTIR else self.project.raman_spectra
        collection.append(derived)
        self.project.original_observed[identity] = deepcopy(derived)
        self.project.spectrum_order_ids.append(identity)
        self.project.visible_observed_keys.add(identity)
        self.project.sample_metadata[identity] = {
            "derivation": "two-phase fit difference" if difference else "two-phase profile fit",
            "mixture_id": spectrum_id,
            "mixture_name": observed.name,
            "main_reference_id": main_reference_id,
            "main_reference_name": main_reference.name,
            "main_scale": str(fit.scales[0]),
            "additional_reference_id": additional_reference_id,
            "additional_reference_name": reference.name,
            "additional_scale": str(fit.scales[1] * multiplier),
            "additional_multiplier": str(multiplier),
            "fit_offset": str(fit.offset),
            "fit_range": f"{fit.x[0]}–{fit.x[-1]} {observed.x_unit}",
        }
        self.document.mark_changed()
        return derived

    def commit(self, spectrum_id: str, operation: ProcessingOperation) -> ObservedSpectrum:
        state = self._state_with_operation(spectrum_id, operation)
        result, original, needs_embed = self._display_result(spectrum_id, state)
        return self._commit_result(spectrum_id, result, state, original, needs_embed)

    def can_undo(self, spectrum_id: str) -> bool:
        profile = self._profile(spectrum_id)
        return bool(profile is not None and profile.processing.operations)

    def undo(self, spectrum_id: str) -> ObservedSpectrum:
        current = self._current(spectrum_id)
        profile = self._profile(spectrum_id)
        if profile is None or not profile.processing.operations:
            return current
        state = SpectrumProcessingState(
            operations=profile.processing.operations[:-1],
            revision=profile.processing.revision + 1,
        )
        result, original, needs_embed = self._display_result(spectrum_id, state)
        return self._commit_result(spectrum_id, result, state, original, needs_embed)

    def reset(self, spectrum_id: str) -> ObservedSpectrum:
        current = self._current(spectrum_id)
        profile = self._profile(spectrum_id)
        if profile is None or not profile.processing.operations:
            return current
        state = SpectrumProcessingState([], revision=profile.processing.revision + 1)
        result, original, needs_embed = self._display_result(spectrum_id, state)
        return self._commit_result(spectrum_id, result, state, original, needs_embed)

    def _commit_result(
        self,
        spectrum_id: str,
        result: ObservedSpectrum,
        state: SpectrumProcessingState,
        original: ObservedSpectrum,
        needs_embed: bool,
    ) -> ObservedSpectrum:
        target_list: list[ObservedSpectrum] | None = None
        index: int | None = None
        for spectra in (self.project.raman_spectra, self.project.ftir_spectra):
            found = next(
                (item_index for item_index, spectrum in enumerate(spectra) if spectrum.id == spectrum_id),
                None,
            )
            if found is not None:
                target_list = spectra
                index = found
                break
        if target_list is None or index is None:
            raise ValueError(f"Unknown observed spectrum: {spectrum_id!r}.")

        profile = self.project.profile_states.get(spectrum_id)
        if profile is None:
            profile = SpectrumProfileState()
            self.project.profile_states[spectrum_id] = profile
        target_list[index] = result
        if needs_embed:
            self.project.original_observed[spectrum_id] = deepcopy(original)
        self.project.sample_bands.pop(spectrum_id, None)
        profile.spectrum = result
        profile.processing = state
        profile.results.clear()
        profile.residual_results.clear()
        profile.browse_records.clear()
        profile.selected_results.clear()
        profile.visible_selected_candidate_keys.clear()
        profile.cumulative_unassigned_bands.clear()
        self.document.mark_changed()
        return result
