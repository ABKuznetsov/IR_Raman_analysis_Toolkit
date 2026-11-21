from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finder_core.models import SignalKind
from vibrational_finder.band_controller import BandController
from vibrational_finder.band_detection import BandDetectionOptions
from vibrational_finder.models import SpectralBand


class BandWorkspace(QWidget):
    bandSelected = Signal(int)
    bandsChanged = Signal()
    COLUMNS = (
        ("Position", "position", True),
        ("Intensity", "intensity", True),
        ("Width", "width", True),
        ("Prominence", "prominence", True),
        ("Mode", "mode", False),
        ("Assignment", "assignment", False),
        ("Symmetry", "symmetry", False),
        ("Polarization", "polarization", False),
        ("Orientation", "orientation", False),
        ("Comment", "source_comment", False),
        ("Confidence", "confidence", True),
    )

    def __init__(self, controller: BandController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.current_spectrum_id: str | None = None
        self._pending_detected: list[SpectralBand] = []
        self._row_ids: list[str] = []
        self._updating = False

        self.prominence_spin = QDoubleSpinBox()
        self.prominence_spin.setRange(0.0, 1.0)
        self.prominence_spin.setDecimals(4)
        self.prominence_spin.setValue(0.05)
        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.0, 10000.0)
        self.distance_spin.setValue(8.0)
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.0, 10000.0)
        self.max_bands_spin = QSpinBox()
        self.max_bands_spin.setRange(1, 1000)
        self.max_bands_spin.setValue(80)
        self.direction_combo = QComboBox()
        for label, value in (("Auto", "auto"), ("Positive bands", "positive"), ("Negative bands", "negative")):
            self.direction_combo.addItem(label, value)
        self.backend_combo = QComboBox()
        for label, value in (("Auto", "auto"), ("SciPy", "scipy"), ("Ramanchada2", "ramanchada2")):
            self.backend_combo.addItem(label, value)
        self.fit_peaks_checkbox = QCheckBox("Fit Raman peak profiles")

        form = QFormLayout()
        form.addRow("Minimum prominence", self.prominence_spin)
        form.addRow("Minimum distance, cm⁻¹", self.distance_spin)
        form.addRow("Minimum width, cm⁻¹", self.width_spin)
        form.addRow("Maximum bands", self.max_bands_spin)
        form.addRow("Direction", self.direction_combo)
        form.addRow("Backend", self.backend_combo)
        form.addRow(self.fit_peaks_checkbox)

        self.detect_button = QPushButton("Detect bands")
        self.apply_detected_button = QPushButton("Apply detected")
        self.apply_detected_button.setEnabled(False)
        self.add_button = QPushButton("Add manual band")
        self.delete_button = QPushButton("Delete selected")
        self.detect_button.clicked.connect(self.detect_preview)
        self.apply_detected_button.clicked.connect(self.apply_detected)
        self.add_button.clicked.connect(self.add_manual_band)
        self.delete_button.clicked.connect(self.delete_selected_band)
        buttons = QHBoxLayout()
        for button in (self.detect_button, self.apply_detected_button, self.add_button, self.delete_button):
            buttons.addWidget(button)

        self.pending_label = QLabel()
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: #c62828;")
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([item[0] for item in self.COLUMNS])
        self.table.cellChanged.connect(self._cell_changed)
        self.table.itemSelectionChanged.connect(self._selection_changed)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.pending_label)
        layout.addWidget(self.error_label)
        layout.addWidget(self.table)

    def set_spectrum(self, spectrum_id: str | None) -> None:
        self.current_spectrum_id = spectrum_id
        self._pending_detected = []
        self.apply_detected_button.setEnabled(False)
        self.pending_label.clear()
        self.error_label.clear()
        if spectrum_id is None:
            self._row_ids = []
            self._render([])
            self.setEnabled(False)
            return
        spectrum = self.controller._spectrum(spectrum_id)
        self.setEnabled(True)
        is_raman = spectrum.kind == SignalKind.RAMAN
        self.fit_peaks_checkbox.setEnabled(is_raman)
        if not is_raman:
            self.fit_peaks_checkbox.setChecked(False)
        self._row_ids = [uuid4().hex for _ in self.controller.bands(spectrum_id)]
        self._render(self.controller.bands(spectrum_id))

    def options(self) -> BandDetectionOptions:
        return BandDetectionOptions(
            min_prominence=float(self.prominence_spin.value()),
            min_distance_cm1=float(self.distance_spin.value()),
            min_width_cm1=float(self.width_spin.value()),
            max_bands=int(self.max_bands_spin.value()),
            direction=str(self.direction_combo.currentData()),
            backend=str(self.backend_combo.currentData()),
            fit_peaks=bool(self.fit_peaks_checkbox.isChecked()),
        )

    def detect_preview(self) -> None:
        if self.current_spectrum_id is None:
            return
        self._pending_detected = self.controller.detect(self.current_spectrum_id, self.options())
        self.pending_label.setText(f"Detected {len(self._pending_detected)} band(s). Apply to replace the table.")
        self.apply_detected_button.setEnabled(True)

    def apply_detected(self) -> None:
        if self.current_spectrum_id is None or not self.apply_detected_button.isEnabled():
            return
        self.controller.replace_detected(self.current_spectrum_id, self._pending_detected)
        self.set_spectrum(self.current_spectrum_id)
        self.bandsChanged.emit()

    def add_manual_band(self) -> None:
        if self.current_spectrum_id is None:
            return
        spectrum = self.controller._spectrum(self.current_spectrum_id)
        position = float(spectrum.x[len(spectrum.x) // 2]) if spectrum.x else 0.0
        self.controller.add(self.current_spectrum_id, SpectralBand(position=position, intensity=1.0))
        self._row_ids.append(uuid4().hex)
        self._render(self.controller.bands(self.current_spectrum_id))
        self.bandsChanged.emit()

    def delete_selected_band(self) -> None:
        if self.current_spectrum_id is None:
            return
        row = self.table.currentRow()
        if row < 0:
            return
        self.controller.remove(self.current_spectrum_id, row)
        self._row_ids.pop(row)
        self._render(self.controller.bands(self.current_spectrum_id))
        self.bandsChanged.emit()

    def _render(self, bands: list[SpectralBand]) -> None:
        self._updating = True
        try:
            self.table.setRowCount(len(bands))
            if len(self._row_ids) != len(bands):
                self._row_ids = [uuid4().hex for _ in bands]
            for row, band in enumerate(bands):
                for column, (_label, field, _numeric) in enumerate(self.COLUMNS):
                    item = QTableWidgetItem(str(getattr(band, field)))
                    item.setData(Qt.ItemDataRole.UserRole, self._row_ids[row])
                    self.table.setItem(row, column, item)
        finally:
            self._updating = False

    def _cell_changed(self, row: int, column: int) -> None:
        if self._updating or self.current_spectrum_id is None or not 0 <= row < len(self._row_ids):
            return
        _label, field, numeric = self.COLUMNS[column]
        item = self.table.item(row, column)
        text = item.text() if item is not None else ""
        try:
            value: object = float(text) if numeric else text
            self.controller.update(self.current_spectrum_id, row, **{field: value})
        except (TypeError, ValueError, IndexError) as exc:
            self.error_label.setText(str(exc))
            self._render(self.controller.bands(self.current_spectrum_id))
            return
        self.error_label.clear()
        item.setData(Qt.ItemDataRole.UserRole, self._row_ids[row])
        self.bandsChanged.emit()

    def _selection_changed(self) -> None:
        if not self._updating and self.table.currentRow() >= 0:
            self.bandSelected.emit(self.table.currentRow())

    def select_band_row(self, index: int) -> None:
        if not 0 <= index < self.table.rowCount():
            return
        blocker = QSignalBlocker(self.table)
        self.table.selectRow(index)
        blocker.unblock()
