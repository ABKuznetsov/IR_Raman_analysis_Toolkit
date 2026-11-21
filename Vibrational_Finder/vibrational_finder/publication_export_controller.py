from __future__ import annotations

from pathlib import Path

from vibrational_finder.plot_export.options import PlotExportOptions
from vibrational_finder.plot_export.paint_exporter import export_frozen_canvas
from vibrational_finder.plot_export.snapshot import freeze_canvas


class PublicationExportController:
    """Export the exact live modular canvas through the shared figure engine."""

    def export(self, plot, options: PlotExportOptions, destination: str | Path) -> Path:
        target = Path(destination)
        with freeze_canvas(plot) as snapshot:
            export_frozen_canvas(snapshot, options, target)
        return target

