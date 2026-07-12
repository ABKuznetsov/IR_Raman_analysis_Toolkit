from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields

from PySide6.QtCore import QSettings, Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from vibrational_finder.ui.plot_style import PlotLineStyle, PlotMarkerStyle, PlotStyle


@dataclass(slots=True)
class PlotViewSettings:
    title_visible: bool = True
    title_text: str = "IR/Raman Phase Finder: spectrum and candidate markers"
    title_font_size: int = 13
    title_color: str = "#111111"
    aspect_ratio: float | None = None
    custom_aspect_width: float = 4.0
    custom_aspect_height: float = 2.0
    plot_background: str = "#ffffff"
    plot_border_visible: bool = True
    plot_border_color: str = "#111111"
    plot_border_width: int = 1
    label_font_size: int = 12
    tick_font_size: int = 10
    axis_color: str = "#111111"
    axis_width: float = 1.2
    tick_length: int = 5
    x_major_tick_spacing: float = 0.0
    x_minor_tick_spacing: float = 0.0
    y_major_tick_spacing: float = 0.0
    y_minor_tick_spacing: float = 0.0
    x_display_unit: str = "cm-1"
    bottom_axis_visible: bool = True
    bottom_axis_values_visible: bool = True
    bottom_axis_label_visible: bool = True
    bottom_axis_scale: str = "wavenumber"
    bottom_axis_label: str = "Wavenumber"
    bottom_axis_unit: str = "cm-1"
    top_axis_visible: bool = False
    top_axis_values_visible: bool = True
    top_axis_label_visible: bool = True
    top_axis_scale: str = "wavenumber"
    top_axis_label: str = "Wavenumber"
    top_axis_unit: str = "cm-1"
    left_axis_visible: bool = True
    left_axis_values_visible: bool = True
    left_axis_label_visible: bool = True
    left_axis_label: str = "Intensity"
    left_axis_unit: str = "a.u."
    right_axis_visible: bool = False
    right_axis_values_visible: bool = True
    right_axis_label_visible: bool = True
    right_axis_label: str = "Intensity"
    right_axis_unit: str = "a.u."
    grid_visible: bool = True
    grid_color: str = "#8f969e"
    grid_width: float = 0.7
    grid_alpha: float = 0.18
    legend_visible: bool = True
    legend_font_size: int = 10
    legend_color: str = "#111111"
    cursor_vertical_line_visible: bool = False
    hkl_labels_visible: bool = False
    layer_observed_visible: bool = True
    layer_preview_peak_positions_visible: bool = True
    layer_total_profile_visible: bool = True
    layer_phase_profiles_visible: bool = True
    layer_background_visible: bool = True
    layer_phase_ticks_visible: bool = True
    layer_coverage_markers_visible: bool = True
    layer_peak_labels_visible: bool = False
    layer_unknown_peaks_visible: bool = True
    observed_color: str = "#202124"
    calculated_color: str = "#0b8043"
    background_color: str = "#9aa0a6"
    reference_color: str = "#1a73e8"
    observed_width: float = 1.35
    calculated_width: float = 1.6
    marker_size: int = 7
    marker_shape: str = "Circle"


_MARKER_SYMBOLS = {
    "Circle": "o",
    "Triangle": "t",
    "Diamond": "d",
    "Square": "s",
}


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


def plot_style_from_view_settings(settings: PlotViewSettings) -> PlotStyle:
    marker_symbol = _MARKER_SYMBOLS.get(settings.marker_shape, "o")
    return PlotStyle(
        observed=PlotLineStyle(width=settings.observed_width, color=settings.observed_color),
        calculated=PlotLineStyle(width=settings.calculated_width, color=settings.calculated_color),
        phase=PlotLineStyle(width=max(settings.calculated_width - 0.1, 0.5)),
        background=PlotLineStyle(width=max(settings.calculated_width - 0.7, 0.5), color=settings.background_color),
        reference=PlotLineStyle(width=settings.calculated_width, color=settings.reference_color),
        stick=PlotLineStyle(width=max(settings.calculated_width + 1.1, 0.5)),
        marker=PlotMarkerStyle(size=settings.marker_size, symbol=marker_symbol),
    )


class CollapsibleSection(QWidget):
    def __init__(self, title: str, content: QWidget, expanded: bool = True, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("viewSection")
        self.toggle = QToolButton()
        self.toggle.setObjectName("viewSectionHeader")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggle.setMinimumHeight(30)
        self.toggle.clicked.connect(self._set_expanded)

        self.content = content
        self.content.setObjectName("viewSectionContent")
        self.content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)

    def _set_expanded(self, expanded: bool) -> None:
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.content.setVisible(expanded)


class PlotViewSettingsWidget(QScrollArea):
    settingsChanged = Signal(object)
    xAxisUnitChanged = Signal(str)
    referenceViewChanged = Signal(str)
    profileCandidateColorRequested = Signal(int)
    _DEFAULT_SETTINGS_KEY = "plot_view/default_settings"

    _ASPECTS = {
        "Fit": None,
        "1:1": 1.0,
        "2:1": 2.0,
        "4:2": 2.0,
        "Vertical 4:2": 0.5,
        "18:6": 3.0,
        "16:9": 16.0 / 9.0,
        "4:3": 4.0 / 3.0,
        "Custom": None,
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setObjectName("plotViewSettings")

        container = QWidget()
        container.setObjectName("plotViewSettingsBody")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("plotViewTabs")
        self.tabs.addTab(self._graph_tab(), "Graph")
        self.tabs.addTab(self._profile_tab(), "Profile")
        layout.addWidget(self.tabs, 1)

        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        reset_button = QPushButton("Reset view")
        reset_button.setObjectName("viewResetButton")
        reset_button.clicked.connect(self.reset)
        save_default_button = QPushButton("Save as default")
        save_default_button.setObjectName("saveDefaultButton")
        save_default_button.clicked.connect(self.save_as_default)
        factory_reset_button = QPushButton("Factory reset")
        factory_reset_button.setObjectName("factoryResetButton")
        factory_reset_button.clicked.connect(self.factory_reset)
        button_layout.addWidget(reset_button)
        button_layout.addWidget(save_default_button)
        button_layout.addWidget(factory_reset_button)
        layout.addWidget(button_row)
        layout.addStretch(1)
        self.setWidget(container)
        self.setStyleSheet(
            """
            QScrollArea#plotViewSettings {
                background: #24282d;
                border: 0;
            }
            QWidget#plotViewSettingsBody {
                background: #24282d;
            }
            QWidget#viewSection {
                background: #20252b;
                border: 1px solid #3d4651;
                border-radius: 4px;
            }
            QToolButton#viewSectionHeader {
                background: #4a4f55;
                color: #eef2f7;
                border: 0;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                padding: 5px 8px;
                font-weight: 700;
                text-align: left;
            }
            QWidget#viewSectionContent {
                background: #20252b;
                color: #e5e7eb;
            }
            QTabWidget#plotViewTabs::pane {
                border: 1px solid #3d4651;
                background: #20252b;
            }
            QTabBar::tab {
                background: #303740;
                color: #d7dde5;
                padding: 6px 12px;
                border: 1px solid #3d4651;
                border-bottom: 0;
            }
            QTabBar::tab:selected {
                background: #4a4f55;
                color: #ffffff;
                font-weight: 700;
            }
            QLabel#activeProfileLabel {
                background: #151a20;
                border: 1px solid #3d4651;
                border-radius: 4px;
                color: #eaf2ff;
                padding: 8px;
                font-weight: 700;
            }
            QTableWidget#profileCandidateTable {
                background: #1b2026;
                color: #eef2f7;
                gridline-color: #3d4651;
                border: 1px solid #3d4651;
            }
            QWidget#axisCard {
                background: #1b2026;
                border: 1px solid #3d4651;
                border-radius: 4px;
            }
            QToolButton#axisCardTitle {
                background: #323941;
                color: #f2f6fb;
                border: 0;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                padding: 4px 7px;
                font-weight: 700;
                text-align: left;
            }
            QLabel {
                color: #d7dde5;
                font-weight: 600;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background: #1b2229;
                color: #eef2f7;
                border: 1px solid #43505c;
                border-radius: 2px;
                min-height: 26px;
                padding: 2px 6px;
            }
            QSpinBox, QDoubleSpinBox {
                padding-right: 22px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                background: #303943;
                border-left: 1px solid #56616d;
                width: 20px;
            }
            QSpinBox::up-button, QDoubleSpinBox::up-button {
                border-bottom: 1px solid #56616d;
                border-top-right-radius: 2px;
            }
            QSpinBox::down-button, QDoubleSpinBox::down-button {
                border-bottom-right-radius: 2px;
            }
            QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
            QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
                background: #43505c;
            }
            QCheckBox {
                color: #eef2f7;
                spacing: 6px;
            }
            QPushButton#viewResetButton {
                background: #5c6167;
                color: #f8fafc;
                border: 1px solid #737a82;
                border-radius: 4px;
                min-height: 26px;
                font-weight: 700;
            }
            QPushButton#saveDefaultButton {
                background: #007a4d;
                color: #f8fafc;
                border: 1px solid #15a36c;
                border-radius: 4px;
                min-height: 26px;
                font-weight: 700;
            }
            QPushButton#factoryResetButton {
                background: #4b5563;
                color: #f8fafc;
                border: 1px solid #6b7280;
                border-radius: 4px;
                min-height: 26px;
                font-weight: 700;
            }
            QPushButton#colorButton {
                background: #333a42;
                color: #f8fafc;
                border: 1px solid #56616d;
                border-radius: 3px;
                min-height: 24px;
                font-weight: 700;
            }
            """
        )
        self._load_saved_default()

    def _graph_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(CollapsibleSection("Title", self._title_section(), expanded=False))
        layout.addWidget(CollapsibleSection("Axes", self._axes_section(), expanded=False))
        layout.addWidget(CollapsibleSection("Plot Area", self._plot_area_section(), expanded=True))
        layout.addStretch(1)
        return widget

    def _profile_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(CollapsibleSection("Active Spectrum", self._active_profile_section(), expanded=True))
        layout.addWidget(CollapsibleSection("Candidate References", self._profile_candidates_section(), expanded=True))
        layout.addWidget(CollapsibleSection("Layers", self._layers_section(), expanded=True))
        layout.addWidget(CollapsibleSection("Lines", self._lines_section(), expanded=False))
        layout.addWidget(CollapsibleSection("Markers", self._markers_section(), expanded=False))
        layout.addStretch(1)
        return widget

    def _active_profile_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 12)
        self.active_profile_label = QLabel("Active spectrum: none")
        self.active_profile_label.setObjectName("activeProfileLabel")
        self.active_profile_label.setWordWrap(True)
        layout.addWidget(self.active_profile_label)
        reference_form = QFormLayout()
        self.reference_view_combo = QComboBox()
        self.reference_view_combo.addItem("Profiles", "profiles")
        self.reference_view_combo.addItem("Lines", "lines")
        self.reference_view_combo.addItem("Profiles + lines", "both")
        self.reference_view_combo.setToolTip(
            "Display complete reference spectra, extracted band lines, or both."
        )
        self.reference_view_combo.currentIndexChanged.connect(
            lambda _index: self.referenceViewChanged.emit(
                str(self.reference_view_combo.currentData() or "profiles")
            )
        )
        reference_form.addRow("Reference display", self.reference_view_combo)
        layout.addLayout(reference_form)
        return widget

    def _profile_candidates_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 12)
        self.profile_candidate_table = QTableWidget(0, 6)
        self.profile_candidate_table.setObjectName("profileCandidateTable")
        self.profile_candidate_table.setHorizontalHeaderLabels(["Color", "Source", "Entry", "Compound", "Match", "Method"])
        self.profile_candidate_table.verticalHeader().setVisible(False)
        self.profile_candidate_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.profile_candidate_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.profile_candidate_table.setAlternatingRowColors(True)
        self.profile_candidate_table.setMinimumHeight(130)
        self.profile_candidate_table.cellDoubleClicked.connect(self._on_profile_candidate_double_clicked)
        header = self.profile_candidate_table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.profile_candidate_table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((52, 92, 92, 190, 76, 76)):
            self.profile_candidate_table.setColumnWidth(column, width)
        layout.addWidget(self.profile_candidate_table)
        return widget

    def set_active_profile_label(self, text: str) -> None:
        if hasattr(self, "active_profile_label"):
            self.active_profile_label.setText(text or "Active spectrum: none")

    def _on_profile_candidate_double_clicked(self, row: int, column: int) -> None:
        if column == 0 and row >= 0:
            self.profileCandidateColorRequested.emit(row)

    def set_profile_candidates(self, candidates: list[dict[str, str]]) -> None:
        if not hasattr(self, "profile_candidate_table"):
            return
        self.profile_candidate_table.setRowCount(len(candidates))
        for row, candidate in enumerate(candidates):
            color = candidate.get("_Color", "") or "#808080"
            values = [
                color,
                candidate.get("Source", ""),
                candidate.get("Entry", ""),
                candidate.get("Compound", candidate.get("Phase", "")),
                candidate.get("Match", candidate.get("Match (%)", candidate.get("Prob.", ""))),
                candidate.get("Method", ""),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    qcolor = QColor(color)
                    if qcolor.isValid():
                        item.setBackground(qcolor)
                        item.setForeground(QColor("#ffffff" if qcolor.lightness() < 150 else "#111111"))
                self.profile_candidate_table.setItem(row, column, item)

    def _title_section(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._style_form(form)
        self.title_visible_checkbox = QCheckBox()
        self.title_visible_checkbox.setChecked(True)
        self.title_visible_checkbox.toggled.connect(self._emit_settings)
        self.title_text_input = QLineEdit("IR/Raman Phase Finder: spectrum and candidate markers")
        self.title_text_input.textChanged.connect(self._emit_settings)
        self.title_font_spin = self._spin(8, 24, 13)
        self.title_color_input = QLineEdit("#111111")
        self.title_color_input.textChanged.connect(self._emit_settings)
        form.addRow("Show", self.title_visible_checkbox)
        form.addRow("Text", self.title_text_input)
        form.addRow("Font", self.title_font_spin)
        form.addRow("Color", self._color_control(self.title_color_input))
        return widget

    def _axes_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        self.bottom_axis_checkbox = QCheckBox()
        self.bottom_axis_checkbox.setChecked(True)
        self.bottom_axis_checkbox.toggled.connect(self._emit_settings)
        self.bottom_values_checkbox = QCheckBox()
        self.bottom_values_checkbox.setChecked(True)
        self.bottom_values_checkbox.toggled.connect(self._emit_settings)
        self.bottom_label_checkbox = QCheckBox()
        self.bottom_label_checkbox.setChecked(True)
        self.bottom_label_checkbox.toggled.connect(self._emit_settings)
        self.bottom_scale_combo = self._axis_scale_combo("wavenumber", "bottom")
        self.bottom_label_input = QLineEdit("Wavenumber")
        self.bottom_label_input.textChanged.connect(self._emit_settings)
        self.bottom_unit_input = QLineEdit("cm-1")
        self.bottom_unit_input.textChanged.connect(self._emit_settings)

        self.top_axis_checkbox = QCheckBox()
        self.top_axis_checkbox.toggled.connect(self._emit_settings)
        self.top_values_checkbox = QCheckBox()
        self.top_values_checkbox.setChecked(True)
        self.top_values_checkbox.toggled.connect(self._emit_settings)
        self.top_label_checkbox = QCheckBox()
        self.top_label_checkbox.setChecked(True)
        self.top_label_checkbox.toggled.connect(self._emit_settings)
        self.top_scale_combo = self._axis_scale_combo("wavenumber", "top")
        self.top_label_input = QLineEdit("Wavenumber")
        self.top_label_input.textChanged.connect(self._emit_settings)
        self.top_unit_input = QLineEdit("cm-1")
        self.top_unit_input.textChanged.connect(self._emit_settings)

        self.left_axis_checkbox = QCheckBox()
        self.left_axis_checkbox.setChecked(True)
        self.left_axis_checkbox.toggled.connect(self._emit_settings)
        self.left_values_checkbox = QCheckBox()
        self.left_values_checkbox.setChecked(True)
        self.left_values_checkbox.toggled.connect(self._emit_settings)
        self.left_label_checkbox = QCheckBox()
        self.left_label_checkbox.setChecked(True)
        self.left_label_checkbox.toggled.connect(self._emit_settings)
        self.left_label_input = QLineEdit("Intensity")
        self.left_label_input.textChanged.connect(self._emit_settings)
        self.left_unit_input = QLineEdit("a.u.")
        self.left_unit_input.textChanged.connect(self._emit_settings)

        self.right_axis_checkbox = QCheckBox()
        self.right_axis_checkbox.toggled.connect(self._emit_settings)
        self.right_values_checkbox = QCheckBox()
        self.right_values_checkbox.setChecked(True)
        self.right_values_checkbox.toggled.connect(self._emit_settings)
        self.right_label_checkbox = QCheckBox()
        self.right_label_checkbox.setChecked(True)
        self.right_label_checkbox.toggled.connect(self._emit_settings)
        self.right_label_input = QLineEdit("Intensity")
        self.right_label_input.textChanged.connect(self._emit_settings)
        self.right_unit_input = QLineEdit("a.u.")
        self.right_unit_input.textChanged.connect(self._emit_settings)

        self.label_font_spin = self._spin(8, 24, 12)
        self.tick_font_spin = self._spin(7, 20, 10)
        self.axis_color_input = QLineEdit("#111111")
        self.axis_color_input.textChanged.connect(self._emit_settings)
        self.axis_width_spin = self._double_spin(0.5, 4.0, 1.2, 0.1)
        self.tick_length_spin = self._spin(0, 24, 5)
        self.x_major_tick_spin = self._tick_step_spin(1000.0, 0.1)
        self.x_minor_tick_spin = self._tick_step_spin(1000.0, 0.1)
        self.y_major_tick_spin = self._tick_step_spin(1000000.0, 1.0)
        self.y_minor_tick_spin = self._tick_step_spin(1000000.0, 1.0)
        axis_grid = QGridLayout()
        axis_grid.setContentsMargins(0, 0, 0, 0)
        axis_grid.setHorizontalSpacing(8)
        axis_grid.setVerticalSpacing(8)
        axis_grid.addWidget(
            self._axis_card(
                "Top",
                self.top_axis_checkbox,
                self.top_values_checkbox,
                self.top_label_checkbox,
                self.top_scale_combo,
                self.top_label_input,
                self.top_unit_input,
            ),
            0,
            0,
        )
        axis_grid.addWidget(
            self._axis_card(
                "Right",
                self.right_axis_checkbox,
                self.right_values_checkbox,
                self.right_label_checkbox,
                None,
                self.right_label_input,
                self.right_unit_input,
            ),
            0,
            1,
        )
        axis_grid.addWidget(
            self._axis_card(
                "Left",
                self.left_axis_checkbox,
                self.left_values_checkbox,
                self.left_label_checkbox,
                None,
                self.left_label_input,
                self.left_unit_input,
            ),
            1,
            0,
        )
        axis_grid.addWidget(
            self._axis_card(
                "Bottom",
                self.bottom_axis_checkbox,
                self.bottom_values_checkbox,
                self.bottom_label_checkbox,
                self.bottom_scale_combo,
                self.bottom_label_input,
                self.bottom_unit_input,
            ),
            1,
            1,
        )
        layout.addLayout(axis_grid)

        common_form = QFormLayout()
        self._style_form(common_form)
        common_form.setContentsMargins(2, 2, 2, 0)
        common_form.addRow("Label font", self.label_font_spin)
        common_form.addRow("Tick font", self.tick_font_spin)
        common_form.addRow("Color", self._color_control(self.axis_color_input))
        common_form.addRow("Width", self.axis_width_spin)
        common_form.addRow("Tick length", self.tick_length_spin)
        common_form.addRow("X major step", self.x_major_tick_spin)
        common_form.addRow("X minor step", self.x_minor_tick_spin)
        common_form.addRow("Y major step", self.y_major_tick_spin)
        common_form.addRow("Y minor step", self.y_minor_tick_spin)
        layout.addLayout(common_form)
        return widget

    def _axis_card(
        self,
        title: str,
        axis_checkbox: QCheckBox,
        values_checkbox: QCheckBox,
        label_checkbox: QCheckBox,
        scale_combo: QComboBox | None,
        label_input: QLineEdit,
        unit_input: QLineEdit,
    ) -> QWidget:
        card = QWidget()
        card.setObjectName("axisCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(6)

        header = QToolButton()
        header.setObjectName("axisCardTitle")
        header.setText(title)
        header.setEnabled(False)
        header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(header)

        form = QFormLayout()
        form.setContentsMargins(8, 2, 8, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.addRow("Axis", axis_checkbox)
        form.addRow("Values", values_checkbox)
        form.addRow("Label", label_checkbox)
        if scale_combo is not None:
            form.addRow("Scale", scale_combo)
        form.addRow("Text", label_input)
        form.addRow("Unit", unit_input)
        layout.addLayout(form)
        return card

    def _on_x_display_unit_changed(self, _index: int) -> None:
        unit = self._scale_to_legacy_unit(self._combo_data(self.bottom_scale_combo, "wavenumber"))
        self.xAxisUnitChanged.emit(unit)
        self._emit_settings()

    def _plot_area_section(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._style_form(form)
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(self._ASPECTS.keys())
        self.aspect_combo.currentTextChanged.connect(self._on_aspect_mode_changed)
        self.custom_aspect_width_spin = self._double_spin(0.1, 100.0, 4.0, 0.1)
        self.custom_aspect_height_spin = self._double_spin(0.1, 100.0, 2.0, 0.1)
        self.background_input = QLineEdit("#ffffff")
        self.background_input.textChanged.connect(self._emit_settings)
        self.border_checkbox = QCheckBox()
        self.border_checkbox.setChecked(True)
        self.border_checkbox.toggled.connect(self._emit_settings)
        self.border_color_input = QLineEdit("#111111")
        self.border_color_input.textChanged.connect(self._emit_settings)
        self.border_width_spin = self._spin(0, 8, 1)
        self.grid_checkbox = QCheckBox()
        self.grid_checkbox.setChecked(True)
        self.grid_checkbox.toggled.connect(self._emit_settings)
        self.grid_color_input = QLineEdit("#8f969e")
        self.grid_color_input.textChanged.connect(self._emit_settings)
        self.grid_width_spin = self._double_spin(0.2, 4.0, 0.7, 0.1)
        self.grid_alpha_spin = self._double_spin(0.02, 0.6, 0.18, 0.02)
        self.legend_checkbox = QCheckBox()
        self.legend_checkbox.setChecked(True)
        self.legend_checkbox.toggled.connect(self._emit_settings)
        self.legend_font_spin = self._spin(7, 20, 10)
        self.legend_color_input = QLineEdit("#111111")
        self.legend_color_input.textChanged.connect(self._emit_settings)
        self.cursor_line_checkbox = QCheckBox()
        self.cursor_line_checkbox.toggled.connect(self._emit_settings)
        self.hkl_labels_checkbox = QCheckBox()
        self.hkl_labels_checkbox.toggled.connect(self._emit_settings)
        custom_aspect_row = QWidget()
        custom_aspect_layout = QHBoxLayout(custom_aspect_row)
        custom_aspect_layout.setContentsMargins(0, 0, 0, 0)
        custom_aspect_layout.setSpacing(6)
        custom_aspect_layout.addWidget(self.custom_aspect_width_spin)
        custom_aspect_layout.addWidget(QLabel(":"))
        custom_aspect_layout.addWidget(self.custom_aspect_height_spin)
        form.addRow("Format", self.aspect_combo)
        form.addRow("Custom ratio", custom_aspect_row)
        form.addRow("Background", self._color_control(self.background_input))
        form.addRow("Frame", self.border_checkbox)
        form.addRow("Frame color", self._color_control(self.border_color_input))
        form.addRow("Frame width", self.border_width_spin)
        form.addRow("Grid", self.grid_checkbox)
        form.addRow("Grid color", self._color_control(self.grid_color_input))
        form.addRow("Grid width", self.grid_width_spin)
        form.addRow("Grid alpha", self.grid_alpha_spin)
        form.addRow("Legend", self.legend_checkbox)
        form.addRow("Legend font", self.legend_font_spin)
        form.addRow("Legend color", self._color_control(self.legend_color_input))
        form.addRow("Vertical cursor line", self.cursor_line_checkbox)
        form.addRow("Band labels", self.hkl_labels_checkbox)
        return widget

    def _layers_section(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._style_form(form)
        self.layer_observed_checkbox = QCheckBox()
        self.layer_observed_checkbox.setChecked(True)
        self.layer_observed_checkbox.toggled.connect(self._emit_settings)
        self.layer_preview_peak_positions_checkbox = QCheckBox()
        self.layer_preview_peak_positions_checkbox.setChecked(True)
        self.layer_preview_peak_positions_checkbox.toggled.connect(self._emit_settings)
        self.layer_total_profile_checkbox = QCheckBox()
        self.layer_total_profile_checkbox.setChecked(True)
        self.layer_total_profile_checkbox.toggled.connect(self._emit_settings)
        self.layer_phase_profiles_checkbox = QCheckBox()
        self.layer_phase_profiles_checkbox.setChecked(True)
        self.layer_phase_profiles_checkbox.toggled.connect(self._emit_settings)
        self.layer_background_checkbox = QCheckBox()
        self.layer_background_checkbox.setChecked(True)
        self.layer_background_checkbox.toggled.connect(self._emit_settings)
        self.layer_phase_ticks_checkbox = QCheckBox()
        self.layer_phase_ticks_checkbox.setChecked(True)
        self.layer_phase_ticks_checkbox.toggled.connect(self._emit_settings)
        self.layer_coverage_markers_checkbox = QCheckBox()
        self.layer_coverage_markers_checkbox.setChecked(True)
        self.layer_coverage_markers_checkbox.toggled.connect(self._emit_settings)
        self.layer_peak_labels_checkbox = QCheckBox()
        self.layer_peak_labels_checkbox.setChecked(False)
        self.layer_peak_labels_checkbox.toggled.connect(self._emit_settings)
        self.layer_unknown_peaks_checkbox = QCheckBox()
        self.layer_unknown_peaks_checkbox.setChecked(True)
        self.layer_unknown_peaks_checkbox.toggled.connect(self._emit_settings)
        form.addRow("Observed spectrum", self.layer_observed_checkbox)
        form.addRow("Reference preview", self.layer_preview_peak_positions_checkbox)
        form.addRow("Processed spectrum", self.layer_total_profile_checkbox)
        form.addRow("Reference components", self.layer_phase_profiles_checkbox)
        form.addRow("Background", self.layer_background_checkbox)
        form.addRow("Band tick marks", self.layer_phase_ticks_checkbox)
        form.addRow("Assignment markers", self.layer_coverage_markers_checkbox)
        form.addRow("Band labels", self.layer_peak_labels_checkbox)
        form.addRow("Unassigned bands", self.layer_unknown_peaks_checkbox)
        return widget

    def _lines_section(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._style_form(form)
        self.observed_color_input = QLineEdit("#202124")
        self.observed_color_input.textChanged.connect(self._emit_settings)
        self.calculated_color_input = QLineEdit("#0b8043")
        self.calculated_color_input.textChanged.connect(self._emit_settings)
        self.background_color_input = QLineEdit("#9aa0a6")
        self.background_color_input.textChanged.connect(self._emit_settings)
        self.reference_color_input = QLineEdit("#1a73e8")
        self.reference_color_input.textChanged.connect(self._emit_settings)
        self.observed_width_spin = self._double_spin(0.5, 5.0, 1.35, 0.1)
        self.calculated_width_spin = self._double_spin(0.5, 5.0, 1.6, 0.1)
        style_row = QWidget()
        row_layout = QHBoxLayout(style_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.observed_width_spin)
        row_layout.addWidget(self.calculated_width_spin)
        form.addRow("Observed color", self._color_control(self.observed_color_input))
        form.addRow("Processed color", self._color_control(self.calculated_color_input))
        form.addRow("Background color", self._color_control(self.background_color_input))
        form.addRow("Reference color", self._color_control(self.reference_color_input))
        form.addRow("Observed / reference", style_row)
        return widget

    def _markers_section(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)
        self._style_form(form)
        self.marker_size_spin = self._spin(3, 18, 7)
        self.marker_shape_combo = QComboBox()
        self.marker_shape_combo.addItems(["Circle", "Triangle", "Diamond", "Square"])
        self.marker_shape_combo.currentTextChanged.connect(self._emit_settings)
        form.addRow("Size", self.marker_size_spin)
        form.addRow("Shape", self.marker_shape_combo)
        return widget

    def _spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = NoWheelSpinBox()
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spin.setKeyboardTracking(False)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.valueChanged.connect(self._emit_settings)
        return spin

    def _style_form(self, form: QFormLayout) -> None:
        form.setContentsMargins(12, 10, 12, 12)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _double_spin(self, minimum: float, maximum: float, value: float, step: float) -> QDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        spin.setKeyboardTracking(False)
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.valueChanged.connect(self._emit_settings)
        return spin

    def _tick_step_spin(self, maximum: float, step: float) -> QDoubleSpinBox:
        spin = self._double_spin(0.0, maximum, 0.0, step)
        spin.setSpecialValueText("Auto")
        return spin

    def _color_control(self, input_widget: QLineEdit) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        button = QPushButton("")
        button.setObjectName("colorButton")
        button.setMinimumWidth(42)
        button.clicked.connect(lambda _checked=False, target=input_widget: self._choose_color(target))
        input_widget.textChanged.connect(lambda _text, target=input_widget, control=button: self._sync_color_button(target, control))
        layout.addWidget(input_widget, 1)
        layout.addWidget(button)
        self._sync_color_button(input_widget, button)
        return row

    def _choose_color(self, input_widget: QLineEdit) -> None:
        initial = QColor(input_widget.text().strip() or "#111111")
        color = QColorDialog.getColor(initial, self, "Choose color")
        if color.isValid():
            input_widget.setText(color.name())

    def _sync_color_button(self, input_widget: QLineEdit, button: QPushButton) -> None:
        color = QColor(input_widget.text().strip())
        preview = color.name() if color.isValid() else "#333a42"
        border = "#f8fafc" if color.isValid() and color.lightness() < 95 else "#56616d"
        button.setStyleSheet(
            f"background: {preview}; border: 1px solid {border}; border-radius: 3px; min-height: 24px;"
        )

    def _axis_scale_combo(self, value: str, axis_name: str) -> QComboBox:
        combo = QComboBox()
        combo.addItem("Wavenumber / Raman shift", "wavenumber")
        combo.addItem("Wavelength", "nm")
        combo.addItem("Energy", "eV")
        combo.setToolTip(
            "FTIR wavelength is converted from absolute wavenumber. Raman wavelength is scattered wavelength for the selected laser."
        )
        self._set_axis_scale_combo(combo, value)
        combo.currentIndexChanged.connect(lambda _index, axis=axis_name, target=combo: self._on_x_axis_mode_changed(axis, target))
        return combo

    def _combo_data(self, combo: QComboBox, fallback: str) -> str:
        return str(combo.currentData() or fallback)

    def _set_axis_scale_combo(self, combo: QComboBox, value: str) -> None:
        normalized = self._normalize_axis_scale(value)
        index = combo.findData(normalized)
        combo.setCurrentIndex(max(0, index))

    def _normalize_axis_scale(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        aliases = {
            "cm-1": "wavenumber",
            "cm⁻¹": "wavenumber",
            "wavenumbers": "wavenumber",
            "raman shift": "wavenumber",
            "wavelength": "nm",
            "nanometer": "nm",
            "nanometers": "nm",
            "energy": "eV",
            "ev": "eV",
        }
        return aliases.get(normalized, normalized if normalized in {"wavenumber", "nm", "eV"} else "wavenumber")

    def _scale_to_legacy_unit(self, scale: str) -> str:
        return {"nm": "nm", "eV": "eV"}.get(self._normalize_axis_scale(scale), "cm-1")

    def _on_aspect_mode_changed(self, _mode: str) -> None:
        is_custom = self.aspect_combo.currentText() == "Custom"
        self.custom_aspect_width_spin.setEnabled(is_custom)
        self.custom_aspect_height_spin.setEnabled(is_custom)
        self._emit_settings()

    def _current_aspect_ratio(self) -> float | None:
        if self.aspect_combo.currentText() == "Custom":
            height = max(float(self.custom_aspect_height_spin.value()), 0.1)
            return max(float(self.custom_aspect_width_spin.value()), 0.1) / height
        return self._ASPECTS.get(self.aspect_combo.currentText())

    def _on_x_axis_mode_changed(self, axis_name: str, combo: QComboBox) -> None:
        label_input = self.bottom_label_input if axis_name == "bottom" else self.top_label_input
        unit_input = self.bottom_unit_input if axis_name == "bottom" else self.top_unit_input
        scale = self._combo_data(combo, "wavenumber")
        label_by_scale = {
            "wavenumber": "Wavenumber",
            "nm": "Wavelength",
            "eV": "Energy",
        }
        unit_by_scale = {
            "wavenumber": "cm-1",
            "nm": "nm",
            "eV": "eV",
        }
        current_label = label_input.text().strip()
        current_unit = unit_input.text().strip()
        auto_labels = {"", "2theta", "2 theta", "2-theta", "d", "wavenumber", "raman shift", "wavelength", "energy"}
        auto_units = {"", "deg", "degree", "degrees", "a", "angstrom", "angstroms", "cm-1", "cm⁻¹", "nm", "ev", "eV"}
        if current_label.lower() in auto_labels:
            label_input.setText(label_by_scale.get(scale, "Wavenumber"))
        if current_unit in auto_units or current_unit.lower() in auto_units:
            unit_input.setText(unit_by_scale.get(scale, "cm-1"))
        if axis_name == "bottom":
            self.xAxisUnitChanged.emit(self._scale_to_legacy_unit(scale))
        self._emit_settings()

    def settings(self) -> PlotViewSettings:
        return PlotViewSettings(
            title_visible=bool(self.title_visible_checkbox.isChecked()),
            title_text=self.title_text_input.text().strip(),
            title_font_size=int(self.title_font_spin.value()),
            title_color=self.title_color_input.text().strip() or "#111111",
            aspect_ratio=self._current_aspect_ratio(),
            custom_aspect_width=float(self.custom_aspect_width_spin.value()),
            custom_aspect_height=float(self.custom_aspect_height_spin.value()),
            plot_background=self.background_input.text().strip() or "#ffffff",
            plot_border_visible=bool(self.border_checkbox.isChecked()),
            plot_border_color=self.border_color_input.text().strip() or "#111111",
            plot_border_width=int(self.border_width_spin.value()),
            label_font_size=int(self.label_font_spin.value()),
            tick_font_size=int(self.tick_font_spin.value()),
            axis_color=self.axis_color_input.text().strip() or "#111111",
            axis_width=float(self.axis_width_spin.value()),
            tick_length=int(self.tick_length_spin.value()),
            x_major_tick_spacing=float(self.x_major_tick_spin.value()),
            x_minor_tick_spacing=float(self.x_minor_tick_spin.value()),
            y_major_tick_spacing=float(self.y_major_tick_spin.value()),
            y_minor_tick_spacing=float(self.y_minor_tick_spin.value()),
            x_display_unit=self._scale_to_legacy_unit(self._combo_data(self.bottom_scale_combo, "wavenumber")),
            bottom_axis_visible=bool(self.bottom_axis_checkbox.isChecked()),
            bottom_axis_values_visible=bool(self.bottom_values_checkbox.isChecked()),
            bottom_axis_label_visible=bool(self.bottom_label_checkbox.isChecked()),
            bottom_axis_scale=self._combo_data(self.bottom_scale_combo, "wavenumber"),
            bottom_axis_label=self.bottom_label_input.text().strip() or "Wavenumber",
            bottom_axis_unit=self.bottom_unit_input.text().strip(),
            top_axis_visible=bool(self.top_axis_checkbox.isChecked()),
            top_axis_values_visible=bool(self.top_values_checkbox.isChecked()),
            top_axis_label_visible=bool(self.top_label_checkbox.isChecked()),
            top_axis_scale=self._combo_data(self.top_scale_combo, "wavenumber"),
            top_axis_label=self.top_label_input.text().strip() or "Wavenumber",
            top_axis_unit=self.top_unit_input.text().strip(),
            left_axis_visible=bool(self.left_axis_checkbox.isChecked()),
            left_axis_values_visible=bool(self.left_values_checkbox.isChecked()),
            left_axis_label_visible=bool(self.left_label_checkbox.isChecked()),
            left_axis_label=self.left_label_input.text().strip() or "Intensity",
            left_axis_unit=self.left_unit_input.text().strip(),
            right_axis_visible=bool(self.right_axis_checkbox.isChecked()),
            right_axis_values_visible=bool(self.right_values_checkbox.isChecked()),
            right_axis_label_visible=bool(self.right_label_checkbox.isChecked()),
            right_axis_label=self.right_label_input.text().strip() or "Intensity",
            right_axis_unit=self.right_unit_input.text().strip(),
            grid_visible=bool(self.grid_checkbox.isChecked()),
            grid_color=self.grid_color_input.text().strip() or "#8f969e",
            grid_width=float(self.grid_width_spin.value()),
            grid_alpha=float(self.grid_alpha_spin.value()),
            legend_visible=bool(self.legend_checkbox.isChecked()),
            legend_font_size=int(self.legend_font_spin.value()),
            legend_color=self.legend_color_input.text().strip() or "#111111",
            cursor_vertical_line_visible=bool(self.cursor_line_checkbox.isChecked()),
            hkl_labels_visible=bool(self.hkl_labels_checkbox.isChecked()),
            layer_observed_visible=bool(self.layer_observed_checkbox.isChecked()),
            layer_preview_peak_positions_visible=bool(self.layer_preview_peak_positions_checkbox.isChecked()),
            layer_total_profile_visible=bool(self.layer_total_profile_checkbox.isChecked()),
            layer_phase_profiles_visible=bool(self.layer_phase_profiles_checkbox.isChecked()),
            layer_background_visible=bool(self.layer_background_checkbox.isChecked()),
            layer_phase_ticks_visible=bool(self.layer_phase_ticks_checkbox.isChecked()),
            layer_coverage_markers_visible=bool(self.layer_coverage_markers_checkbox.isChecked()),
            layer_peak_labels_visible=bool(self.layer_peak_labels_checkbox.isChecked()),
            layer_unknown_peaks_visible=bool(self.layer_unknown_peaks_checkbox.isChecked()),
            observed_color=self.observed_color_input.text().strip() or "#202124",
            calculated_color=self.calculated_color_input.text().strip() or "#0b8043",
            background_color=self.background_color_input.text().strip() or "#9aa0a6",
            reference_color=self.reference_color_input.text().strip() or "#1a73e8",
            observed_width=float(self.observed_width_spin.value()),
            calculated_width=float(self.calculated_width_spin.value()),
            marker_size=int(self.marker_size_spin.value()),
            marker_shape=self.marker_shape_combo.currentText(),
        )

    def reset(self) -> None:
        if self._load_saved_default(emit=False):
            self._emit_settings()
            return
        self.factory_reset()

    def factory_reset(self) -> None:
        self._apply_settings(PlotViewSettings())
        self._emit_settings()

    def save_as_default(self) -> None:
        QSettings("IRRamanPhaseFinder", "Standalone").setValue(self._DEFAULT_SETTINGS_KEY, json.dumps(asdict(self.settings())))

    def _load_saved_default(self, emit: bool = True) -> bool:
        raw = QSettings("IRRamanPhaseFinder", "Standalone").value(self._DEFAULT_SETTINGS_KEY, "", type=str)
        if not raw:
            return False
        try:
            stored = json.loads(raw)
            defaults = asdict(PlotViewSettings())
            valid_names = {field.name for field in fields(PlotViewSettings)}
            values = {name: stored.get(name, defaults[name]) for name in valid_names}
            self._apply_settings(PlotViewSettings(**values))
            if emit:
                self._emit_settings()
            return True
        except Exception:
            return False

    def _aspect_name(self, value: float | None) -> str:
        for name, aspect in self._ASPECTS.items():
            if aspect == value:
                return name
        if value is not None:
            return "Custom"
        return "Fit"

    def _apply_settings(self, settings: PlotViewSettings) -> None:
        self.title_visible_checkbox.setChecked(settings.title_visible)
        self.title_text_input.setText(settings.title_text)
        self.title_font_spin.setValue(settings.title_font_size)
        self.title_color_input.setText(settings.title_color)
        self.custom_aspect_width_spin.setValue(settings.custom_aspect_width)
        self.custom_aspect_height_spin.setValue(settings.custom_aspect_height)
        self.aspect_combo.setCurrentText(self._aspect_name(settings.aspect_ratio))
        self._on_aspect_mode_changed(self.aspect_combo.currentText())
        self.background_input.setText(settings.plot_background)
        self.border_checkbox.setChecked(settings.plot_border_visible)
        self.border_color_input.setText(settings.plot_border_color)
        self.border_width_spin.setValue(settings.plot_border_width)
        self.bottom_axis_checkbox.setChecked(settings.bottom_axis_visible)
        self.bottom_values_checkbox.setChecked(settings.bottom_axis_values_visible)
        self.bottom_label_checkbox.setChecked(settings.bottom_axis_label_visible)
        bottom_scale = settings.bottom_axis_scale
        if self._normalize_axis_scale(bottom_scale) == "wavenumber" and settings.x_display_unit in {"nm", "eV"}:
            bottom_scale = settings.x_display_unit
        self._set_axis_scale_combo(self.bottom_scale_combo, bottom_scale)
        self.bottom_label_input.setText(settings.bottom_axis_label)
        self.bottom_unit_input.setText(settings.bottom_axis_unit)
        self.top_axis_checkbox.setChecked(settings.top_axis_visible)
        self.top_values_checkbox.setChecked(settings.top_axis_values_visible)
        self.top_label_checkbox.setChecked(settings.top_axis_label_visible)
        self._set_axis_scale_combo(self.top_scale_combo, settings.top_axis_scale)
        self.top_label_input.setText(settings.top_axis_label)
        self.top_unit_input.setText(settings.top_axis_unit)
        self.left_axis_checkbox.setChecked(settings.left_axis_visible)
        self.left_values_checkbox.setChecked(settings.left_axis_values_visible)
        self.left_label_checkbox.setChecked(settings.left_axis_label_visible)
        self.left_label_input.setText(settings.left_axis_label)
        self.left_unit_input.setText(settings.left_axis_unit)
        self.right_axis_checkbox.setChecked(settings.right_axis_visible)
        self.right_values_checkbox.setChecked(settings.right_axis_values_visible)
        self.right_label_checkbox.setChecked(settings.right_axis_label_visible)
        self.right_label_input.setText(settings.right_axis_label)
        self.right_unit_input.setText(settings.right_axis_unit)
        self.label_font_spin.setValue(settings.label_font_size)
        self.tick_font_spin.setValue(settings.tick_font_size)
        self.axis_color_input.setText(settings.axis_color)
        self.axis_width_spin.setValue(settings.axis_width)
        self.tick_length_spin.setValue(settings.tick_length)
        self.x_major_tick_spin.setValue(settings.x_major_tick_spacing)
        self.x_minor_tick_spin.setValue(settings.x_minor_tick_spacing)
        self.y_major_tick_spin.setValue(settings.y_major_tick_spacing)
        self.y_minor_tick_spin.setValue(settings.y_minor_tick_spacing)
        self.grid_checkbox.setChecked(settings.grid_visible)
        self.grid_color_input.setText(settings.grid_color)
        self.grid_width_spin.setValue(settings.grid_width)
        self.grid_alpha_spin.setValue(settings.grid_alpha)
        self.legend_checkbox.setChecked(settings.legend_visible)
        self.legend_font_spin.setValue(settings.legend_font_size)
        self.legend_color_input.setText(settings.legend_color)
        self.cursor_line_checkbox.setChecked(settings.cursor_vertical_line_visible)
        self.hkl_labels_checkbox.setChecked(settings.hkl_labels_visible)
        self.layer_observed_checkbox.setChecked(settings.layer_observed_visible)
        self.layer_preview_peak_positions_checkbox.setChecked(settings.layer_preview_peak_positions_visible)
        self.layer_total_profile_checkbox.setChecked(settings.layer_total_profile_visible)
        self.layer_phase_profiles_checkbox.setChecked(settings.layer_phase_profiles_visible)
        self.layer_background_checkbox.setChecked(settings.layer_background_visible)
        self.layer_phase_ticks_checkbox.setChecked(settings.layer_phase_ticks_visible)
        self.layer_coverage_markers_checkbox.setChecked(settings.layer_coverage_markers_visible)
        self.layer_peak_labels_checkbox.setChecked(settings.layer_peak_labels_visible)
        self.layer_unknown_peaks_checkbox.setChecked(settings.layer_unknown_peaks_visible)
        self.observed_color_input.setText(settings.observed_color)
        self.calculated_color_input.setText(settings.calculated_color)
        self.background_color_input.setText(settings.background_color)
        self.reference_color_input.setText(settings.reference_color)
        self.observed_width_spin.setValue(settings.observed_width)
        self.calculated_width_spin.setValue(settings.calculated_width)
        self.marker_size_spin.setValue(settings.marker_size)
        self.marker_shape_combo.setCurrentText(settings.marker_shape)

    def _emit_settings(self, *_args) -> None:
        self.settingsChanged.emit(self.settings())
