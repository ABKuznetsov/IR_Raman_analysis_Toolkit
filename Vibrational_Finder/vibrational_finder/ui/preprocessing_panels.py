from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


BACKGROUND_METHOD_LABELS = {
    "auto": "arPLS (auto)",
    "arpls": "arPLS",
    "asls": "AsLS",
    "snip": "SNIP",
    "rolling_ball": "rolling ball",
}


def background_method_label(method: str, degree: int | None = None) -> str:
    if method == "polynomial":
        return f"polynomial {degree}" if degree is not None else "polynomial"
    return BACKGROUND_METHOD_LABELS.get(method, method)


def preprocessing_panel_style(dark: bool = False) -> str:
    if dark:
        panel = "#202124"
        text = "#f1f3f4"
        input_bg = "#2b2f34"
        button_bg = "#33383e"
        border = "#4a5057"
        hover = "#4aa3df"
        slider = "#4a5057"
        tick = "#8c96a3"
    else:
        panel = "#ffffff"
        text = "#111827"
        input_bg = "#f8fafc"
        button_bg = "#e5e7eb"
        border = "#cbd5e1"
        hover = "#2563eb"
        slider = "#d1d5db"
        tick = "#6b7280"
    return (
        f"QWidget#preprocessingPanel {{ background-color: {panel}; border: 1px solid {border}; border-radius: 6px; }}"
        f"QLabel {{ color: {text}; }}"
        f"QComboBox, QDoubleSpinBox {{ background: {input_bg}; color: {text}; border: 1px solid {border}; padding: 3px; }}"
        f"QPushButton {{ background: {button_bg}; color: {text}; border: 1px solid {border}; border-radius: 4px; padding: 5px 12px; }}"
        f"QPushButton:hover {{ border-color: {hover}; }}"
        f"QSlider::groove:horizontal {{ height: 5px; background: {slider}; border-radius: 2px; }}"
        f"QSlider::handle:horizontal {{ width: 15px; margin: -5px 0; border-radius: 7px; background: {hover}; }}"
        f"QSlider::tick:horizontal {{ background: {tick}; width: 1px; }}"
    )


class _OddWindowMixin:
    def _odd(self, value: int) -> int:
        value = max(3, int(value))
        return value if value % 2 else value + 1


class _SliderRow(QWidget):
    released = Signal()

    def __init__(self, minimum: int, maximum: int, value: int, suffix: str = "", parent=None) -> None:
        super().__init__(parent)
        self._suffix = suffix
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(max(1, (maximum - minimum) // 8))
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(58)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.slider.valueChanged.connect(self._update_label)
        self.slider.sliderReleased.connect(self.released)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.value_label)
        self._update_label(value)

    def value(self) -> int:
        return int(self.slider.value())

    def set_value(self, value: int) -> None:
        self.slider.setValue(int(value))
        self._update_label(int(value))

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802
        super().setEnabled(enabled)
        self.slider.setEnabled(enabled)
        self.value_label.setEnabled(enabled)

    def _update_label(self, value: int) -> None:
        self.value_label.setText(f"{int(value)}{self._suffix}")


class _PanelButtonsMixin:
    previewRequested: Signal
    applyRequested: Signal
    cancelRequested: Signal

    def _button_row(self) -> QHBoxLayout:
        auto_button = QPushButton("Auto")
        cancel_button = QPushButton("Cancel")
        ok_button = QPushButton("OK")
        auto_button.clicked.connect(self.apply_auto)
        cancel_button.clicked.connect(self.cancelRequested)
        ok_button.clicked.connect(self.applyRequested)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(auto_button)
        row.addWidget(cancel_button)
        row.addWidget(ok_button)
        return row


class SmoothPanel(QWidget, _OddWindowMixin, _PanelButtonsMixin):
    previewRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, default_window: int, parent=None) -> None:
        super().__init__(parent)
        self._default_window = min(self._odd(default_window), 101)
        self.setObjectName("preprocessingPanel")
        self.setMinimumWidth(480)

        self._method = QComboBox()
        self._method.addItem("Savitzky-Golay", "savgol")
        self._method.addItem("Moving average", "moving")
        self._method.addItem("Gaussian", "gaussian")
        self._window = _SliderRow(3, 101, self._default_window)
        self._window.slider.setSingleStep(2)
        self._window.slider.setPageStep(10)
        self._polyorder = QComboBox()
        for order in (2, 3, 4, 5):
            self._polyorder.addItem(str(order), order)
        self._strength = _SliderRow(1, 50, 10)
        self._strength.setToolTip("Gaussian sigma x 10; used only for Gaussian smoothing.")
        self._passes = QComboBox()
        for passes in (1, 2, 3):
            self._passes.addItem(str(passes), passes)

        self._method.currentIndexChanged.connect(self._method_changed)
        self._window.released.connect(self.previewRequested)
        self._strength.released.connect(self.previewRequested)
        self._passes.currentIndexChanged.connect(self.previewRequested)
        self._polyorder.currentIndexChanged.connect(self.previewRequested)

        form = QFormLayout()
        form.addRow("Function", self._method)
        form.addRow("Window (points)", self._window)
        form.addRow("Polynomial order", self._polyorder)
        form.addRow("Gaussian sigma", self._strength)
        form.addRow("Passes", self._passes)

        hint = QLabel("Small windows preserve narrow Raman bands. Preview is calculated from the spectrum state captured when this panel opened.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa4af;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Smooth the active Raman/FTIR spectrum."))
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(self._button_row())
        self._method_changed(emit_preview=False)

    def _method_changed(self, *_args, emit_preview: bool = True) -> None:
        method = self.method()
        self._polyorder.setEnabled(method == "savgol")
        self._strength.setEnabled(method == "gaussian")
        if emit_preview:
            self.previewRequested.emit()

    def apply_auto(self) -> None:
        blockers = [
            QSignalBlocker(self._method),
            QSignalBlocker(self._window.slider),
            QSignalBlocker(self._polyorder),
            QSignalBlocker(self._strength.slider),
            QSignalBlocker(self._passes),
        ]
        self._method.setCurrentIndex(0)
        self._window.set_value(self._default_window)
        self._polyorder.setCurrentIndex(0)
        self._strength.set_value(10)
        self._passes.setCurrentIndex(0)
        for blocker in blockers:
            blocker.unblock()
        self._method_changed(emit_preview=False)
        self.previewRequested.emit()

    def method(self) -> str:
        return str(self._method.currentData())

    def window_size(self) -> int:
        return self._odd(self._window.value())

    def polyorder(self) -> int:
        return int(self._polyorder.currentData())

    def gaussian_sigma(self) -> float:
        return max(0.1, self._strength.value() / 10.0)

    def passes(self) -> int:
        return max(1, int(self._passes.currentData()))


class BackgroundRemovalPanel(QWidget, _PanelButtonsMixin):
    previewRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, default_degree: int = 10, parent=None) -> None:
        super().__init__(parent)
        self._default_degree = int(default_degree)
        self.setObjectName("preprocessingPanel")
        self.setMinimumWidth(500)

        self._method = QComboBox()
        self._method.addItem("Auto (arPLS)", "auto")
        self._method.addItem("arPLS", "arpls")
        self._method.addItem("AsLS", "asls")
        self._method.addItem("SNIP", "snip")
        self._method.addItem("Rolling ball", "rolling_ball")
        self._method.addItem("Polynomial", "polynomial")
        self._method.addItem("Constant floor", "constant")
        self._lambda_power = _SliderRow(2, 10, 6)
        self._asymmetry = QDoubleSpinBox()
        self._asymmetry.setRange(0.001, 0.5)
        self._asymmetry.setDecimals(3)
        self._asymmetry.setSingleStep(0.005)
        self._asymmetry.setValue(0.01)
        self._half_window = _SliderRow(2, 300, 40)
        self._degree = _SliderRow(2, 30, self._default_degree)
        self._floor = _SliderRow(0, 40, 15, "%")

        self._method.currentIndexChanged.connect(self._method_changed)
        self._lambda_power.released.connect(self.previewRequested)
        self._asymmetry.editingFinished.connect(self.previewRequested)
        self._half_window.released.connect(self.previewRequested)
        self._degree.released.connect(self.previewRequested)
        self._floor.released.connect(self.previewRequested)

        form = QFormLayout()
        form.addRow("Function", self._method)
        form.addRow("Smoothness log10(lambda)", self._lambda_power)
        form.addRow("AsLS asymmetry", self._asymmetry)
        form.addRow("Half window (points)", self._half_window)
        form.addRow("Polynomial degree", self._degree)
        form.addRow("Floor percentile", self._floor)

        hint = QLabel("Auto estimates arPLS smoothness from spectrum length. Manual controls are enabled only for methods that use them.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa4af;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Subtract the background from the active spectrum."))
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(self._button_row())
        self._method_changed(emit_preview=False)

    def _method_changed(self, *_args, emit_preview: bool = True) -> None:
        method = self.method()
        self._lambda_power.setEnabled(method in {"arpls", "asls"})
        self._asymmetry.setEnabled(method == "asls")
        self._half_window.setEnabled(method in {"snip", "rolling_ball"})
        self._degree.setEnabled(method == "polynomial")
        self._floor.setEnabled(method == "constant")
        if emit_preview:
            self.previewRequested.emit()

    def apply_auto(self) -> None:
        blockers = [
            QSignalBlocker(self._method),
            QSignalBlocker(self._lambda_power.slider),
            QSignalBlocker(self._asymmetry),
            QSignalBlocker(self._half_window.slider),
            QSignalBlocker(self._degree.slider),
            QSignalBlocker(self._floor.slider),
        ]
        self._method.setCurrentIndex(0)
        self._lambda_power.set_value(6)
        self._asymmetry.setValue(0.01)
        self._half_window.set_value(40)
        self._degree.set_value(self._default_degree)
        self._floor.set_value(15)
        for blocker in blockers:
            blocker.unblock()
        self._method_changed(emit_preview=False)
        self.previewRequested.emit()

    def method(self) -> str:
        return str(self._method.currentData())

    def lambda_value(self) -> float | None:
        return None if self.method() == "auto" else 10.0 ** self._lambda_power.value()

    def asymmetry(self) -> float:
        return float(self._asymmetry.value())

    def half_window(self) -> int:
        return int(self._half_window.value())

    def degree(self) -> int:
        return int(self._degree.value())

    def floor_percentile(self) -> int:
        return int(self._floor.value())


class DespikePanel(QWidget, _OddWindowMixin, _PanelButtonsMixin):
    previewRequested = Signal()
    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("preprocessingPanel")
        self.setMinimumWidth(460)

        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(2.0, 30.0)
        self._threshold.setDecimals(1)
        self._threshold.setSingleStep(0.5)
        self._threshold.setValue(8.0)
        self._max_width = QComboBox()
        for width in range(1, 7):
            self._max_width.addItem(str(width), width)
        self._max_width.setCurrentIndex(1)
        self._median_window = _SliderRow(3, 21, 5)
        self._median_window.slider.setSingleStep(2)
        self._passes = QComboBox()
        for passes in (1, 2, 3):
            self._passes.addItem(str(passes), passes)

        self._threshold.editingFinished.connect(self.previewRequested)
        self._max_width.currentIndexChanged.connect(self.previewRequested)
        self._median_window.released.connect(self.previewRequested)
        self._passes.currentIndexChanged.connect(self.previewRequested)

        form = QFormLayout()
        form.addRow("Noise threshold", self._threshold)
        form.addRow("Maximum spike width", self._max_width)
        form.addRow("Median window (points)", self._median_window)
        form.addRow("Passes", self._passes)

        hint = QLabel("Only narrow positive spikes are replaced. Broader Raman and FTIR bands are preserved.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9aa4af;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(QLabel("Remove cosmic-ray and detector spikes."))
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(self._button_row())

    def apply_auto(self) -> None:
        blockers = [
            QSignalBlocker(self._threshold),
            QSignalBlocker(self._max_width),
            QSignalBlocker(self._median_window.slider),
            QSignalBlocker(self._passes),
        ]
        self._threshold.setValue(8.0)
        self._max_width.setCurrentIndex(1)
        self._median_window.set_value(5)
        self._passes.setCurrentIndex(0)
        for blocker in blockers:
            blocker.unblock()
        self.previewRequested.emit()

    def threshold(self) -> float:
        return float(self._threshold.value())

    def max_width(self) -> int:
        return int(self._max_width.currentData())

    def median_window(self) -> int:
        return self._odd(self._median_window.value())

    def passes(self) -> int:
        return max(1, int(self._passes.currentData()))
