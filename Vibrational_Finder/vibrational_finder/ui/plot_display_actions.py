from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QActionGroup
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QMenu

from vibrational_finder.preprocessing import normalize_y
from vibrational_finder.ui.spectrum_legends import PHASE_LEGEND_CHOICES, multi_legend_mode


ASPECT_RATIOS = {"1:1": 1.0, "2:1": 2.0, "4:3": 4 / 3, "16:9": 16 / 9}


def _positive_number(value, default: float) -> float:
    try:
        value = float(value)
    except (ValueError, TypeError):
        return default
    return value if math.isfinite(value) and value > 0 else default


class PlotDisplayActionsMixin:
    def _init_plot_display_actions(self) -> None:
        self.top_toolbar.plotSettingsRequested.connect(self._show_plot_settings)
        controls = self.plot_control_bar
        controls.normalize_checkbox.setChecked(self.project.ui.normalization_mode != "none")
        controls.normalizeSpectraChanged.connect(self._set_plot_normalization)
        self._sync_all_black_button()
        controls.allObservedBlackChanged.connect(
            lambda enabled: self._set_plot_layer_visible("all_observed_black", enabled)
        )
        controls.plotAspectModeChanged.connect(self._apply_plot_aspect)
        controls.spectrumDisplayModeChanged.connect(self._display_mode_changed)
        controls.spectrumOffsetPercentChanged.connect(
            lambda _percent: self._update_selected_plot(preserve_view=True)
        )
        self.project_tree.spectrum_selection_changed.connect(self._update_selected_plot)
        self._plot_layer_menu = QMenu(self.spectrum_plot)
        self._phase_legend_menu = QMenu("Phase legend", self.spectrum_plot)
        self._phase_legend_menu.setObjectName("phaseLegendMenu")
        self._phase_legend_group = QActionGroup(self._phase_legend_menu)
        self._phase_legend_group.setExclusive(True)
        self._phase_legend_actions = {}
        for code, text in PHASE_LEGEND_CHOICES:
            action = self._phase_legend_menu.addAction(text)
            action.setData(code)
            action.setCheckable(True)
            self._phase_legend_group.addAction(action)
            self._phase_legend_actions[code] = action
            action.triggered.connect(lambda _checked, mode=code: self._set_multi_legend_mode(mode))
        self.spectrum_plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.spectrum_plot.customContextMenuRequested.connect(self._show_plot_layer_menu)
        self._sync_plot_mode_controls()
        self._apply_plot_aspect()

    def _show_plot_layer_menu(self, point: QPoint) -> None:
        menu = self._plot_layer_menu
        # Detach the reusable submenu before clear(), which can delete attached actions.
        menu.removeAction(self._phase_legend_menu.menuAction())
        menu.clear()
        menu.addAction("Export publication figure…", self.request_publication_export)
        menu.addAction("Show full spectrum", self.fit_active_plot)
        menu.addSeparator()
        settings = self.project.ui.plot_view_settings
        multi = self._in_multi_spectra_mode()
        legend = menu.addAction("Spectrum names" if multi else "Legend")
        legend.setCheckable(True)
        legend.setChecked(bool(settings.get("legend_visible", True)))
        legend.toggled.connect(lambda visible: self._set_plot_layer_visible("legend_visible", visible))
        if multi:
            self._phase_legend_actions[multi_legend_mode(settings)].setChecked(True)
            menu.addMenu(self._phase_legend_menu)
        menu.addSeparator()
        for label, key, default in (
            ("Grid", "grid_visible", False),
            ("Reference profile", "layer_phase_profiles_visible", True),
            ("Reference peak lines", "layer_phase_ticks_visible", True),
            ("Phase markers", "layer_reference_peak_markers_visible", False),
            ("Reference ticks below spectrum", "layer_reference_shift_ticks_visible", True),
            ("Mode labels", "layer_reference_mode_labels_visible", True),
            ("Vibration assignments", "layer_reference_assignment_labels_visible", False),
        ):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(bool(settings.get(key, default)))
            action.toggled.connect(lambda visible, field=key: self._set_plot_layer_visible(field, visible))
        markers_only = menu.addAction("Markers only")
        markers_only.setToolTip("Show round phase markers without lines inside peaks or labels. Keep lower reference ticks as set.")
        markers_only.triggered.connect(self._show_markers_only)
        menu.popup(self.spectrum_plot.viewport().mapToGlobal(point))

    def _show_markers_only(self) -> None:
        self.project.ui.plot_view_settings.update(
            layer_reference_peak_markers_visible=True,
            layer_phase_ticks_visible=False,
            layer_reference_mode_labels_visible=False,
            layer_reference_assignment_labels_visible=False,
        )
        self.document.mark_changed()
        self._redraw_active_spectrum(preserve_view=True)

    def _set_plot_layer_visible(self, key: str, visible: bool) -> None:
        self.project.ui.plot_view_settings[key] = visible
        self.document.mark_changed()
        self._redraw_active_spectrum(preserve_view=True)

    def _sync_all_black_button(self) -> None:
        button = self.plot_control_bar.all_observed_black_button
        blocked = button.blockSignals(True)
        button.setChecked(bool(self.project.ui.plot_view_settings.get("all_observed_black", False)))
        button.blockSignals(blocked)

    def _in_multi_spectra_mode(self) -> bool:
        return self.plot_control_bar.spectrum_display_mode.currentText() == "All selected"

    def _set_multi_legend_mode(self, mode: str) -> None:
        settings = self.project.ui.plot_view_settings
        if mode != multi_legend_mode(settings):
            settings["multi_phase_legend_mode"] = mode
            self.document.mark_changed()
            self._redraw_active_spectrum(preserve_view=True)

    def _remember_spectrum_legend_position(self, spectrum_id: str | None, x: float, y: float) -> None:
        settings = self.project.ui.plot_view_settings
        if spectrum_id is None:
            settings["multi_common_legend_position"] = [x, y]
            self.document.mark_changed()
            self._reposition_band_annotations()
            return
        stored = settings.get("multi_legend_positions")
        positions = dict(stored) if isinstance(stored, dict) else {}
        if positions.get(spectrum_id) != [x, y]:
            positions[spectrum_id] = [x, y]
            settings["multi_legend_positions"] = positions
            self.document.mark_changed()
            self._reposition_band_annotations()

    def _apply_plot_aspect(self) -> None:
        mode = self.plot_control_bar.plot_aspect_mode.currentText()
        settings = self.project.ui.plot_view_settings
        aspect = ASPECT_RATIOS.get(mode)
        if mode == "Custom":
            width = _positive_number(settings.get("custom_aspect_width"), 4.0)
            height = _positive_number(settings.get("custom_aspect_height"), 2.0)
            aspect = min(100.0, max(0.01, width / height))
        self.plot_canvas.set_aspect(aspect)

    def _display_mode_changed(self) -> None:
        self._sync_plot_mode_controls()
        if self._active_processing_key is not None and self._active_processing_key != "bands":
            self.cancel_processing_preview()
        self._redraw_active_spectrum()

    def _set_plot_normalization(self, enabled: bool) -> None:
        if self._active_processing_key not in {None, "bands"}:
            self.cancel_processing_preview()
        self.project.ui.normalization_mode = "max" if enabled else "none"
        self.document.mark_changed()
        self._redraw_active_spectrum(preserve_x_range=True)

    def _display_spectrum(self, spectrum):
        if spectrum is None or not self.plot_control_bar.normalize_checkbox.isChecked():
            return spectrum
        y = np.array(spectrum.y, dtype=float)
        finite = np.isfinite(y)
        if np.any(finite):
            y[finite] = normalize_y(y[finite], "max")
        return replace(spectrum, y=y.tolist())

    def _sync_plot_mode_controls(self) -> None:
        controls = self.plot_control_bar
        controls.offset_slider.setEnabled(self._in_multi_spectra_mode())
        controls.offset_value.setText(f"{controls.offset_slider.value()}%")

    def _update_selected_plot(self, *, preserve_view: bool = False) -> None:
        if (self._in_multi_spectra_mode()
                and self._active_processing_key in {None, "bands"}):
            self._redraw_active_spectrum(preserve_view=preserve_view)

    def _spectra_for_plot(self, active):
        if not self._in_multi_spectra_mode():
            return self._display_spectrum(active), ()
        checked = set(self.project_tree.checked_spectrum_ids())
        chosen = [item for item in self._ordered_spectra() if item.id in checked]
        if not chosen:
            return None, ()
        primary = active if active is not None and active.id in checked else chosen[0]
        # Axes, units and magnitudes must agree before spectra can share a canvas.
        axes = (primary.kind, primary.x_unit, primary.y_unit)
        chosen = [item for item in chosen if (item.kind, item.x_unit, item.y_unit) == axes]
        primary_index = next(index for index, item in enumerate(chosen) if item.id == primary.id)
        chosen = [self._display_spectrum(item) for item in chosen]
        primary = chosen[primary_index]
        finite_traces = [values[np.isfinite(values)] for values in (np.asarray(item.y) for item in chosen)]
        span = max((float(np.ptp(values)) for values in finite_traces if values.size), default=0.0)
        step = (span or 1.0) * self.plot_control_bar.offset_slider.value() / 100.0
        return primary, tuple((item, (index - primary_index) * step) for index, item in enumerate(chosen)
                              if item.id != primary.id)

    def _show_plot_settings(self) -> None:
        settings = self.project.ui.plot_view_settings
        dialog = QDialog(self)
        dialog.setObjectName("spectroscopyPlotSettings")
        dialog.setWindowTitle("Plot settings")
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        form = QFormLayout(dialog)
        grid = QCheckBox("Show grid")
        grid.setObjectName("plotGrid")
        grid.setChecked(bool(settings.get("grid_visible", False)))
        title = QCheckBox("Show plot title")
        title.setObjectName("plotTitle")
        title.setChecked(bool(settings.get("title_visible", True)))
        form.addRow(grid)
        form.addRow(title)
        width, height = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (width, height):
            spin.setRange(0.1, 100.0)
            spin.setDecimals(2)
        width.setValue(_positive_number(settings.get("custom_aspect_width"), 4.0))
        height.setValue(_positive_number(settings.get("custom_aspect_height"), 2.0))
        form.addRow("Custom width", width)
        form.addRow("Custom height", height)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        form.addRow(controls)

        def apply() -> None:
            updated = {"grid_visible": grid.isChecked(), "title_visible": title.isChecked(),
                       "custom_aspect_width": width.value(), "custom_aspect_height": height.value()}
            if any(settings.get(key) != value for key, value in updated.items()):
                settings.update(updated)
                self.document.mark_changed()
            self._apply_plot_appearance()
            self._apply_plot_aspect()

        dialog.accepted.connect(apply)
        dialog.open()

    def _apply_plot_appearance(self) -> None:
        settings = self.project.ui.plot_view_settings
        grid = bool(settings.get("grid_visible", False))
        title = bool(settings.get("title_visible", True))
        self.spectrum_plot.showGrid(x=grid, y=grid, alpha=0.18)
        self.spectrum_plot.plotItem.titleLabel.setVisible(title)
        preview = self._phase_deconvolution_plot
        if preview is not None:
            visible = bool(settings.get("grid_visible", True))
            preview.main_plot.showGrid(x=visible, y=False, alpha=0.16)
            preview.difference_plot.showGrid(x=visible, y=False, alpha=0.16)
            preview.main_plot.plotItem.titleLabel.setVisible(title)
