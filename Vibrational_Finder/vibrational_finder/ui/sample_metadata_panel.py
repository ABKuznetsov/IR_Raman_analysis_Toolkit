from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QLabel, QLineEdit, QPlainTextEdit, QVBoxLayout, QWidget


class SampleMetadataPanel(QWidget):
    metadataEdited = Signal(dict)

    _FIELDS = (
        ("orientation", "Orientation"),
        ("polarization", "Polarization"),
        ("instrument", "Instrument"),
        ("acquisition", "Acquisition"),
        ("laser_nm", "Laser wavelength (nm)"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sampleMetadataPanel")
        self._metadata: dict[str, str] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        self.sample_label = QLabel("No active spectrum")
        self.sample_label.setObjectName("sampleMetadataTitle")
        root.addWidget(self.sample_label)
        form = QFormLayout()
        self._edits: dict[str, QLineEdit] = {}
        for key, label in self._FIELDS:
            edit = QLineEdit()
            edit.setObjectName(f"sample_{key}")
            edit.editingFinished.connect(self.commit)
            self._edits[key] = edit
            form.addRow(label, edit)
        self.orientation_edit = self._edits["orientation"]
        self.polarization_edit = self._edits["polarization"]
        self.instrument_edit = self._edits["instrument"]
        self.acquisition_edit = self._edits["acquisition"]
        self.laser_nm_edit = self._edits["laser_nm"]
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("sample_notes")
        self.notes_edit.setMaximumHeight(110)
        self.notes_edit.textChanged.connect(self.commit)
        form.addRow("Notes", self.notes_edit)
        root.addLayout(form)
        root.addStretch(1)
        self.setEnabled(False)

    def set_metadata(self, metadata: dict[str, str], *, spectrum_name: str = "") -> None:
        self._metadata = {str(key): str(value) for key, value in metadata.items()}
        for key, edit in self._edits.items():
            blocked = edit.blockSignals(True)
            edit.setText(self._metadata.get(key, ""))
            edit.blockSignals(blocked)
        blocked = self.notes_edit.blockSignals(True)
        self.notes_edit.setPlainText(self._metadata.get("notes", ""))
        self.notes_edit.blockSignals(blocked)
        self.sample_label.setText(spectrum_name or "Active spectrum")
        self.setEnabled(True)

    def clear(self) -> None:
        self._metadata = {}
        for edit in self._edits.values():
            edit.clear()
        self.notes_edit.clear()
        self.sample_label.setText("No active spectrum")
        self.setEnabled(False)

    def metadata(self) -> dict[str, str]:
        result = dict(self._metadata)
        result.update({key: edit.text().strip() for key, edit in self._edits.items()})
        result["notes"] = self.notes_edit.toPlainText().strip()
        return result

    def commit(self) -> None:
        metadata = self.metadata()
        self._metadata = dict(metadata)
        self.metadataEdited.emit(metadata)
