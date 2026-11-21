from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog, QMessageBox

from vibrational_finder.plot_export.options import PlotExportFormat, PlotExportOptions
from vibrational_finder.publication_export_controller import PublicationExportController
from vibrational_finder.ui.plot_export_dialog import PlotExportDialog


_FORMAT_DETAILS = {
    PlotExportFormat.SVG: ("svg", "Layered SVG (*.svg)"),
    PlotExportFormat.PDF: ("pdf", "Vector PDF (*.pdf)"),
    PlotExportFormat.PNG: ("png", "PNG image (*.png)"),
    PlotExportFormat.JPG: ("jpg", "JPEG image (*.jpg *.jpeg)"),
}


class PublicationExportActionsMixin:
    def _init_publication_export_actions(self) -> None:
        self.publication_export_controller = PublicationExportController()
        self._last_publication_export_options: PlotExportOptions | None = None
        self.top_toolbar.exportRequested.connect(self.request_publication_export)

    def _choose_publication_export_path(self, format: PlotExportFormat) -> Path | None:
        suffix, file_filter = _FORMAT_DETAILS[format]
        directory = self._last_project_directory() or str(Path.cwd())
        path, _selected = QFileDialog.getSaveFileName(
            self,
            "Export publication figure",
            str(Path(directory) / f"ir_raman_figure.{suffix}"),
            file_filter,
        )
        if not path:
            return None
        allowed = (".jpg", ".jpeg") if format is PlotExportFormat.JPG else (f".{suffix}",)
        if not path.lower().endswith(allowed):
            path += f".{suffix}"
        return Path(path)

    def request_publication_export(self) -> None:
        if getattr(self, "_phase_deconvolution_plot", None) is not None:
            self.statusBar().showMessage("Close the deconvolution preview or save the component before exporting.", 6000)
            return
        dialog = PlotExportDialog(
            self.spectrum_plot.size(),
            self._last_publication_export_options,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        destination = self._choose_publication_export_path(options.format)
        if destination is None:
            return
        try:
            self.publication_export_controller.export(self.spectrum_plot, options, destination)
        except Exception as exc:
            QMessageBox.warning(self, "Export publication figure", f"Could not export the current plot:\n{exc}")
            return
        self._last_publication_export_options = options
        self._remember_project_directory(destination.parent)
        self.statusBar().showMessage(f"Exported publication figure: {destination}", 6000)

