from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from vibrational_finder.ui.plot_view_settings import CollapsibleSection


class FinderActionBar(QWidget):
    smoothRequested = Signal()
    cropRequested = Signal()
    subtractBackgroundRequested = Signal()
    phaseDeconvolutionRequested = Signal()
    despikeRequested = Signal()
    normalizeRequested = Signal()
    axisCalibrationRequested = Signal()
    detectBandsRequested = Signal()
    undoProcessingRequested = Signal()
    resetProcessingRequested = Signal()
    processingSectionCollapsed = Signal(str)

    _SECTIONS = (
        ("smooth", "Smoothing", "Configure smoothing for the active spectrum."),
        ("background", "Background", "Estimate and remove the spectral background."),
        ("phase_deconvolution", "Phase deconvolution", "Separate two known phase profiles."),
        ("crop", "Crop spectrum", "Limit the active spectral range."),
        ("despike", "Despike", "Remove narrow acquisition spikes."),
        ("normalize", "Normalization", "Configure spectrum normalization."),
        ("calibration", "Axis calibration", "Apply a reversible spectral-axis correction."),
        ("bands", "Bands", "Detect or edit spectral bands."),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.processing_scroll = QScrollArea()
        self.processing_scroll.setWidgetResizable(True)
        self.processing_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("processingBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.processing_availability_label = QLabel()
        self.processing_availability_label.setObjectName("processingAvailabilityLabel")
        self.processing_availability_label.setWordWrap(True)
        history_row = QHBoxLayout()
        self.undo_processing_button = QPushButton("Undo processing")
        self.undo_processing_button.setObjectName("undoProcessingButton")
        self.reset_processing_button = QPushButton("Reset spectrum")
        self.reset_processing_button.setObjectName("resetProcessingButton")
        self.undo_processing_button.clicked.connect(self.undoProcessingRequested)
        self.reset_processing_button.clicked.connect(self.resetProcessingRequested)
        history_row.addWidget(self.undo_processing_button)
        history_row.addWidget(self.reset_processing_button)
        layout.addWidget(self.processing_availability_label)
        layout.addLayout(history_row)
        self._preprocessing_sections: dict[str, CollapsibleSection] = {}
        self._preprocessing_hosts: dict[str, QWidget] = {}
        self._preprocessing_placeholders: dict[str, QLabel] = {}
        self._section_editors: dict[str, QWidget] = {}
        for key, title, hint in self._SECTIONS:
            host = QWidget()
            host_layout = QVBoxLayout(host)
            host_layout.setContentsMargins(8, 8, 8, 8)
            placeholder = QLabel(hint)
            placeholder.setObjectName("processingPlaceholder")
            placeholder.setWordWrap(True)
            host_layout.addWidget(placeholder)
            section = CollapsibleSection(title, host, expanded=False)
            section.toggle.clicked.connect(lambda checked, item_key=key: self._section_toggled(item_key, checked))
            self._preprocessing_sections[key] = section
            self._preprocessing_hosts[key] = host
            self._preprocessing_placeholders[key] = placeholder
            layout.addWidget(section)
        layout.addStretch(1)
        self.processing_scroll.setWidget(body)
        root.addWidget(self.processing_scroll)
        self.set_processing_available(False, "Import or select a Raman/FTIR spectrum to enable processing.")
        self.set_history_available(False, False)

    def preprocessing_section_keys(self) -> tuple[str, ...]:
        return tuple(self._preprocessing_sections)

    def section_editor(self, key: str) -> QWidget | None:
        return self._section_editors.get(key)

    def set_section_editor(self, key: str, editor: QWidget) -> None:
        self.clear_section_editor(key)
        self._preprocessing_placeholders[key].hide()
        editor.setParent(self._preprocessing_hosts[key])
        self._preprocessing_hosts[key].layout().addWidget(editor)
        self._section_editors[key] = editor
        editor.show()

    def clear_section_editor(self, key: str) -> None:
        editor = self._section_editors.pop(key, None)
        if editor is not None:
            self._preprocessing_hosts[key].layout().removeWidget(editor)
            editor.setParent(None)
            editor.deleteLater()
        self._preprocessing_placeholders[key].show()

    def set_processing_available(self, available: bool, reason: str = "") -> None:
        self.processing_availability_label.setText("" if available else reason)
        self.processing_availability_label.setVisible(not available and bool(reason))
        for section in self._preprocessing_sections.values():
            section.toggle.setEnabled(available)

    def set_history_available(self, can_undo: bool, can_reset: bool) -> None:
        self.undo_processing_button.setEnabled(can_undo)
        self.reset_processing_button.setEnabled(can_reset)

    def _section_toggled(self, key: str, checked: bool) -> None:
        if not checked:
            self.processingSectionCollapsed.emit(key)
            return
        signals = {
            "smooth": self.smoothRequested,
            "background": self.subtractBackgroundRequested,
            "phase_deconvolution": self.phaseDeconvolutionRequested,
            "crop": self.cropRequested,
            "despike": self.despikeRequested,
            "normalize": self.normalizeRequested,
            "calibration": self.axisCalibrationRequested,
            "bands": self.detectBandsRequested,
        }
        signals[key].emit()
