from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _TransformPanel(QWidget):
    previewRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("preprocessingPanel")
        self.error_label = QLabel()
        self.error_label.setObjectName("transformErrorLabel")
        self.error_label.setStyleSheet("color: #c62828;")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

    def set_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(bool(message))

    def _button_row(self) -> QHBoxLayout:
        preview = QPushButton("Preview")
        cancel = QPushButton("Cancel")
        apply = QPushButton("OK")
        preview.clicked.connect(self.previewRequested)
        cancel.clicked.connect(self.cancelRequested)
        apply.clicked.connect(self.applyRequested)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(preview)
        row.addWidget(cancel)
        row.addWidget(apply)
        return row


class CropPanel(_TransformPanel):
    def __init__(self, x_values: list[float], unit: str = "cm-1", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lower = min(x_values)
        upper = max(x_values)
        margin = max(abs(lower), abs(upper), 1.0)
        self.minimum_spin = QDoubleSpinBox()
        self.maximum_spin = QDoubleSpinBox()
        for spin in (self.minimum_spin, self.maximum_spin):
            spin.setDecimals(6)
            spin.setRange(lower - margin, upper + margin)
        self.minimum_spin.setValue(lower)
        self.maximum_spin.setValue(upper)
        self.unit_label = QLabel(unit or "cm-1")

        form = QFormLayout()
        form.addRow("Range start", self.minimum_spin)
        form.addRow("Range end", self.maximum_spin)
        form.addRow("Axis unit", self.unit_label)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Keep points inside the selected coordinate range."))
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(self._button_row())

    def minimum(self) -> float:
        return min(float(self.minimum_spin.value()), float(self.maximum_spin.value()))

    def maximum(self) -> float:
        return max(float(self.minimum_spin.value()), float(self.maximum_spin.value()))


class NormalizationPanel(_TransformPanel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mode_combo = QComboBox()
        for label, mode in (
            ("None", "none"),
            ("Maximum", "max"),
            ("Vector norm", "vector"),
            ("Integrated area", "area"),
            ("Standard normal variate (SNV)", "snv"),
        ):
            self.mode_combo.addItem(label, mode)
        self.mode_combo.setCurrentIndex(self.mode_combo.findData("max"))
        self.mode_combo.currentIndexChanged.connect(self.previewRequested)
        form = QFormLayout()
        form.addRow("Mode", self.mode_combo)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Normalize the active spectrum using a committed project operation."))
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(self._button_row())

    def mode(self) -> str:
        return str(self.mode_combo.currentData())


class AxisCalibrationPanel(_TransformPanel):
    def __init__(self, unit: str = "cm-1", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title_label = QLabel("Constant spectral-axis offset")
        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setDecimals(6)
        self.offset_spin.setRange(-10000.0, 10000.0)
        self.offset_spin.setSingleStep(0.1)
        self.unit_label = QLabel(unit or "cm-1")
        form = QFormLayout()
        form.addRow("Offset", self.offset_spin)
        form.addRow("Axis unit", self.unit_label)
        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(QLabel("The first release applies one reversible constant offset to every x value."))
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(self._button_row())

    def offset(self) -> float:
        return float(self.offset_spin.value())
