from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from vibrational_finder.io import load_project, save_project
from vibrational_finder.project_gui_bridge import project_open_filter, project_save_filter, project_save_path
from vibrational_finder.project_state import VibrationalProjectState


LAST_PROJECT_DIRECTORY_KEY = "project/last_directory"


class ProjectDocumentActionsMixin:
    """Dialog-free project lifecycle used by the modular spectroscopy window."""

    def new_project(self) -> None:
        self.apply_project_state(VibrationalProjectState(), path=None)

    def request_new_project(self) -> bool:
        if not self._confirm_document_replacement("create a new project"):
            return False
        self.new_project()
        return True

    def request_open_project(self) -> bool:
        if not self._confirm_document_replacement("open another project"):
            return False
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Open IR/Raman project",
            self._last_project_directory(),
            project_open_filter(),
        )
        if not path:
            return False
        source = Path(path)
        try:
            self.open_project_path(source)
        except Exception as exc:
            QMessageBox.warning(self, "Open project", f"Could not open project:\n{source}\n\n{exc}")
            return False
        self._remember_project_directory(source.parent)
        self.statusBar().showMessage(f"Project opened: {source}", 8000)
        return True

    def request_save_project(self) -> bool:
        target = self.document.path
        if target is None:
            default = Path(self._last_project_directory()) / "ir_raman_project.irff"
            path, _selected_filter = QFileDialog.getSaveFileName(
                self,
                "Save IR/Raman project",
                str(default),
                project_save_filter(),
            )
            if not path:
                return False
            target = Path(project_save_path(path))
        try:
            saved = self.save_project_path(target)
        except Exception as exc:
            QMessageBox.warning(self, "Save project", f"Could not save project:\n{target}\n\n{exc}")
            return False
        self._remember_project_directory(saved.parent)
        self.statusBar().showMessage(f"Project saved: {saved}", 8000)
        return True

    def open_project_path(self, path: Path) -> VibrationalProjectState:
        source = Path(path)
        restored = load_project(source)
        self.apply_project_state(restored, path=source)
        return self.project

    def save_project_path(self, path: Path | None = None) -> Path:
        target = Path(path) if path is not None else self.document.path
        if target is None:
            raise ValueError("A project path is required for the first save.")
        state = self.collect_project_state()
        saved = save_project(state, target)
        self.document.mark_saved(saved)
        return saved

    def collect_project_state(self) -> VibrationalProjectState:
        state = self.project
        state.active_spectrum_key = self.active_spectrum().id if self.active_spectrum() is not None else None
        state.visible_observed_keys = set(self.project_tree.checked_spectrum_ids())
        state.ui.display_mode = self.plot_control_bar.spectrum_display_mode.currentText()
        state.ui.multi_offset = self.plot_control_bar.offset_slider.value()
        state.ui.normalization_mode = "max" if self.plot_control_bar.normalize_checkbox.isChecked() else "none"
        plot_settings = deepcopy(state.ui.plot_view_settings)
        plot_settings["aspect_mode"] = self.plot_control_bar.plot_aspect_mode.currentText()
        state.ui.plot_view_settings = plot_settings
        state.ui.tree_expansion_state = self.project_tree.expansion_state()
        state.normalize()
        self.document.state = state
        return state

    def apply_project_state(self, state: VibrationalProjectState, *, path: Path | None = None) -> None:
        restored = deepcopy(state)
        self.document.replace_state(restored, path=path)
        self.project = self.document.state
        if hasattr(self, "_analysis_project_replaced"):
            self._analysis_project_replaced()

        ui = self.project.ui
        self._set_combo_text(self.plot_control_bar.spectrum_display_mode, ui.display_mode)
        self._set_combo_text(
            self.plot_control_bar.plot_aspect_mode,
            str(ui.plot_view_settings.get("aspect_mode", "Fit")),
        )
        self._set_slider_value(self.plot_control_bar.offset_slider, max(0, min(int(ui.multi_offset), 150)))
        self._sync_plot_mode_controls()
        blocked = self.plot_control_bar.normalize_checkbox.blockSignals(True)
        self.plot_control_bar.normalize_checkbox.setChecked(ui.normalization_mode != "none")
        self.plot_control_bar.normalize_checkbox.blockSignals(blocked)
        self._sync_all_black_button()

        self._refresh_project_tree()
        self.project_tree.set_checked_spectrum_ids(list(self.project.visible_observed_keys))
        self.project_tree.restore_expansion_state(ui.tree_expansion_state)
        self._apply_plot_aspect()
        self.set_active_spectrum(self.project.active_spectrum_key)
        self.setWindowTitle(f"IR/Raman Phase Finder — {self.project.project_name}")

    def _confirm_document_replacement(self, action: str) -> bool:
        if not self.document.dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved project",
            f"Save changes before you {action}?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.request_save_project()
        return choice == QMessageBox.StandardButton.Discard

    def _last_project_directory(self) -> str:
        return self.workspace_preferences.settings.value(LAST_PROJECT_DIRECTORY_KEY, "", type=str)

    def _remember_project_directory(self, directory: Path) -> None:
        self.workspace_preferences.settings.setValue(LAST_PROJECT_DIRECTORY_KEY, str(directory))
        self.workspace_preferences.settings.sync()

    @staticmethod
    def _set_combo_text(combo, value: str) -> None:
        index = combo.findText(value)
        if index < 0:
            return
        blocked = combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(blocked)

    @staticmethod
    def _set_slider_value(slider, value: int) -> None:
        blocked = slider.blockSignals(True)
        slider.setValue(value)
        slider.blockSignals(blocked)
