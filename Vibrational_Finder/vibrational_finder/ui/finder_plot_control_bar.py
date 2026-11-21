from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QBoxLayout, QComboBox, QHBoxLayout, QLabel, QLayout, QSizePolicy, QSlider, QToolButton, QWidget

from finder_core.models import SignalKind
from vibrational_finder.ui.wrapping_layout import WrappingLayout


class SpectrumDisplayButton(QToolButton):
    """Two spectrum display modes with the combo-like API used by project files."""

    _MODES = ("One", "All selected")

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setProperty("plotToggle", True)
        self.setText("One spectrum")
        self.toggled.connect(self._sync_text)

    def _sync_text(self, checked: bool) -> None:
        self.setText("All selected" if checked else "One spectrum")

    def currentText(self) -> str:
        return self._MODES[int(self.isChecked())]

    def setCurrentText(self, mode: str) -> None:
        if mode in self._MODES:
            self.setChecked(mode == "All selected")
            self._sync_text(self.isChecked())

    def findText(self, mode: str) -> int:
        try:
            return self._MODES.index(mode)
        except ValueError:
            return -1

    def currentIndex(self) -> int:
        return int(self.isChecked())

    def setCurrentIndex(self, index: int) -> None:
        if index in (0, 1):
            self.setChecked(bool(index))
            self._sync_text(self.isChecked())


class FinderPlotControlBar(QWidget):
    spectrumDisplayModeChanged = Signal(str)
    plotAspectModeChanged = Signal(str)
    spectrumOffsetPercentChanged = Signal(int)
    normalizeSpectraChanged = Signal(bool)
    axisCalibrationChanged = Signal(bool)
    allObservedBlackChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("finderPlotControlBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bar_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._bar_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._bar_layout.setContentsMargins(6, 3, 6, 3)
        self._bar_layout.setSpacing(4)
        self._controls = QWidget()
        self._flow_layout = WrappingLayout(self._controls)

        self.spectrum_display_mode = SpectrumDisplayButton()
        self.spectrum_display_mode.setToolTip(
            "One: show only the active spectrum.\n"
            "All selected: show checked spectra compatible with the displayed method and units."
        )
        self.spectrum_display_mode.toggled.connect(
            lambda checked: self.spectrumDisplayModeChanged.emit("All selected" if checked else "One")
        )
        self.plot_aspect_mode = QComboBox()
        self.plot_aspect_mode.addItems(["Fit", "1:1", "2:1", "4:3", "16:9", "Custom"])
        self.plot_aspect_mode.setToolTip("Plot aspect ratio")
        self.plot_aspect_mode.currentTextChanged.connect(self.plotAspectModeChanged)
        self.normalize_checkbox = self._toggle_button("Normalize")
        self.normalize_checkbox.setToolTip("Scale each displayed spectrum to 0–1 before stacking. Does not modify the data.")
        self.normalize_checkbox.toggled.connect(self.normalizeSpectraChanged)
        self.axis_calibration_checkbox = self._toggle_button("Calibrate")
        self.axis_calibration_checkbox.setToolTip("Apply axis calibration")
        self.axis_calibration_checkbox.toggled.connect(self.axisCalibrationChanged)
        self.all_observed_black_button = self._toggle_button("All black")
        self.all_observed_black_button.setToolTip(
            "Show all experimental spectra in black. Turn off to restore their colors. "
            "Phase markers and reference curves keep their colors."
        )
        self.all_observed_black_button.toggled.connect(self.allObservedBlackChanged)
        self.offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.offset_slider.setRange(0, 150)
        self.offset_slider.setValue(10)
        self.offset_slider.setMinimumWidth(100)
        self.offset_value = QLabel("10%")
        self.offset_slider.valueChanged.connect(lambda value: self.offset_value.setText(f"{value}%"))
        self.offset_slider.valueChanged.connect(self.spectrumOffsetPercentChanged)

        groups = (
            (self.spectrum_display_mode,),
            (self.plot_aspect_mode,),
            (self.normalize_checkbox,),
            (QLabel("Offset"), self.offset_slider, self.offset_value),
            (self.axis_calibration_checkbox,),
            (self.all_observed_black_button,),
        )
        for controls in groups:
            group = QWidget()
            row = QHBoxLayout(group)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for control in controls:
                row.addWidget(control)
            self._flow_layout.addWidget(group)
        self._bar_layout.addWidget(self._controls, 1)

        self.cursor_position_status_label = QLabel()
        self.cursor_position_status_label.setObjectName("cursorReadout")
        self.cursor_position_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._bar_layout.addWidget(self.cursor_position_status_label, 0, Qt.AlignmentFlag.AlignRight)
        self.set_cursor_readout()
        for button in (
            self.spectrum_display_mode,
            self.normalize_checkbox,
            self.axis_calibration_checkbox,
            self.all_observed_black_button,
        ):
            button.toggled.connect(lambda _checked: self._update_control_layout())
        self._update_control_layout()

    @staticmethod
    def _toggle_button(text: str) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setCheckable(True)
        button.setProperty("plotToggle", True)
        return button

    def set_cursor_readout(
        self,
        *,
        position: float | None = None,
        intensity: float | None = None,
        kind: SignalKind = SignalKind.UNKNOWN,
        x_unit: str = "",
    ) -> None:
        label = "Raman shift" if kind == SignalKind.RAMAN else "Wavenumber" if kind == SignalKind.FTIR else "Position"
        unit = x_unit or "cm-1"
        if position is None or intensity is None:
            text = "x: -    I: -"
            tooltip = f"{label}: -    I: -"
        else:
            text = f"x: {position:.3f}    I: {intensity:.4g}"
            tooltip = f"{label}: {position:.3f} {unit}    I: {intensity:.4g}"
        self.cursor_position_status_label.setText(text)
        self.cursor_position_status_label.setToolTip(tooltip)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_control_layout()

    def _update_control_layout(self) -> None:
        available = max(1, self.width() - 12)
        cursor_width = self.cursor_position_status_label.sizeHint().width()
        horizontal = self._flow_layout.sizeHint().width() + cursor_width + 4 <= available
        self._bar_layout.setDirection(QBoxLayout.Direction.LeftToRight if horizontal else QBoxLayout.Direction.TopToBottom)
        controls_width = available - cursor_width - 4 if horizontal else available
        height = self._flow_layout.heightForWidth(max(1, controls_width))
        self._controls.setFixedHeight(height)
        cursor_height = self.cursor_position_status_label.sizeHint().height()
        total = (max(height, cursor_height) if horizontal else height + cursor_height + 4) + 6
        self.setFixedHeight(total)
        self.updateGeometry()
