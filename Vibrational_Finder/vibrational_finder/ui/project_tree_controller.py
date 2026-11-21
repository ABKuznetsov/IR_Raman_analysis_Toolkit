from __future__ import annotations

from PySide6.QtCore import QObject

from vibrational_finder.project_model import observed_by_id
from vibrational_finder.project_series import ProjectSeries, assign_spectrum_to_series


class ProjectTreeController(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window

    @property
    def project(self):
        return self.window.project

    def create_series(self, name: str) -> str:
        series = ProjectSeries.create(name)
        self.project.series.append(series)
        self._changed("series", series.id)
        return series.id

    def rename_object(self, object_type: str, object_id: str, name: str) -> bool:
        clean_name = str(name).strip()
        if not clean_name:
            return False
        if object_type == "project" and object_id == self.project.project_id:
            target = self.project
            attribute = "project_name"
        elif object_type == "series":
            target = next((item for item in self.project.series if item.id == object_id), None)
            attribute = "name"
        elif object_type == "spectrum":
            target = observed_by_id(self.project).get(object_id)
            attribute = "name"
        else:
            return False
        if target is None or getattr(target, attribute) == clean_name:
            return False
        setattr(target, attribute, clean_name)
        self._changed(object_type, object_id)
        return True

    def move_spectrum_to_series(self, spectrum_id: str, series_id: str | None) -> bool:
        if spectrum_id not in observed_by_id(self.project):
            return False
        if series_id and all(item.id != series_id for item in self.project.series):
            return False
        before = [list(item.spectrum_ids) for item in self.project.series]
        assign_spectrum_to_series(self.project.series, spectrum_id, series_id)
        if before == [item.spectrum_ids for item in self.project.series]:
            return False
        self._changed("spectrum", spectrum_id)
        return True

    def reorder_object(self, object_type: str, object_id: str, direction: int) -> bool:
        if direction not in {-1, 1}:
            return False
        if object_type == "series":
            collection = self.project.series
            ids = [item.id for item in collection]
        elif object_type == "spectrum":
            collection = self.project.spectrum_order_ids
            ids = list(collection)
        else:
            return False
        if object_id not in ids:
            return False
        index = ids.index(object_id)
        target = index + direction
        if not 0 <= target < len(collection):
            return False
        collection[index], collection[target] = collection[target], collection[index]
        self._changed(object_type, object_id)
        return True

    def delete_object(self, object_type: str, object_id: str) -> bool:
        if object_type == "series":
            before = len(self.project.series)
            self.project.series = [item for item in self.project.series if item.id != object_id]
            if len(self.project.series) == before:
                return False
            self._changed()
            return True
        if object_type != "spectrum":
            return False
        spectrum = observed_by_id(self.project).get(object_id)
        if spectrum is None:
            return False
        self.project.raman_spectra = [item for item in self.project.raman_spectra if item.id != object_id]
        self.project.ftir_spectra = [item for item in self.project.ftir_spectra if item.id != object_id]
        self.project.spectrum_order_ids = [item for item in self.project.spectrum_order_ids if item != object_id]
        for series in self.project.series:
            series.remove_spectrum(object_id)
        self.project.sample_metadata.pop(object_id, None)
        self.project.sample_bands.pop(object_id, None)
        self.project.profile_states.pop(object_id, None)
        self.project.visible_observed_keys.discard(object_id)
        remaining_paths = {item.source_path for item in observed_by_id(self.project).values() if item.source_path}
        for key, original in list(self.project.original_observed.items()):
            if key == object_id or (original.id == object_id and original.source_path not in remaining_paths):
                self.project.original_observed.pop(key, None)
            elif key == spectrum.source_path and spectrum.source_path not in remaining_paths:
                self.project.original_observed.pop(key, None)
        self._changed()
        return True

    def _changed(self, object_type: str | None = None, object_id: str | None = None) -> None:
        self.project.normalize()
        self.window.document.mark_changed()
        self.window._refresh_project_tree()
        if object_type and object_id:
            self.window.project_tree.select_object(object_type, object_id)
        self.window.set_active_spectrum(self.project.active_spectrum_key)
