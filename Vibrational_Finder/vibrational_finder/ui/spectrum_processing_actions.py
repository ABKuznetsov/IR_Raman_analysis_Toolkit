from __future__ import annotations

import numpy as np

from vibrational_finder.processing_controller import SpectrumProcessingController
from vibrational_finder.band_controller import BandController
from vibrational_finder.processing_state import ProcessingOperation
from vibrational_finder.services.phase_deconvolution import PhaseDeconvolutionFit, fit_phase_deconvolution
from vibrational_finder.services.preprocessing_service import auto_smoothing_window
from vibrational_finder.ui.phase_deconvolution_panel import PhaseDeconvolutionPanel
from vibrational_finder.ui.preprocessing_panels import (
    BackgroundRemovalPanel,
    DespikePanel,
    SmoothPanel,
    preprocessing_panel_style,
)
from vibrational_finder.ui.spectrum_transform_panels import (
    AxisCalibrationPanel,
    CropPanel,
    NormalizationPanel,
)
from vibrational_finder.ui.vibrational_plot import PhaseDeconvolutionPlot, show_observed_spectrum
from vibrational_finder.ui.band_workspace import BandWorkspace


class SpectrumProcessingActionsMixin:
    """Connect inline spectroscopy editors to the transactional processing core."""

    def _init_spectrum_processing_actions(self) -> None:
        self.processing_controller = SpectrumProcessingController(self.document)
        self.band_controller = BandController(self.document)
        self._active_processing_key: str | None = None
        self._active_processing_panel = None
        self._processing_previous_range: list[list[float]] | None = None
        self._processing_preview_operation: ProcessingOperation | None = None
        self._phase_deconvolution_fit: PhaseDeconvolutionFit | None = None
        self._phase_deconvolution_plot: PhaseDeconvolutionPlot | None = None
        self.action_bar.smoothRequested.connect(self._open_smooth_panel)
        self.action_bar.subtractBackgroundRequested.connect(self._open_background_panel)
        self.action_bar.phaseDeconvolutionRequested.connect(self._open_phase_deconvolution_panel)
        self.action_bar.despikeRequested.connect(self._open_despike_panel)
        self.action_bar.cropRequested.connect(self._open_crop_panel)
        self.action_bar.normalizeRequested.connect(self._open_normalization_panel)
        self.action_bar.axisCalibrationRequested.connect(self._open_axis_calibration_panel)
        self.action_bar.detectBandsRequested.connect(self._open_band_workspace)
        self.action_bar.undoProcessingRequested.connect(self.undo_active_processing)
        self.action_bar.resetProcessingRequested.connect(self.reset_active_processing)
        self.action_bar.processingSectionCollapsed.connect(self._processing_section_collapsed)
        self.plot_control_bar.axisCalibrationChanged.connect(self._calibration_indicator_changed)
        self._syncing_transform_indicators = False
        self._refresh_processing_controls()

    def apply_project_state(self, state, *, path=None) -> None:
        self.cancel_processing_preview()
        super().apply_project_state(state, path=path)

    def _open_smooth_panel(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            self._refresh_processing_controls()
            return
        panel = SmoothPanel(auto_smoothing_window(np.asarray(spectrum.x), np.asarray(spectrum.y)))
        self._mount_processing_panel("smooth", panel)

    def _open_background_panel(self) -> None:
        if self.active_spectrum() is None:
            self._refresh_processing_controls()
            return
        self._mount_processing_panel("background", BackgroundRemovalPanel())

    def _open_phase_deconvolution_panel(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return
        references = [item for item in self._ordered_spectra() if item.id != spectrum.id and
                      (item.kind, item.x_unit, item.y_unit) == (spectrum.kind, spectrum.x_unit, spectrum.y_unit)]
        self.cancel_processing_preview()
        self._processing_previous_range = self.spectrum_plot.viewRange()
        panel = PhaseDeconvolutionPanel(references)
        self.action_bar.set_section_editor("phase_deconvolution", panel)
        self._active_processing_key = "phase_deconvolution"
        self._active_processing_panel = panel
        panel.fitRequested.connect(self._fit_phase_deconvolution)
        panel.referencesChanged.connect(self._clear_phase_deconvolution)
        panel.contributionChanged.connect(self._update_phase_contribution)
        panel.differenceToggled.connect(self._set_phase_difference_visible)
        panel.saveRequested.connect(self._save_phase_output)
        panel.saveDifferenceRequested.connect(lambda: self._save_phase_output(difference=True))
        panel.cancelRequested.connect(self.cancel_processing_preview)

    def _fit_phase_deconvolution(self) -> None:
        panel = self._active_processing_panel
        spectrum = self.active_spectrum()
        if not isinstance(panel, PhaseDeconvolutionPanel) or spectrum is None:
            return
        by_id = {item.id: item for item in self._ordered_spectra()}
        main_id, additional_id = panel.reference_ids()
        main, additional = by_id.get(main_id), by_id.get(additional_id)
        self._clear_phase_deconvolution()
        panel.set_fit_available(False)
        if main is None or additional is None:
            panel.set_status("Choose two reference spectra that are still in the project.")
            return
        try:
            fit = fit_phase_deconvolution(spectrum, main, additional)
        except ValueError as exc:
            panel.set_status(str(exc))
            return
        self._phase_deconvolution_fit = fit
        plot = PhaseDeconvolutionPlot(spectrum, fit, additional.name)
        self._phase_deconvolution_plot = plot
        plot.differenceVisibilityRequested.connect(panel.show_difference.setChecked)
        self.plot_canvas.show_preview(plot)
        for surface in (plot, plot.main_plot.viewport(), plot.difference_plot.viewport()):
            self._register_spectrum_drop_target(surface)
        self._apply_plot_appearance()
        plot.set_difference_visible(panel.show_difference.isChecked())
        panel.reset_multiplier()
        panel.set_fit_available(True, component_available=fit.scales[1] > 0)
        range_text = f"Fit range: {fit.x[0]:g}–{fit.x[-1]:g} {spectrum.x_unit}"
        if fit.scales[1] == 0:
            range_text += " · No additional contribution in this fit."
        panel.set_status(range_text)

    def _update_phase_contribution(self) -> None:
        panel, plot = self._active_processing_panel, self._phase_deconvolution_plot
        if isinstance(panel, PhaseDeconvolutionPanel) and plot is not None:
            plot.update_contribution(panel.multiplier())

    def _set_phase_difference_visible(self, visible: bool) -> None:
        if self._phase_deconvolution_plot is not None:
            self._phase_deconvolution_plot.set_difference_visible(visible)

    def _save_phase_output(self, *, difference: bool = False) -> None:
        panel = self._active_processing_panel
        spectrum, fit = self.active_spectrum(), self._phase_deconvolution_fit
        if not isinstance(panel, PhaseDeconvolutionPanel) or spectrum is None or fit is None:
            return
        main_id, additional_id = panel.reference_ids()
        if main_id is None or additional_id is None:
            return
        try:
            saved = self.processing_controller.save_deconvolved_phase(
                spectrum.id, main_id, additional_id, fit, panel.multiplier(), difference=difference,
            )
        except ValueError as exc:
            panel.set_status(str(exc))
            return
        self._clear_processing_editor()
        self._refresh_project_tree()
        self.set_active_spectrum(saved.id)
        label = "fit difference" if difference else "fitted component"
        self.statusBar().showMessage(f"Saved {label}: {saved.name}", 6000)

    def _clear_phase_deconvolution(self) -> None:
        plot = self._phase_deconvolution_plot
        self._phase_deconvolution_fit = None
        self._phase_deconvolution_plot = None
        if plot is not None:
            self.plot_canvas.close_preview(plot)

    def fit_active_plot(self) -> None:
        if self._phase_deconvolution_plot is not None:
            self._phase_deconvolution_plot.fit_to_data()
        elif self._active_processing_key not in {None, "bands"}:
            self.spectrum_plot.enableAutoRange()
        else:
            self._redraw_active_spectrum()

    def _open_despike_panel(self) -> None:
        if self.active_spectrum() is None:
            self._refresh_processing_controls()
            return
        self._mount_processing_panel("despike", DespikePanel())

    def _open_crop_panel(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            self._refresh_processing_controls()
            return
        self._mount_processing_panel("crop", CropPanel(list(spectrum.x), spectrum.x_unit))

    def _open_normalization_panel(self) -> None:
        if self.active_spectrum() is None:
            self._refresh_processing_controls()
            return
        self._mount_processing_panel("normalize", NormalizationPanel())

    def _open_axis_calibration_panel(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            self._refresh_processing_controls()
            return
        self._mount_processing_panel("calibration", AxisCalibrationPanel(spectrum.x_unit))

    def _open_band_workspace(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            self._refresh_processing_controls()
            return
        self.cancel_processing_preview()
        workspace = BandWorkspace(self.band_controller)
        workspace.set_spectrum(spectrum.id)
        workspace.bandSelected.connect(self.select_band)
        workspace.bandsChanged.connect(self._bands_changed)
        self.action_bar.set_section_editor("bands", workspace)
        self._active_processing_key = "bands"
        self._active_processing_panel = workspace

    def _refresh_band_workspace(self) -> None:
        if self._active_processing_key == "bands" and isinstance(self._active_processing_panel, BandWorkspace):
            spectrum = self.active_spectrum()
            self._active_processing_panel.set_spectrum(spectrum.id if spectrum is not None else None)

    def _bands_changed(self) -> None:
        if hasattr(self, "_redraw_active_spectrum"):
            self._redraw_active_spectrum(preserve_view=True)

    def _mount_processing_panel(self, key: str, panel) -> None:
        self.cancel_processing_preview()
        self._processing_previous_range = self.spectrum_plot.viewRange()
        panel.setStyleSheet(preprocessing_panel_style(self._dark_theme))
        self.action_bar.set_section_editor(key, panel)
        self._active_processing_key = key
        self._active_processing_panel = panel
        panel.previewRequested.connect(self.preview_active_processing)
        panel.applyRequested.connect(self.apply_active_processing)
        panel.cancelRequested.connect(self.cancel_processing_preview)
        self.preview_active_processing()

    def _operation_from_panel(self) -> ProcessingOperation | None:
        panel = self._active_processing_panel
        key = self._active_processing_key
        if panel is None or key is None:
            return None
        if key == "smooth":
            return ProcessingOperation(
                "smooth",
                {
                    "method": panel.method(),
                    "window": panel.window_size(),
                    "polyorder": panel.polyorder(),
                    "gaussian_sigma": panel.gaussian_sigma(),
                    "passes": panel.passes(),
                },
            )
        if key == "background":
            parameters = {
                "method": panel.method(),
                "degree": panel.degree(),
                "lam": panel.lambda_value(),
                "asymmetry": panel.asymmetry(),
                "half_window": panel.half_window(),
                "percentile": panel.floor_percentile(),
            }
            return ProcessingOperation("background", parameters)
        if key == "despike":
            return ProcessingOperation(
                "despike",
                {
                    "threshold": panel.threshold(),
                    "max_width": panel.max_width(),
                    "median_window": panel.median_window(),
                    "passes": panel.passes(),
                },
            )
        if key == "crop":
            return ProcessingOperation(
                "crop",
                {"minimum": panel.minimum(), "maximum": panel.maximum()},
            )
        if key == "normalize":
            return ProcessingOperation("normalize", {"mode": panel.mode()})
        if key == "calibration":
            return ProcessingOperation("axis_offset", {"offset": panel.offset()})
        return None

    def preview_active_processing(self) -> None:
        spectrum = self.active_spectrum()
        operation = self._operation_from_panel()
        if spectrum is None or operation is None:
            return
        try:
            preview = self.processing_controller.preview(spectrum.id, operation)
        except ValueError as exc:
            self._processing_preview_operation = None
            if hasattr(self._active_processing_panel, "set_error"):
                self._active_processing_panel.set_error(str(exc))
            show_observed_spectrum(self.spectrum_plot, spectrum, preserve_x_range=True)
            return
        if hasattr(self._active_processing_panel, "set_error"):
            self._active_processing_panel.set_error("")
        background_y = None
        if operation.kind == "background" and len(preview.y) == len(spectrum.y):
            background_y = (np.asarray(spectrum.y) - np.asarray(preview.y)).tolist()
        show_observed_spectrum(
            self.spectrum_plot,
            preview,
            preview=True,
            background_y=background_y,
            preserve_x_range=True,
        )
        self._processing_preview_operation = operation

    def apply_active_processing(self) -> None:
        spectrum = self.active_spectrum()
        operation = self._operation_from_panel()
        if spectrum is None or operation is None:
            return
        spectrum_id = spectrum.id
        preview_range = (
            self.spectrum_plot.viewRange() if operation == self._processing_preview_operation else None
        )
        try:
            self.processing_controller.commit(spectrum_id, operation)
        except ValueError as exc:
            if hasattr(self._active_processing_panel, "set_error"):
                self._active_processing_panel.set_error(str(exc))
            return
        self._clear_processing_editor()
        self.set_active_spectrum(spectrum_id)
        self._restore_processing_view(preview_range)

    def _processing_section_collapsed(self, key: str) -> None:
        if key == self._active_processing_key and key != "bands":
            self.cancel_processing_preview()

    def cancel_processing_preview(self) -> None:
        had_editor = self._active_processing_key is not None
        previous_range = self._processing_previous_range
        self._clear_processing_editor()
        if had_editor:
            if hasattr(self, "_redraw_active_spectrum"):
                self._redraw_active_spectrum()
            else:
                show_observed_spectrum(self.spectrum_plot, self.active_spectrum())
            self._restore_processing_view(previous_range)
        self._refresh_processing_controls()

    def _restore_processing_view(self, view_range: list[list[float]] | None) -> None:
        if view_range is not None:
            self.spectrum_plot.setRange(xRange=view_range[0], yRange=view_range[1], padding=0)

    def _clear_processing_editor(self) -> None:
        key = self._active_processing_key
        self._clear_phase_deconvolution()
        self._active_processing_key = None
        self._active_processing_panel = None
        self._processing_previous_range = None
        self._processing_preview_operation = None
        if key is not None:
            self.action_bar.clear_section_editor(key)

    def undo_active_processing(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return
        self.cancel_processing_preview()
        self.processing_controller.undo(spectrum.id)
        self.set_active_spectrum(spectrum.id)

    def reset_active_processing(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return
        self.cancel_processing_preview()
        self.processing_controller.reset(spectrum.id)
        self.set_active_spectrum(spectrum.id)

    def _refresh_processing_controls(self) -> None:
        spectrum = self.active_spectrum()
        available = spectrum is not None
        self.action_bar.set_processing_available(
            available,
            "Import or select a Raman/FTIR spectrum to enable processing.",
        )
        can_undo = available and self.processing_controller.can_undo(spectrum.id)
        self.action_bar.set_history_available(can_undo, can_undo)
        self.plot_control_bar.normalize_checkbox.setEnabled(available)
        self.plot_control_bar.axis_calibration_checkbox.setEnabled(available)
        self._sync_transform_indicators()

    def _processing_kinds(self) -> list[str]:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return []
        profile = self.project.profile_states.get(spectrum.id)
        if profile is None:
            return []
        return [operation.kind for operation in profile.processing.operations]

    def _sync_transform_indicators(self) -> None:
        kinds = self._processing_kinds()
        self._syncing_transform_indicators = True
        try:
            self.plot_control_bar.axis_calibration_checkbox.setChecked(
                "axis_offset" in kinds or self._active_processing_key == "calibration"
            )
        finally:
            self._syncing_transform_indicators = False

    def _open_section_from_indicator(self, key: str) -> None:
        section = self.action_bar._preprocessing_sections[key]
        if not section.toggle.isChecked():
            section.toggle.click()
        else:
            self.action_bar._section_toggled(key, True)

    def _calibration_indicator_changed(self, checked: bool) -> None:
        if self._syncing_transform_indicators:
            return
        if checked:
            self._open_section_from_indicator("calibration")
            self._sync_transform_indicators()
            return
        self._undo_last_transform_kind("axis_offset")

    def _undo_last_transform_kind(self, kind: str) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return
        kinds = self._processing_kinds()
        if kinds and kinds[-1] == kind:
            self.cancel_processing_preview()
            self.processing_controller.undo(spectrum.id)
            self.set_active_spectrum(spectrum.id)
        else:
            self._sync_transform_indicators()
