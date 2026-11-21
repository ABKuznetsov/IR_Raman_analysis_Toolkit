from __future__ import annotations

from PySide6.QtWidgets import QInputDialog, QMessageBox

from vibrational_finder.project_series import ProjectSeries, assign_spectrum_to_series


class ProjectTreeActionsMixin:
    def _create_project_series(self) -> None:
        default_name = f"Series {len(self.project_series) + 1}"
        name, accepted = QInputDialog.getText(self, "Add series", "Name:", text=default_name)
        name = name.strip()
        if not accepted or not name:
            return
        series = ProjectSeries.create(name)
        self.project_series.append(series)
        self._refresh_project_tree()
        self.project_tree.select_object("series", series.id)

    def _move_project_object_to_series(self, object_type: str, object_id: str, series_id: str) -> None:
        if object_type != "spectrum" or self._spectrum_by_id(object_id) is None:
            return
        assign_spectrum_to_series(self.project_series, object_id, series_id or None)
        self._refresh_project_tree()
        self.project_tree.select_object("spectrum", object_id)

    def _series_id_for_new_project_object(self) -> str | None:
        return self.project_tree.current_series_id()

    def _rename_project_object(self, object_type: str, object_id: str) -> None:
        if object_type == "project" and object_id == self.project_id:
            current_name = self.project_name
        elif object_type == "series":
            current = next((item for item in self.project_series if item.id == object_id), None)
            current_name = current.name if current is not None else ""
        elif object_type == "spectrum":
            current = self._spectrum_by_id(object_id)
            current_name = current.name if current is not None else ""
        else:
            return
        if not current_name:
            return
        name, accepted = QInputDialog.getText(self, "Rename", "Name:", text=current_name)
        name = name.strip()
        if not accepted or not name or name == current_name:
            return
        if object_type == "project":
            self.project_name = name
        elif object_type == "series":
            current.name = name
        else:
            current.name = name
            self._refresh_sample_card()
        self._refresh_project_tree()
        self.project_tree.select_object(object_type, object_id)
        self._redraw_plot()

    def _delete_project_object(self, object_type: str, object_id: str) -> None:
        if object_type == "series":
            self._delete_project_series(object_id)
            return
        if object_type != "spectrum":
            return
        spectrum = self._spectrum_by_id(object_id)
        if spectrum is None:
            return
        answer = QMessageBox.question(
            self,
            "Delete spectrum",
            f"Delete spectrum '{spectrum.name}' from this project?\n\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._remove_spectrum_by_id(object_id)

    def _delete_project_series(self, series_id: str) -> None:
        series = next((item for item in self.project_series if item.id == series_id), None)
        if series is None:
            return
        detail = f"\n\n{len(series.spectrum_ids)} spectrum/spectra will remain under 'No series'." if series.spectrum_ids else ""
        answer = QMessageBox.question(
            self,
            "Delete series",
            f"Delete series '{series.name}'?{detail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.project_series = [item for item in self.project_series if item.id != series_id]
            self._refresh_project_tree()

    def _move_current_tree_object(self, direction: int) -> None:
        current = self.project_tree.current_object()
        if current is None or direction not in {-1, 1}:
            return
        object_type, object_id = current
        if object_type == "series":
            ids = [item.id for item in self.project_series]
            index = ids.index(object_id)
            target = index + direction
            if 0 <= target < len(self.project_series):
                self.project_series[index], self.project_series[target] = self.project_series[target], self.project_series[index]
        elif object_type == "spectrum":
            index = self.spectrum_order_ids.index(object_id)
            target = index + direction
            if 0 <= target < len(self.spectrum_order_ids):
                self.spectrum_order_ids[index], self.spectrum_order_ids[target] = self.spectrum_order_ids[target], self.spectrum_order_ids[index]
            else:
                return
        else:
            return
        self._refresh_project_tree()
        self.project_tree.select_object(object_type, object_id)
        self._redraw_plot()
