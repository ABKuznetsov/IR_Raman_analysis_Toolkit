from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vibrational_finder.plot_export.options import PlotExportFormat, PlotExportOptions, SvgTextMode


class PlotExportDialog(QDialog):
    def __init__(
        self,
        canvas_size_px: QSize,
        initial_options: PlotExportOptions | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if canvas_size_px.width() <= 0 or canvas_size_px.height() <= 0:
            raise ValueError("canvas_size_px must be positive")
        self.canvas_size_px = QSize(canvas_size_px)
        self._aspect_ratio = self.canvas_size_px.width() / self.canvas_size_px.height()
        self.setWindowTitle("Publication figure export")
        self.setMinimumWidth(430)

        default_options = initial_options or PlotExportOptions.for_canvas(
            PlotExportFormat.SVG,
            canvas_width_px=self.canvas_size_px.width(),
            canvas_height_px=self.canvas_size_px.height(),
        )

        self.format_combo = QComboBox()
        for format, label in (
            (PlotExportFormat.SVG, "SVG — layered vector"),
            (PlotExportFormat.PDF, "PDF — vector"),
            (PlotExportFormat.PNG, "PNG — lossless raster"),
            (PlotExportFormat.JPG, "JPG — lossy raster"),
        ):
            self.format_combo.addItem(label, format)

        self.format_hint = QLabel()
        self.format_hint.setWordWrap(True)

        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(1.0, 2000.0)
        self.width_spin.setDecimals(2)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(default_options.width_mm)

        self.height_spin = QDoubleSpinBox()
        self.height_spin.setRange(1.0, 2000.0)
        self.height_spin.setDecimals(2)
        self.height_spin.setSuffix(" mm")
        self.height_spin.setReadOnly(True)
        self.height_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)

        self.one_to_one_button = QPushButton("1:1 canvas size (96 ppi)")
        self.pixel_size_label = QLabel()

        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 2400)
        self.dpi_spin.setValue(default_options.dpi)
        self.dpi_spin.setSuffix(" dpi")
        self.dpi_controls = self._control_row("Raster resolution", self.dpi_spin)

        self.jpeg_quality_spin = QSpinBox()
        self.jpeg_quality_spin.setRange(1, 100)
        self.jpeg_quality_spin.setValue(default_options.jpeg_quality)
        self.jpeg_quality_spin.setSuffix(" %")
        self.jpeg_controls = self._control_row("JPG quality", self.jpeg_quality_spin)

        self.svg_text_mode_combo = QComboBox()
        self.svg_text_mode_combo.addItem("Keep text editable", SvgTextMode.EDITABLE)
        self.svg_text_mode_combo.addItem("Convert text to curves", SvgTextMode.CURVES)
        text_index = self.svg_text_mode_combo.findData(default_options.svg_text_mode)
        self.svg_text_mode_combo.setCurrentIndex(max(0, text_index))
        self.svg_text_controls = self._control_row("SVG text", self.svg_text_mode_combo)

        form = QFormLayout()
        form.addRow("Format", self.format_combo)
        form.addRow("Width", self.width_spin)
        form.addRow("Height (locked)", self.height_spin)
        form.addRow("", self.one_to_one_button)
        form.addRow("Output", self.pixel_size_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.dpi_controls)
        layout.addWidget(self.jpeg_controls)
        layout.addWidget(self.svg_text_controls)
        layout.addWidget(self.format_hint)
        layout.addWidget(buttons)

        format_index = self.format_combo.findData(default_options.format)
        self.format_combo.setCurrentIndex(max(0, format_index))
        self.format_combo.currentIndexChanged.connect(self._update_controls)
        self.width_spin.valueChanged.connect(self._update_dimensions)
        self.dpi_spin.valueChanged.connect(self._update_output_size)
        self.one_to_one_button.clicked.connect(self._restore_canvas_physical_size)
        self._update_dimensions()
        self._update_controls()

    @staticmethod
    def _control_row(label: str, control: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        layout.addStretch(1)
        layout.addWidget(control)
        return row

    def _selected_format(self) -> PlotExportFormat:
        return PlotExportFormat(self.format_combo.currentData())

    def _update_dimensions(self) -> None:
        self.height_spin.setValue(self.width_spin.value() / self._aspect_ratio)
        self._update_output_size()

    def _update_output_size(self) -> None:
        options = PlotExportOptions.for_canvas(
            self._selected_format(),
            canvas_width_px=self.canvas_size_px.width(),
            canvas_height_px=self.canvas_size_px.height(),
            width_mm=self.width_spin.value(),
            dpi=self.dpi_spin.value(),
            jpeg_quality=self.jpeg_quality_spin.value(),
            svg_text_mode=SvgTextMode(self.svg_text_mode_combo.currentData()),
        )
        width, height = options.pixel_size()
        self.pixel_size_label.setText(f"{width} × {height} px at {options.dpi} dpi")

    def _update_controls(self) -> None:
        format = self._selected_format()
        is_raster = format in {PlotExportFormat.PNG, PlotExportFormat.JPG}
        self.dpi_controls.setVisible(is_raster)
        self.jpeg_controls.setVisible(format is PlotExportFormat.JPG)
        self.svg_text_controls.setVisible(format is PlotExportFormat.SVG)
        if format is PlotExportFormat.SVG:
            self.format_hint.setText(
                "Recommended for CorelDRAW: canvas geometry and physical size are preserved, "
                "with scientific objects kept in named layers."
            )
        elif format is PlotExportFormat.PDF:
            self.format_hint.setText("Vector PDF with the exact physical page size.")
        elif format is PlotExportFormat.PNG:
            self.format_hint.setText("Lossless raster rendered directly at the final resolution.")
        else:
            self.format_hint.setText("Lossy raster rendered directly at the final resolution.")
        self._update_output_size()

    def _restore_canvas_physical_size(self) -> None:
        self.width_spin.setValue(self.canvas_size_px.width() / 96.0 * 25.4)

    def options(self) -> PlotExportOptions:
        return PlotExportOptions.for_canvas(
            self._selected_format(),
            canvas_width_px=self.canvas_size_px.width(),
            canvas_height_px=self.canvas_size_px.height(),
            width_mm=self.width_spin.value(),
            dpi=self.dpi_spin.value(),
            jpeg_quality=self.jpeg_quality_spin.value(),
            svg_text_mode=SvgTextMode(self.svg_text_mode_combo.currentData()),
        )
