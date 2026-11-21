from __future__ import annotations

import re
from copy import deepcopy
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QFileDialog

from finder_core.models import SignalKind
from vibrational_finder.io.autodetect import guess_spectrum_metadata
from vibrational_finder.io.scientific_folder_import import collect_scientific_folder_groups, unique_series_name
from vibrational_finder.io.xy_loader import load_xy_spectrum, supported_spectrum_extensions
from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.project_model import normalize_project_state
from vibrational_finder.project_series import ProjectSeries, assign_spectrum_to_series


class ObservedSpectrumActionsMixin:
    """Batch import actions shared by the modular spectroscopy window."""

    last_import_failures: list[str]

    def _init_spectrum_import_actions(self) -> None:
        self.top_toolbar.importRequested.connect(self.request_import_data)
        self.setAcceptDrops(True)
        self._spectrum_drop_targets = set()
        for target in (
            self.plot_host, self.plot_canvas, self.spectrum_plot, self.spectrum_plot.viewport(),
            self.project_tree, self.project_tree.viewport(),
        ):
            self._register_spectrum_drop_target(target)

    def _register_spectrum_drop_target(self, widget) -> None:
        widget.setAcceptDrops(True)
        widget.installEventFilter(self)
        self._spectrum_drop_targets.add(widget)
        widget.destroyed.connect(lambda _object=None, target=widget: self._spectrum_drop_targets.discard(target))

    def request_import_data(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in supported_spectrum_extensions())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Raman or FTIR spectra", self._last_project_directory() or str(Path.cwd()),
            f"Spectra ({patterns});;All files (*)",
        )
        if files:
            self._remember_project_directory(Path(files[0]).parent)
            self.import_spectrum_paths([Path(path) for path in files])

    def request_import_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Import folder as spectra", self._last_project_directory() or str(Path.cwd()),
        )
        if folder:
            self._remember_project_directory(Path(folder))
            self.import_folder_paths([Path(folder)])

    @staticmethod
    def _spectral_drop_paths(event) -> list[Path]:
        suffixes = set(supported_spectrum_extensions())
        paths = []
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                try:
                    supported = path.is_dir() or (path.is_file() and path.suffix.lower() in suffixes)
                except OSError:
                    # Let the import batch report why this dropped path cannot be read.
                    supported = True
                if supported:
                    paths.append(path)
        return paths

    def _handle_spectrum_drop(self, event) -> bool:
        paths = self._spectral_drop_paths(event)
        if not paths or not (event.possibleActions() & Qt.DropAction.CopyAction):
            return False
        # Import never moves or removes the files selected in Finder.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if event.type() == QEvent.Type.Drop:
            self._import_data_paths(paths)
        return True

    def dragEnterEvent(self, event) -> None:
        if not self._handle_spectrum_drop(event):
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if not self._handle_spectrum_drop(event):
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not self._handle_spectrum_drop(event):
            super().dropEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if (event.type() in {QEvent.Type.DragEnter, QEvent.Type.DragMove, QEvent.Type.Drop}
                and watched in getattr(self, "_spectrum_drop_targets", ()) and self._handle_spectrum_drop(event)):
            return True
        return super().eventFilter(watched, event)

    def import_spectrum_paths(self, paths: Sequence[Path]) -> list[str]:
        return self._import_data_paths(paths)

    def import_folder_paths(self, paths: Sequence[Path]) -> list[str]:
        return self._import_data_paths(paths)

    def _import_data_paths(self, paths: Sequence[Path]) -> list[str]:
        self.last_import_failures = []
        imported: list[str] = []
        existing_names = [series.name for series in self.project.series]
        for raw_path in paths:
            path = Path(raw_path)
            try:
                is_folder = path.is_dir()
                groups = collect_scientific_folder_groups(path, supported_spectrum_extensions()) if is_folder else []
            except OSError as exc:
                self.last_import_failures.append(f"{path}: {exc}")
                continue
            if not is_folder:
                spectrum = self._import_observed_path(path)
                if spectrum is not None:
                    imported.append(spectrum.id)
                continue
            if not groups:
                self.last_import_failures.append(f"{path}: no supported Raman/FTIR spectra")
                continue
            for group in groups:
                series = ProjectSeries.create(unique_series_name(group.name, existing_names))
                self.project.series.append(series)
                group_ids: list[str] = []
                for path in group.paths:
                    spectrum = self._import_observed_path(path)
                    if spectrum is None:
                        continue
                    assign_spectrum_to_series(self.project.series, spectrum.id, series.id)
                    group_ids.append(spectrum.id)
                    imported.append(spectrum.id)
                if group_ids:
                    existing_names.append(series.name)
                else:
                    self.project.series.remove(series)
        self._finish_spectrum_import(imported)
        return imported

    def _import_observed_path(self, path: Path) -> ObservedSpectrum | None:
        try:
            spectrum = load_xy_spectrum(path, kind=self._kind_for_path(path))
        except Exception as exc:
            self.last_import_failures.append(f"{path}: {exc}")
            return None
        if not isinstance(spectrum, ObservedSpectrum):
            self.last_import_failures.append(f"{path}: not an observed spectrum")
            return None
        if spectrum.kind == SignalKind.FTIR:
            self.project.ftir_spectra.append(spectrum)
        else:
            spectrum.kind = SignalKind.RAMAN
            self.project.raman_spectra.append(spectrum)
        self.project.spectrum_order_ids.append(spectrum.id)
        self.project.visible_observed_keys.add(spectrum.id)
        self.project.original_observed[spectrum.id] = deepcopy(spectrum)
        return spectrum

    @staticmethod
    def _kind_for_path(path: Path) -> SignalKind:
        guess = guess_spectrum_metadata(path)
        if guess.kind != SignalKind.UNKNOWN:
            return guess.kind
        text = " ".join((path.stem.lower(), *(part.lower() for part in path.parts)))
        if "ftir" in text or "infrared" in text or re.search(r"(^|[_\-\s])ir($|[_\-\s])", text):
            return SignalKind.FTIR
        return SignalKind.RAMAN

    def _finish_spectrum_import(self, imported: list[str]) -> None:
        normalize_project_state(self.project)
        if imported and self.project.active_spectrum_key is None:
            self.project.active_spectrum_key = imported[0]
        if imported:
            self.document.mark_changed()
            self._refresh_project_tree()
            self.set_active_spectrum(self.project.active_spectrum_key)
        summary = f"Imported {len(imported)} spectrum" + ("" if len(imported) == 1 else "s")
        if self.last_import_failures:
            summary += f"; {len(self.last_import_failures)} failed"
            summary += f" — {self.last_import_failures[0]}"
        self.statusBar().showMessage(summary, 7000)

