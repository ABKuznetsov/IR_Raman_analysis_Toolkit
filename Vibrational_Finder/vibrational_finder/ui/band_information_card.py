from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from vibrational_finder.models import ObservedSpectrum, SpectralBand


class BandInformationCard(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("bandInformationCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(260)
        self.band_index: int | None = None
        self.local_x: list[float] = []
        self.local_y: list[float] = []
        title = QLabel("Band information")
        self.close_button = QPushButton("×")
        self.close_button.setFixedWidth(28)
        self.close_button.clicked.connect(self.hide)
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.close_button)

        self.position_value = QLabel("—")
        self.local_intensity_value = QLabel("—")
        self.width_value = QLabel("—")
        self.prominence_value = QLabel("—")
        self.residual_value = QLabel("—")
        self.assignment_value = QLabel("—")
        self.confidence_value = QLabel("—")
        self.local_plot = pg.PlotWidget()
        self.local_plot.setObjectName("bandLocalProfile")
        self.local_plot.setMaximumHeight(120)
        self.local_plot.setMouseEnabled(x=False, y=False)
        self.local_plot.setMenuEnabled(False)
        self.local_plot.hideAxis("left")
        self.local_plot.hideAxis("bottom")
        form = QFormLayout()
        for label, value in (
            ("Position", self.position_value),
            ("Local intensity", self.local_intensity_value),
            ("Width", self.width_value),
            ("Prominence", self.prominence_value),
            ("Residual", self.residual_value),
            ("Assignment", self.assignment_value),
            ("Confidence", self.confidence_value),
        ):
            form.addRow(label, value)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.local_plot)
        layout.addLayout(form)
        self.hide()

    def set_band(self, spectrum: ObservedSpectrum, band: SpectralBand, index: int) -> None:
        self.band_index = int(index)
        self.position_value.setText(f"{band.position:.6g} {spectrum.x_unit or 'cm-1'}")
        self.width_value.setText(f"{band.width:.6g}")
        self.prominence_value.setText(f"{band.prominence:.6g}")
        self.assignment_value.setText(band.assignment or "—")
        self.confidence_value.setText(f"{band.confidence:.6g}")
        x = np.asarray(spectrum.x, dtype=float)
        y = np.asarray(spectrum.y, dtype=float)
        self.local_x = []
        self.local_y = []
        self.local_plot.clear()
        if not len(x) or band.position < float(np.min(x)) or band.position > float(np.max(x)):
            self.local_intensity_value.setText("Unavailable")
            self.residual_value.setText("Unavailable")
            return
        nearest = int(np.argmin(np.abs(x - band.position)))
        start = max(0, nearest - 2)
        end = min(len(x), nearest + 3)
        self.local_x = x[start:end].tolist()
        self.local_y = y[start:end].tolist()
        self.local_plot.plot(self.local_x, self.local_y, pen=pg.mkPen("#d81b60", width=1.5))
        self.local_plot.autoRange(padding=0.08)
        local_intensity = float(y[nearest])
        self.local_intensity_value.setText(f"{local_intensity:.6g}")
        self.residual_value.setText(f"{float(band.intensity) - local_intensity:.6g}")

    def show_anchored(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            self.move(max(8, parent.width() - self.width() - 18), 52)
        self.show()
        self.raise_()
