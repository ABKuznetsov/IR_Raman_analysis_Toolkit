from __future__ import annotations

import pyqtgraph as pg
from PySide6.QtGui import QFont


class VibrationalViewBox(pg.ViewBox):
    def __init__(self) -> None:
        super().__init__(enableMenu=False)
        self.setMouseMode(pg.ViewBox.RectMode)
        self.setMouseEnabled(x=True, y=True)

    def wheelEvent(self, event, axis=None) -> None:
        delta = event.delta() if hasattr(event, "delta") else event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        center = self.mapSceneToView(event.scenePos())
        self.scaleBy(x=factor, y=1.0, center=center)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        reset_callback = getattr(self, "double_click_reset_callback", None)
        if callable(reset_callback):
            reset_callback()
        else:
            self.autoRange(padding=0.02)
        event.accept()


def create_vibrational_plot_widget() -> pg.PlotWidget:
    plot = pg.PlotWidget(viewBox=VibrationalViewBox())
    plot.setBackground("w")
    plot.showGrid(x=False, y=False)
    plot.setMenuEnabled(False)
    plot.setTitle("IR/Raman Phase Finder: spectrum and candidate markers", color="#111111", size="13pt")
    for axis_name in ("bottom", "left"):
        axis = plot.getAxis(axis_name)
        axis.setPen(pg.mkPen("#111111", width=1.2))
        axis.setTextPen(pg.mkPen("#111111"))
        axis_font = QFont()
        axis_font.setPointSize(10)
        axis.setTickFont(axis_font)
        axis.setStyle(tickTextOffset=8)
    plot.setLabel("bottom", "Wavenumber", units="cm-1", color="#111111", **{"font-size": "12pt"})
    plot.setLabel("left", "Intensity", units="a.u.", color="#111111", **{"font-size": "12pt"})
    plot.getAxis("bottom").enableAutoSIPrefix(False)
    plot.getAxis("left").enableAutoSIPrefix(False)
    return plot
