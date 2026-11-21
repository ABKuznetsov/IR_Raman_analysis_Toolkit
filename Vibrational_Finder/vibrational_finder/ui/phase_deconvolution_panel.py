from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from vibrational_finder.models import ObservedSpectrum


class PhaseDeconvolutionPanel(QWidget):
    fitRequested = Signal()
    referencesChanged = Signal()
    contributionChanged = Signal()
    differenceToggled = Signal(bool)
    saveRequested = Signal()
    saveDifferenceRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, references: list[ObservedSpectrum]) -> None:
        super().__init__()
        self.main_reference = QComboBox()
        self.additional_reference = QComboBox()
        for combo in (self.main_reference, self.additional_reference):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
            combo.addItem("Select a spectrum…", None)
            for spectrum in references:
                combo.addItem(spectrum.name or spectrum.id, spectrum.id)
            combo.currentIndexChanged.connect(self._references_changed)
            combo.setEnabled(len(references) >= 2)

        self.fit_button = QPushButton("Auto fit")
        self.fit_button.clicked.connect(self.fitRequested)
        self.show_difference = QCheckBox("Show difference")
        self.show_difference.setChecked(True)
        self.show_difference.toggled.connect(self.differenceToggled)
        self.contribution_slider = QSlider(Qt.Orientation.Horizontal)
        self.contribution_slider.setRange(0, 200)
        self.contribution_slider.setPageStep(10)
        self.contribution_slider.setValue(100)
        self.contribution_slider.setAccessibleName("Additional phase contribution")
        self.contribution_slider.setToolTip("Percent of the fitted spectral contribution, not phase abundance.")
        self.contribution_label = QLabel("100%")
        self.contribution_slider.valueChanged.connect(self._contribution_changed)
        contribution = QHBoxLayout()
        contribution.addWidget(self.contribution_slider, 1)
        contribution.addWidget(self.contribution_label)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.save_button = QPushButton("Save component")
        self.save_button.clicked.connect(self.saveRequested)
        self.save_difference_button = QPushButton("Save difference")
        self.save_difference_button.setToolTip("Save the measured minus calculated spectrum, including negative values.")
        self.save_difference_button.clicked.connect(self.saveDifferenceRequested)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.cancelRequested)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        selectors = QFormLayout()
        selectors.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        selectors.addRow("Main phase", self.main_reference)
        selectors.addRow("Additional phase", self.additional_reference)
        selectors.addRow("Contribution", contribution)
        layout.addLayout(selectors)
        controls = QHBoxLayout()
        controls.addWidget(self.fit_button)
        controls.addWidget(self.show_difference)
        controls.addStretch(1)
        controls.addWidget(close_button)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.save_button)
        actions.addWidget(self.save_difference_button)
        layout.addLayout(actions)
        self._references_changed()
        if len(references) < 2:
            self.set_status("Import two compatible reference spectra into the project.")

    def reference_ids(self) -> tuple[str | None, str | None]:
        return self.main_reference.currentData(), self.additional_reference.currentData()

    def multiplier(self) -> float:
        return self.contribution_slider.value() / 100.0

    def set_status(self, message: str) -> None:
        self.status.setText(message)
        self.status.setVisible(bool(message))

    def set_fit_available(self, available: bool, *, component_available: bool = True) -> None:
        self.contribution_slider.setEnabled(available and component_available)
        self.show_difference.setEnabled(available)
        self.save_button.setEnabled(available and component_available)
        self.save_difference_button.setEnabled(available)

    def reset_multiplier(self) -> None:
        with QSignalBlocker(self.contribution_slider):
            self.contribution_slider.setValue(100)
        self.contribution_label.setText("100%")

    def _references_changed(self) -> None:
        main, extra = self.reference_ids()
        ready = main is not None and extra is not None and main != extra
        self.fit_button.setEnabled(ready)
        self.set_fit_available(False)
        self.set_status("Choose two different reference spectra." if not ready else "")
        self.referencesChanged.emit()

    def _contribution_changed(self, percent: int) -> None:
        self.contribution_label.setText(f"{percent}%")
        self.contributionChanged.emit()
