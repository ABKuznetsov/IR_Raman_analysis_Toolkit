from __future__ import annotations

import os
import re
import sys
import time
import json
from dataclasses import dataclass, field, replace
from pathlib import Path

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
import numpy as np
from PySide6.QtCore import Signal, Qt
from PySide6.QtCore import QSettings
from PySide6.QtCore import QTimer
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finder_core.data_sources import SourceQuery
from finder_core.cache import app_cache_dir
from finder_core.chemistry import parse_formula_elements
from finder_core.export import write_match_table, write_spectrum_csv, write_spectrum_jcamp
from finder_core.models import CandidateRecord, MatchScore, SignalKind
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands, extract_reference_band_set
from vibrational_finder.io import guess_spectrum_metadata, load_xy_spectrum, ramanchada2_available, supported_spectrum_extensions
from vibrational_finder.matching import MatchingOptions, rank_candidates
from vibrational_finder.metadata import APP_NAME, about_html
from vibrational_finder.models import CompoundCandidate, ObservedSpectrum, ReferenceBandSet, ReferenceSpectrum, SpectralBand, VibrationalMatchResult
from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum
from vibrational_finder.services import (
    CifStructureSource,
    EditableReferenceSource,
    FolderLibrarySource,
    JarvisDftSource,
    RodSource,
    RruffSource,
    UserLibrarySource,
    write_editable_reference,
)
from vibrational_finder.services.editable_reference import USER_REFERENCE_BAND_RECIPE_VERSION
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache
from vibrational_finder.services.openspecy_source import OpenSpecyLibrarySource
from vibrational_finder.services.preprocessing_service import auto_smoothing_window, estimate_background, remove_narrow_spikes, smooth_spectrum_curve
from vibrational_finder.services.public_sources import external_source_by_key
from vibrational_finder.ui import ImportMethodDialog, PeriodicTableWidget, ReferenceEditorDialog, element_sort_key
from vibrational_finder.ui.background_task import BackgroundTaskHandle
from vibrational_finder.ui.plot_view_settings import PlotViewSettings, PlotViewSettingsWidget
from vibrational_finder.ui.preprocessing_panels import (
    BackgroundRemovalPanel,
    DespikePanel,
    SmoothPanel,
    background_method_label,
    preprocessing_panel_style,
)
from vibrational_finder.ui.vibrational_plot import create_vibrational_plot_widget
from vibrational_finder.units import WAVENUMBERS_PER_EV, spectral_x_to_nm, wavenumber_to_energy_ev


SPECTRUM_GLOBS = " ".join(f"*{extension}" for extension in supported_spectrum_extensions())
SPECTRUM_FILE_FILTER = (
    f"Spectra ({SPECTRUM_GLOBS});;"
    "Text spectra (*.txt *.xy *.csv *.tsv *.dat *.asc *.ascii);;"
    "Spreadsheets (*.xlsx);;"
    "JCAMP-DX (*.jdx *.dx);;"
    "Vendor spectra (*.spc *.sp *.spa *.0 *.1 *.2 *.wdf *.ngs *.spe *.cha);;"
    "All files (*)"
)

OBSERVED_OVERLAY_COLORS = ["#202124", "#d93025", "#1a73e8", "#188038", "#f9ab00", "#8e24aa", "#00acc1"]
REFERENCE_OVERLAY_COLORS = ["#1a73e8", "#d93025", "#188038", "#f9ab00", "#8e24aa", "#00acc1", "#c5221f"]


@dataclass
class SpectrumProfileState:
    spectrum: ObservedSpectrum | None = None
    results: list[VibrationalMatchResult] = field(default_factory=list)
    browse_records: list[CandidateRecord] = field(default_factory=list)
    selected_results: list[VibrationalMatchResult] = field(default_factory=list)
    visible_selected_candidate_keys: set[str] = field(default_factory=set)


def _format_bytes(size: int) -> str:
    value = float(max(size, 0))
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GB"


def _glass_button_style(background: str, border: str) -> str:
    return (
        "QPushButton {"
        f"background: {background}; border: 1px solid {border}; color: #ffffff;"
        "border-radius: 7px; padding: 7px 12px; font-weight: 700;"
        "}"
        "QPushButton:hover { border-color: rgba(255, 255, 255, 0.72); }"
        "QPushButton:pressed { padding: 8px 12px 6px 12px; }"
    )


def _theme_palette(theme: str) -> dict[str, str]:
    if theme.lower() == "dark":
        return {
            "bg": "#1f2328",
            "panel": "#252a31",
            "alt": "#2c323a",
            "text": "#eef2f7",
            "border": "#46515d",
            "selected": "#315f92",
            "tab": "#303740",
            "tab_selected": "#252a31",
            "input_bg": "#20252b",
            "header": "#333b45",
            "plot_canvas": "#d7dadd",
            "plot_bg": "#ffffff",
            "axis": "#111111",
            "section": "#3a3f45",
            "field_name": "#282c31",
            "field_value": "#252a31",
        }
    return {
        "bg": "#f4f6f8",
        "panel": "#ffffff",
        "alt": "#f3f6fa",
        "text": "#111827",
        "border": "#cbd5e1",
        "selected": "#dbeafe",
        "tab": "#e5e7eb",
        "tab_selected": "#ffffff",
        "input_bg": "#ffffff",
        "header": "#e5e7eb",
        "plot_canvas": "#d7dadd",
        "plot_bg": "#ffffff",
        "axis": "#111111",
        "section": "#3a3f45",
        "field_name": "#282c31",
        "field_value": "#ffffff",
    }


def _window_style(theme: str = "Light") -> str:
    colors = _theme_palette(theme)
    return (
        f"QMainWindow {{ background: {colors['bg']}; color: {colors['text']}; }}"
        f"QWidget {{ color: {colors['text']}; }}"
        f"QLabel {{ color: {colors['text']}; }}"
        f"QCheckBox {{ color: {colors['text']}; }}"
        f"QTabWidget::pane {{ border: 1px solid {colors['border']}; background: {colors['panel']}; }}"
        f"QTabBar::tab {{ background: {colors['tab']}; color: {colors['text']}; padding: 6px 10px; }}"
        f"QTabBar::tab:selected {{ background: {colors['tab_selected']}; color: {colors['text']}; }}"
        f"QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {colors['input_bg']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 3px; }}"
        f"QTreeWidget, QTableWidget, QTextEdit, QPlainTextEdit {{ background: {colors['panel']}; alternate-background-color: {colors['alt']}; color: {colors['text']}; border: 1px solid {colors['border']}; gridline-color: {colors['border']}; }}"
        f"QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {colors['selected']}; color: {colors['text']}; }}"
        f"QHeaderView::section {{ background: {colors['header']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 4px; }}"
        f"QToolButton {{ background: {colors['input_bg']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 4px 8px; }}"
        f"QSplitter::handle {{ background: {colors['border']}; }}"
        f"QSplitter::handle:hover {{ background: {colors['selected']}; }}"
    )


class FinderActionBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display_mode = QComboBox()
        self.normalization_combo = QComboBox()
        self.laser_wavelength_spin = QDoubleSpinBox()
        self.multi_offset_slider = QSlider(Qt.Orientation.Horizontal)
        self.multi_offset_value = QLabel("10%")
        self.smooth_button = QPushButton("Smooth")
        self.remove_background_button = QPushButton("Remove background")
        self.despike_button = QPushButton("Despike")
        self.reset_data_button = QPushButton("Reset data")
        self.auto_match_button = QPushButton("Auto match")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        processing_row = QHBoxLayout()
        processing_row.setContentsMargins(0, 0, 0, 0)
        processing_row.setSpacing(6)
        display_row = QHBoxLayout()
        display_row.setContentsMargins(0, 0, 0, 0)
        display_row.setSpacing(6)

        self.smooth_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.remove_background_button.setStyleSheet(_glass_button_style("#8a5a16", "#c68a2e"))
        self.despike_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.reset_data_button.setStyleSheet(_glass_button_style("#7b4fb3", "#a782d8"))
        self.auto_match_button.setStyleSheet(_glass_button_style("#0b8043", "#35a96c"))

        self.display_mode.addItems(["One", "All selected"])
        self.display_mode.setToolTip(
            "One: show only the active experimental spectrum.\n"
            "All selected: show all checked Raman/FTIR spectra from the project tree."
        )
        self.normalization_combo.addItem("None", "none")
        self.normalization_combo.addItem("Max (0-1)", "max")
        self.normalization_combo.addItem("Vector", "vector")
        self.normalization_combo.addItem("Area", "area")
        self.normalization_combo.addItem("SNV", "snv")
        self.normalization_combo.setCurrentIndex(1)
        self.smooth_button.setMinimumWidth(82)
        self.remove_background_button.setMinimumWidth(154)
        self.despike_button.setMinimumWidth(82)
        self.reset_data_button.setMinimumWidth(100)
        self.auto_match_button.setMinimumWidth(116)
        self.display_mode.setMinimumWidth(104)
        self.normalization_combo.setMinimumWidth(92)
        self.laser_wavelength_spin.setRange(0.0, 2000.0)
        self.laser_wavelength_spin.setDecimals(1)
        self.laser_wavelength_spin.setSingleStep(1.0)
        self.laser_wavelength_spin.setValue(532.0)
        self.laser_wavelength_spin.setSuffix(" nm")
        self.laser_wavelength_spin.setSpecialValueText("All lasers")
        self.laser_wavelength_spin.setToolTip("User laser wavelength for Raman references. Set 0 to show all.")
        self.laser_wavelength_spin.setKeyboardTracking(False)
        self.laser_wavelength_spin.setMinimumWidth(96)
        self.multi_offset_slider.setRange(0, 100)
        self.multi_offset_slider.setValue(10)
        self.multi_offset_slider.setSingleStep(1)
        self.multi_offset_slider.setPageStep(5)
        self.multi_offset_slider.setMinimumWidth(130)
        self.multi_offset_slider.setToolTip("Vertical distance between experimental spectra in All selected mode.")
        self.multi_offset_slider.setEnabled(False)
        self.multi_offset_value.setMinimumWidth(38)
        self.multi_offset_value.setEnabled(False)

        processing_row.addWidget(self.smooth_button)
        processing_row.addWidget(self.remove_background_button)
        processing_row.addWidget(self.despike_button)
        processing_row.addWidget(self.reset_data_button)
        processing_row.addWidget(self.auto_match_button)
        processing_row.addStretch(1)

        display_row.addWidget(QLabel("Show"))
        display_row.addWidget(self.display_mode)
        display_row.addWidget(QLabel("Normalize"))
        display_row.addWidget(self.normalization_combo)
        display_row.addWidget(QLabel("Laser"))
        display_row.addWidget(self.laser_wavelength_spin)
        display_row.addSpacing(8)
        distance_label = QLabel("Distance")
        distance_label.setToolTip("Vertical distance between spectra in All selected mode.")
        display_row.addWidget(distance_label)
        display_row.addWidget(self.multi_offset_slider, 1)
        display_row.addWidget(self.multi_offset_value)
        display_row.addStretch(1)
        layout.addLayout(processing_row)
        layout.addLayout(display_row)


class ProjectControlsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.new_button = QPushButton("New project")
        self.load_button = QPushButton("Load project")
        self.save_button = QPushButton("Save project")
        self.export_button = QPushButton("Export")
        self.import_button = QPushButton("Import")
        self.references_button = QPushButton("Create reference")
        self.move_up_button = QToolButton()
        self.move_down_button = QToolButton()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.new_button.setMinimumHeight(34)
        self.load_button.setMinimumHeight(34)
        self.save_button.setMinimumHeight(34)
        self.export_button.setMinimumHeight(34)
        self.import_button.setMinimumHeight(38)
        self.references_button.setMinimumHeight(38)
        self.new_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.load_button.setStyleSheet(_glass_button_style("#0b8043", "#35a96c"))
        self.save_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.export_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.import_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.references_button.setStyleSheet(_glass_button_style("#7b4fb3", "#a782d8"))

        self.move_up_button.setText("Up")
        self.move_down_button.setText("Down")

        order_row = QHBoxLayout()
        order_row.setContentsMargins(0, 0, 0, 0)
        order_row.setSpacing(4)
        order_row.addWidget(QLabel("Order"))
        order_row.addWidget(self.move_up_button)
        order_row.addWidget(self.move_down_button)
        order_row.addStretch(1)

        layout.addWidget(self.new_button)
        layout.addWidget(self.load_button)
        layout.addWidget(self.save_button)
        layout.addWidget(self.export_button)
        layout.addWidget(self.import_button)
        layout.addWidget(self.references_button)
        layout.addLayout(order_row)


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(about_html())
        browser.anchorClicked.connect(QDesktopServices.openUrl)
        browser.setMinimumHeight(240)
        layout.addWidget(browser, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_button = QPushButton("Close")
        close_button.setMinimumWidth(96)
        close_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)


class CandidateTableWidget(QTableWidget):
    HEADERS = ["Source", "Entry", "Formula", "Compound", "Method", "Orientation", "Polarization", "Match (%)", "Bands", "Shift"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.HEADERS), parent)
        self.setToolTip(
            "Candidate list\n"
            "Single click: preview this candidate.\n"
            "Double click: add this candidate to selected compounds."
        )
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self._resize_columns()

    def set_results(self, results: list[VibrationalMatchResult]) -> None:
        self.setRowCount(len(results))
        for row, result in enumerate(results):
            values = [
                result.candidate.source,
                result.candidate.entry_id,
                result.candidate.formula,
                result.candidate.name,
                result.candidate.kind.value.upper(),
                result.candidate.metadata.get("orientation", "unknown"),
                result.candidate.metadata.get("polarization", "unknown"),
                f"{result.score.combined:.1f}",
                f"{result.score.matched_features}/{result.score.total_features}",
                f"{result.score.x_shift:.1f}",
            ]
            for column, value in enumerate(values):
                self.setItem(row, column, QTableWidgetItem(value))

    def set_records(self, records: list[CandidateRecord]) -> None:
        self.setRowCount(len(records))
        for row, record in enumerate(records):
            values = [
                record.source,
                record.entry_id,
                record.formula,
                record.name,
                record.kind.value.upper(),
                record.metadata.get("orientation", "unknown"),
                record.metadata.get("polarization", "unknown"),
                "-",
                "-",
                "-",
            ]
            for column, value in enumerate(values):
                self.setItem(row, column, QTableWidgetItem(value))

    def _resize_columns(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((76, 92, 150, 260, 72, 104, 108, 82, 82, 72)):
            self.setColumnWidth(column, width)


class SelectedCompoundsTableWidget(QTableWidget):
    HEADERS = ["Color", "Compound", "Method", "Bands", "Match (%)"]
    visibilityChanged = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.HEADERS), parent)
        self.setToolTip("Selected compounds")
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(150)
        self.itemChanged.connect(self._on_item_changed)
        self._resize_columns()

    def set_selected(
        self,
        results: list[VibrationalMatchResult],
        visible_keys: set[str] | None = None,
        colors: dict[str, str] | None = None,
    ) -> None:
        visible_keys = visible_keys if visible_keys is not None else {result.candidate.key for result in results}
        colors = colors or {}
        blocked = self.blockSignals(True)
        self.setRowCount(len(results))
        for row, result in enumerate(results):
            key = result.candidate.key
            color_text = colors.get(key, REFERENCE_OVERLAY_COLORS[row % len(REFERENCE_OVERLAY_COLORS)])
            values = [
                color_text,
                result.candidate.name,
                result.candidate.kind.value.upper(),
                f"{result.score.matched_features}/{result.score.total_features}",
                f"{result.score.combined:.1f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    color = QColor(value)
                    item.setBackground(color)
                    item.setForeground(QColor("#ffffff"))
                    item.setData(Qt.ItemDataRole.UserRole, key)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(Qt.CheckState.Checked if key in visible_keys else Qt.CheckState.Unchecked)
                self.setItem(row, column, item)
        self.blockSignals(blocked)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        key = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if key:
            self.visibilityChanged.emit(key, item.checkState() == Qt.CheckState.Checked)

    def _resize_columns(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((82, 190, 76, 82, 82)):
            self.setColumnWidth(column, width)


class VibrationalFinderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1500, 850)
        self.settings = QSettings("IRRamanPhaseFinder", "Standalone")
        self._header_persistence_connected = False
        self._header_save_timer = QTimer(self)
        self._header_save_timer.setSingleShot(True)
        self._header_save_timer.setInterval(350)
        self._header_save_timer.timeout.connect(self._flush_table_header_states)
        self.setAcceptDrops(True)
        self.theme_preference = "System"
        self.current_theme = self._system_theme()
        self.plot_settings_panel: PlotViewSettingsWidget | None = None
        self.plot_view_settings = PlotViewSettings()
        self.legend_item = None
        self.cursor_position_line = None
        self._auto_line_colors = True
        self._active_display_offset = 0.0
        self.observed_spectrum_plot_context: dict[str, dict[str, float]] = {}
        self._reference_label_boxes: list[tuple[float, float, float, float]] = []
        self._default_splitter_handle_width = 4
        self._pinned_splitter_sizes: dict[int, list[int]] = {}
        self._pinned_splitter_connections: set[int] = set()
        self._restoring_pinned_splitter = False
        self.setStyleSheet(_window_style(self.current_theme))

        self.active_spectrum: ObservedSpectrum | None = None
        self.raman_spectra: list[ObservedSpectrum] = []
        self.ftir_spectra: list[ObservedSpectrum] = []
        self.reference_records: list[CandidateRecord] = []
        self.reference_spectra: list[ReferenceSpectrum] = []
        self._current_preview_reference: ReferenceSpectrum | None = None
        self._current_preview_result: VibrationalMatchResult | None = None
        self.removed_user_reference_keys: set[str] = set()
        self.user_libraries: list[
            UserLibrarySource | FolderLibrarySource | CifStructureSource | EditableReferenceSource
        ] = []
        self.rruff_source = RruffSource()
        self.rod_source = RodSource()
        self.jarvis_source = JarvisDftSource()
        self.openspecy_source = OpenSpecyLibrarySource()
        self.results: list[VibrationalMatchResult] = []
        self.browse_records: list[CandidateRecord] = []
        self.selected_results: list[VibrationalMatchResult] = []
        self.spectrum_profile_states: dict[str, SpectrumProfileState] = {}
        self.active_profile_spectrum_key: str | None = None
        self._profile_state_loading = False
        self.visible_observed_paths: set[str] = set()
        self.visible_selected_candidate_keys: set[str] = set()
        self.selected_candidate_colors: dict[str, str] = {}
        self._updating_project_tree = False
        self.element_states: dict[str, str] = {}
        self.required_elements: set[str] = set()
        self.optional_elements: set[str] = set()
        self.excluded_elements: set[str] = set()
        self.selected_element_order: list[str] = []
        self.exclude_all_other_elements = True
        self._background_tasks: list[BackgroundTaskHandle] = []
        self._original_observed: dict[str, ObservedSpectrum] = {}
        self.sample_metadata: dict[str, dict[str, str]] = {}
        self.sample_bands: dict[str, list] = {}
        self._updating_card_tables = False
        self._preprocessing_panel: QWidget | None = None
        self._preprocessing_panel_key: str | None = None
        self._preprocessing_cancel_callback = None

        self._create_sidebar()
        self._create_center()
        self._create_right_tabs()
        self._create_main_splitter()
        QApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme("System") if self.theme_preference == "System" else None)
        self._apply_theme(self.theme_preference)
        QTimer.singleShot(0, self._load_saved_user_references)
        QTimer.singleShot(0, self._restore_ui_state)

    def _create_sidebar(self) -> None:
        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(170)
        self.sidebar.setMaximumWidth(360)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)

        self.project_controls = ProjectControlsWidget()
        self.project_controls.import_button.clicked.connect(self._show_import_dialog)
        self.project_controls.references_button.clicked.connect(self._create_reference)
        self.project_controls.new_button.clicked.connect(self._new_project)
        self.project_controls.load_button.clicked.connect(self._load_project_file)
        self.project_controls.save_button.clicked.connect(self._save_project_file)
        export_menu = QMenu(self.project_controls.export_button)
        export_menu.addAction("Active spectrum CSV...", self._export_active_spectrum)
        export_menu.addAction("Candidate table CSV...", self._export_candidate_table)
        export_menu.addAction("Plot image...", self._export_plot_image)
        self.project_controls.export_button.setMenu(export_menu)
        sidebar_layout.addWidget(self.project_controls)

        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderLabel("Data")
        self.project_tree.setToolTip(
            "Project tree\n"
            "Select a Raman or FTIR spectrum to make it active.\n"
            "Select a reference spectrum to preview it."
        )
        self.project_tree.itemSelectionChanged.connect(self._on_project_tree_selection_changed)
        self.project_tree.itemChanged.connect(self._on_project_tree_item_changed)
        sidebar_layout.addWidget(self.project_tree, 1)

        self.cursor_label = QLabel("cm-1: -    I: -")
        self.cursor_label.setStyleSheet(
            "background: #20262d; border: 1px solid #3b4652; border-radius: 3px; "
            "color: #d7e3f4; font-weight: 700; padding: 6px 8px;"
        )
        self.cursor_label.setMinimumHeight(30)
        sidebar_layout.addWidget(self.cursor_label)

        self._refresh_project_tree()

    def _create_center(self) -> None:
        self.center = QWidget()
        self.center_layout = QVBoxLayout(self.center)
        self.center_layout.setContentsMargins(6, 6, 6, 6)

        self.action_bar = FinderActionBar()
        self.action_bar.smooth_button.clicked.connect(self._smooth_active_spectrum)
        self.action_bar.remove_background_button.clicked.connect(self._remove_background_active_spectrum)
        self.action_bar.despike_button.clicked.connect(self._despike_active_spectrum)
        self.action_bar.reset_data_button.clicked.connect(self._reset_active_spectrum_data)
        self.action_bar.auto_match_button.clicked.connect(self._auto_match_active_spectrum)
        self.action_bar.normalization_combo.currentIndexChanged.connect(self._on_normalization_changed)
        self.action_bar.display_mode.currentTextChanged.connect(self._on_display_mode_changed)
        self.action_bar.multi_offset_slider.valueChanged.connect(self._on_multi_offset_changed)
        self.action_bar.laser_wavelength_spin.valueChanged.connect(self._on_laser_wavelength_changed)
        self.center_layout.addWidget(self.action_bar)

        self.match_plot = create_vibrational_plot_widget()
        setattr(self.match_plot.plotItem.vb, "double_click_reset_callback", self._reset_plot_view)
        self.match_plot.setMinimumSize(1, 1)
        self.match_plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.match_plot.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.match_plot.customContextMenuRequested.connect(self._show_plot_context_menu)
        self.match_plot.scene().sigMouseMoved.connect(self._update_cursor_readout)

        self.candidate_table = CandidateTableWidget()
        self.candidate_table.currentCellChanged.connect(self._preview_candidate_row)
        self.candidate_table.cellDoubleClicked.connect(lambda _row, _column: self._add_selected_candidate())

        self.candidate_panel = QWidget()
        candidate_layout = QVBoxLayout(self.candidate_panel)
        candidate_layout.setContentsMargins(0, 0, 0, 0)
        candidate_layout.setSpacing(4)
        candidate_layout.addWidget(QLabel("Candidate list"))
        candidate_layout.addWidget(self.candidate_table, 1)

        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.plot_canvas = QWidget()
        self.plot_canvas.setObjectName("plotCanvas")
        self.plot_canvas.setStyleSheet("QWidget#plotCanvas { background: #d7dadd; border: 1px solid #56616c; }")
        plot_canvas_layout = QGridLayout(self.plot_canvas)
        plot_canvas_layout.setContentsMargins(0, 0, 0, 0)
        plot_canvas_layout.setSpacing(0)
        plot_canvas_layout.addWidget(self.match_plot, 0, 0)
        self.center_splitter.addWidget(self.plot_canvas)
        self.center_splitter.addWidget(self.candidate_panel)
        self.center_splitter.setStretchFactor(0, 3)
        self.center_splitter.setStretchFactor(1, 2)
        self.center_splitter.setSizes([520, 260])
        self.center_layout.addWidget(self.center_splitter, 1)

    def _create_right_tabs(self) -> None:
        self.right_panel = QWidget()
        self.right_panel.setMinimumWidth(460)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        right_controls = QWidget()
        right_controls_layout = QHBoxLayout(right_controls)
        right_controls_layout.setContentsMargins(0, 0, 0, 0)
        right_controls_layout.setSpacing(6)
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(460)
        self.pin_panels_button = QPushButton("Pin")
        self.pin_panels_button.setCheckable(True)
        self.pin_panels_button.setToolTip("Lock panel positions and splitter handles.")
        self.pin_panels_button.setMinimumSize(82, 34)
        self.pin_panels_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.pin_panels_button.toggled.connect(self._set_panels_pinned)
        self.about_button = QPushButton("?")
        self.about_button.setToolTip("About IR/Raman Phase Finder")
        self.about_button.setMinimumSize(42, 34)
        self.about_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.about_button.clicked.connect(self._show_about_dialog)
        right_controls_layout.addStretch(1)
        right_controls_layout.addWidget(self.pin_panels_button)
        right_controls_layout.addWidget(self.about_button)
        right_layout.addWidget(right_controls)
        right_layout.addWidget(self.right_tabs, 1)
        self.right_tabs.addTab(self._elements_tab(), "Elements")
        self.right_tabs.addTab(self._compound_card_tab(), "Card")
        self.right_tabs.addTab(self._database_tab(), "Databases")
        self.right_tabs.addTab(self._plot_view_tab(), "View")

    def _create_main_splitter(self) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.center)
        self.main_splitter.addWidget(self.right_panel)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 0)
        self.main_splitter.setSizes([190, 880, 500])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.main_splitter)
        self.setCentralWidget(root)

    def _elements_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.elements_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(self.elements_splitter)

        element_panel = QWidget()
        element_layout = QVBoxLayout(element_panel)
        element_layout.setContentsMargins(0, 0, 0, 0)
        element_layout.setSpacing(6)
        element_layout.addWidget(QLabel("Element filters"))
        self.element_table = PeriodicTableWidget()
        self.element_table.leftClicked.connect(self._toggle_required_element)
        self.element_table.rightClicked.connect(self._toggle_optional_element)
        element_layout.addWidget(self.element_table, 1)
        self.elements_splitter.addWidget(element_panel)

        controls_panel = QWidget()
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)
        self.element_gate_label = QLabel("Required: none    Optional: none")
        self.element_gate_label.setWordWrap(True)

        self.reference_search_input = QLineEdit()
        self.reference_search_input.setPlaceholderText("Formula / compound name / entry id")
        self.reference_search_input.setClearButtonEnabled(True)
        self.reference_search_input.returnPressed.connect(self._search_active_spectrum)

        origin_row = QHBoxLayout()
        origin_row.setContentsMargins(0, 0, 0, 0)
        origin_row.addWidget(QLabel("Reference data"))
        self.reference_origin_combo = QComboBox()
        self.reference_origin_combo.addItem("Experimental + calculated", "both")
        self.reference_origin_combo.addItem("Experimental", "experimental")
        self.reference_origin_combo.addItem("Calculated", "calculated")
        self.reference_origin_combo.setToolTip("Filter measured and calculated reference data.")
        self.reference_origin_combo.currentIndexChanged.connect(
            lambda _index: self._search_active_spectrum()
        )
        origin_row.addWidget(self.reference_origin_combo, 1)

        method_row = QHBoxLayout()
        method_row.setContentsMargins(0, 0, 0, 0)
        self.include_raman_checkbox = QCheckBox("Raman references")
        self.include_ftir_checkbox = QCheckBox("FTIR references")
        self.include_raman_checkbox.setChecked(True)
        self.include_ftir_checkbox.setChecked(True)
        method_row.addWidget(self.include_raman_checkbox)
        method_row.addWidget(self.include_ftir_checkbox)
        method_row.addStretch(1)

        filter_buttons = QWidget()
        filter_buttons_layout = QHBoxLayout(filter_buttons)
        filter_buttons_layout.setContentsMargins(0, 0, 0, 0)
        filter_buttons_layout.setSpacing(6)
        self.find_by_elements_button = QPushButton("Find")
        self.find_by_elements_button.setMinimumHeight(34)
        self.find_by_elements_button.setStyleSheet(_glass_button_style("#8a5a16", "#c68a2e"))
        self.reset_elements_button = QPushButton("Reset table")
        self.reset_elements_button.setMinimumHeight(34)
        self.reset_elements_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.find_by_elements_button.clicked.connect(self._search_active_spectrum)
        self.reset_elements_button.clicked.connect(self._reset_element_filters)
        filter_buttons_layout.addWidget(self.find_by_elements_button)
        filter_buttons_layout.addWidget(self.reset_elements_button)
        controls_layout.addWidget(filter_buttons)

        self.selected_table = SelectedCompoundsTableWidget()
        self.selected_table.visibilityChanged.connect(self._on_selected_reference_visibility_changed)
        controls_layout.addWidget(QLabel("Selected compounds"))
        controls_layout.addWidget(self.selected_table, 1)
        self.elements_splitter.addWidget(controls_panel)
        self.elements_splitter.setStretchFactor(0, 1)
        self.elements_splitter.setStretchFactor(1, 2)
        self.elements_splitter.setSizes([320, 430])
        self._refresh_element_table()
        return widget

    def _compound_card_tab(self) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        self.card_inner_tabs = QTabWidget()
        layout.addWidget(self.card_inner_tabs)

        sample_scroll = QScrollArea()
        sample_scroll.setWidgetResizable(True)
        sample_scroll.setFrameShape(QFrame.Shape.NoFrame)
        sample_content = QWidget()
        sample_scroll.setWidget(sample_content)
        sample_layout = QVBoxLayout(sample_content)
        sample_layout.setContentsMargins(12, 12, 12, 12)
        sample_layout.setSpacing(10)
        self.sample_card_title = QLabel("No sample selected")
        self.sample_card_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sample_card_title.setStyleSheet(self._section_style())
        sample_layout.addWidget(self.sample_card_title)
        sample_layout.addWidget(self._section_title("Sample provenance and measurement"))
        self.sample_card_fields: dict[str, QLineEdit] = {}
        sample_form = QFormLayout()
        for key, caption in (
            ("name", "Sample name"),
            ("source_path", "Source file"),
            ("method", "Method"),
            ("laser_nm", "Laser wavelength, nm"),
            ("orientation", "Orientation"),
            ("polarization", "Polarization"),
            ("instrument", "Instrument"),
            ("notes", "Notes"),
        ):
            field = QLineEdit()
            field.setClearButtonEnabled(key not in {"source_path", "method"})
            field.setReadOnly(key in {"source_path", "method"})
            field.editingFinished.connect(self._save_sample_card_fields)
            self.sample_card_fields[key] = field
            sample_form.addRow(caption, field)
        sample_layout.addLayout(sample_form)
        sample_layout.addWidget(self._section_title("Sample peaks"))
        self.sample_band_table = self._card_table(
            ["Position cm-1", "Intensity", "FWHM", "Mode", "Symmetry", "Assignment", "Confidence", "Comment"]
        )
        self.sample_band_table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        self.sample_band_table.cellChanged.connect(self._on_sample_band_cell_changed)
        self.sample_band_table.setMinimumHeight(300)
        sample_layout.addWidget(self.sample_band_table)
        self.card_inner_tabs.addTab(sample_scroll, "Sample")

        reference_scroll = QScrollArea()
        reference_scroll.setWidgetResizable(True)
        reference_scroll.setFrameShape(QFrame.Shape.NoFrame)
        reference_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        reference_content = QWidget()
        reference_scroll.setWidget(reference_content)
        card_layout = QVBoxLayout(reference_content)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(10)

        self.card_title = QLabel("Selected compound")
        self.card_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card_title.setStyleSheet(self._section_style())
        card_layout.addWidget(self.card_title)

        self.card_labels: dict[str, QLabel] = {}
        card_layout.addWidget(self._section_title("Compound classification"))
        card_layout.addLayout(
            self._field_grid(
                [
                    ("Name", "Name"),
                    ("Formula", "Formula"),
                    ("Method", "Method"),
                    ("Source", "Source"),
                    ("Entry", "Entry"),
                    ("Quality", "Quality"),
                    ("Orientation", "Orientation"),
                    ("Polarization", "Polarization"),
                ]
            )
        )

        card_layout.addWidget(self._section_title("Spectral match"))
        card_layout.addLayout(
            self._field_grid(
                [
                    ("Match", "Match"),
                    ("Position score", "Position score"),
                    ("Intensity score", "Intensity score"),
                    ("Correlation", "Correlation"),
                    ("Coverage", "Coverage"),
                    ("X shift", "X shift"),
                ]
            )
        )

        card_layout.addWidget(self._section_title("Reference availability"))
        card_layout.addLayout(
            self._field_grid(
                [
                    ("Raman available", "Raman available"),
                    ("FTIR available", "FTIR available"),
                    ("XRD available", "XRD available"),
                    ("Reference path", "Reference path"),
                ]
            )
        )

        card_layout.addWidget(self._section_title("Observed and reference peaks"))
        self.band_table = self._card_table(
            ["Observed cm-1", "Reference cm-1", "Delta", "Intensity", "FWHM", "Mode", "Symmetry", "Assignment"]
        )
        self.band_table.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
        self.band_table.cellChanged.connect(self._on_reference_band_cell_changed)
        self.band_table.setMinimumHeight(220)
        card_layout.addWidget(self.band_table)
        self.card_inner_tabs.addTab(reference_scroll, "Reference")
        return outer

    def _database_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.database_table = QTableWidget(0, 5)
        self.database_table.setHorizontalHeaderLabels(["Database", "Status", "Details", "Records", "Size"])
        self.database_table.verticalHeader().setVisible(False)
        self.database_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.database_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.database_table.setAlternatingRowColors(True)
        self.database_table.setMinimumHeight(220)
        database_header = self.database_table.horizontalHeader()
        database_header.setStretchLastSection(False)
        for column in range(self.database_table.columnCount()):
            database_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((130, 92, 330, 82, 86)):
            self.database_table.setColumnWidth(column, width)
        layout.addWidget(self.database_table)
        self._update_database_table()

        layout.addWidget(self._section_title("Databases used for search"))
        source_box = QWidget()
        source_layout = QGridLayout(source_box)
        source_layout.setContentsMargins(0, 0, 0, 0)
        self.source_checks: dict[str, QCheckBox] = {}
        source_labels = [
            "User Library",
            "RRUFF",
            "ROD",
            "OpenSpecy",
            "JARVIS-DFT",
        ]
        for index, label in enumerate(source_labels):
            checkbox = QCheckBox(label)
            enabled = (
                label in {"User Library", "RRUFF"}
                or (label == "ROD" and bool(self.rod_source.search(SourceQuery())))
                or (label == "OpenSpecy" and bool(self.openspecy_source.search(SourceQuery())))
                or (label == "JARVIS-DFT" and self.jarvis_source.indexed_count() > 0)
            )
            checkbox.setChecked(label in {"User Library", "RRUFF"} or (label in {"ROD", "OpenSpecy", "JARVIS-DFT"} and enabled))
            checkbox.setEnabled(enabled)
            self.source_checks[label] = checkbox
            source_layout.addWidget(checkbox, index // 2, index % 2)
        layout.addWidget(source_box)

        layout.addWidget(self._section_title("Database management"))
        layout.addWidget(
            self._management_row(
                "User reference library",
                [
                    ("Open list", self._manage_user_references, "open"),
                    ("Create reference", self._create_reference, "create"),
                    ("Clear", self._clear_user_libraries, "clear"),
                ],
            )
        )
        layout.addWidget(
            self._management_row(
                "SQL line indexes",
                [
                    ("Update all SQL indexes", self._build_all_band_indexes, "sql"),
                    ("Clear all SQL indexes", self._clear_all_band_indexes, "clear"),
                ],
            )
        )
        self.rruff_archive_combo = QComboBox()
        for archive in self.rruff_source.available_archives():
            cache_text = "cached" if archive.is_cached else "not cached"
            self.rruff_archive_combo.addItem(f"{archive.label} ({cache_text})", archive.key)
        self._set_rruff_archive_combo_key("excellent_unoriented")
        layout.addWidget(self._rruff_archive_row())
        layout.addWidget(self._management_row("RRUFF downloadable ZIP database", [("Download / update", self._update_rruff, "download"), ("Clear cache", self._clear_rruff, "clear")]))
        layout.addWidget(
            self._management_row(
                "Raman Open Database (CC0)",
                [("Download / update", self._update_rod, "download"), ("Clear cache", self._clear_rod, "clear")],
            )
        )
        layout.addWidget(
            self._management_row(
                "JARVIS-DFT calculated spectra",
                [("Download / update", self._update_jarvis, "download"), ("Clear cache", self._clear_jarvis, "clear")],
            )
        )
        self.openspecy_library_combo = QComboBox()
        for library in self.openspecy_source.available_libraries():
            cache_text = "cached" if library.is_cached else "not cached"
            self.openspecy_library_combo.addItem(f"{library.label} ({cache_text})", library.key)
        self._set_openspecy_library_combo_key("medoid_derivative")
        layout.addWidget(self._openspecy_library_row())
        layout.addWidget(self._management_row("OpenSpecy downloadable RDS library", [("Download / update", self._update_openspecy, "download"), ("Clear cache", self._clear_openspecy, "clear")]))
        layout.addWidget(
            self._management_row(
                "External spectrum search",
                [
                    ("Search SDBS", lambda: self._open_external_source("SDBS"), "open"),
                    ("Search NIST", lambda: self._open_external_source("NIST"), "open"),
                    ("Search SpectraBase", lambda: self._open_external_source("SpectraBase"), "open"),
                ],
            )
        )
        layout.addStretch(1)
        return widget

    def _rruff_archive_row(self) -> QWidget:
        row = QWidget()
        layout = QFormLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.rruff_archive_combo.setToolTip(
            "Choose which official RRUFF ZIP archive to download and index. "
            "Use unoriented archives for typical unpolarized lab Raman spectra."
        )
        layout.addRow("RRUFF archive", self.rruff_archive_combo)
        return row

    def _openspecy_library_row(self) -> QWidget:
        row = QWidget()
        layout = QFormLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.openspecy_library_combo.setToolTip(
            "Choose which official OpenSpecy RDS library to download. "
            "Medoid libraries are usually smaller and better for first tests."
        )
        layout.addRow("OpenSpecy library", self.openspecy_library_combo)
        return row

    def _plot_view_tab(self) -> QWidget:
        self.plot_settings_panel = PlotViewSettingsWidget()
        self.plot_settings_panel.settingsChanged.connect(self._apply_plot_view_settings)
        self.plot_settings_panel.xAxisUnitChanged.connect(self._on_x_axis_unit_changed)
        self.plot_settings_panel.referenceViewChanged.connect(
            lambda _mode: self._on_reference_view_changed()
        )
        QTimer.singleShot(0, lambda: self._apply_plot_view_settings(self.plot_settings_panel.settings()))
        QTimer.singleShot(0, self._update_profile_view_context)
        return self.plot_settings_panel

    def _axis_label(self, label: str, unit: str) -> str:
        unit = unit.strip()
        return f"{label} [{unit}]" if unit else label

    def _apply_plot_view_settings(self, settings: PlotViewSettings) -> None:
        self.plot_view_settings = settings
        self.match_plot.setBackground(settings.plot_background)
        if settings.plot_border_visible and settings.plot_border_width > 0:
            self.match_plot.setStyleSheet(
                f"border: {settings.plot_border_width}px solid {settings.plot_border_color};"
            )
        else:
            self.match_plot.setStyleSheet("border: 0;")

        self.match_plot.setTitle(
            settings.title_text if settings.title_visible else "",
            color=settings.title_color,
            size=f"{settings.title_font_size}pt",
        )
        axis_visible = {
            "bottom": settings.bottom_axis_visible,
            "top": settings.top_axis_visible,
            "left": settings.left_axis_visible,
            "right": settings.right_axis_visible,
        }
        axis_values_visible = {
            "bottom": settings.bottom_axis_values_visible,
            "top": settings.top_axis_values_visible,
            "left": settings.left_axis_values_visible,
            "right": settings.right_axis_values_visible,
        }
        axis_labels = {
            "bottom": (settings.bottom_axis_label, settings.bottom_axis_unit, settings.bottom_axis_label_visible),
            "top": (settings.top_axis_label, settings.top_axis_unit, settings.top_axis_label_visible),
            "left": (settings.left_axis_label, settings.left_axis_unit, settings.left_axis_label_visible),
            "right": (settings.right_axis_label, settings.right_axis_unit, settings.right_axis_label_visible),
        }
        axis_font = QFont()
        axis_font.setPointSize(settings.tick_font_size)
        for axis_name in ("bottom", "top", "left", "right"):
            visible = bool(axis_visible[axis_name])
            axis = self.match_plot.getAxis(axis_name)
            self.match_plot.showAxis(axis_name, visible)
            axis.setVisible(visible)
            axis.setPen(pg.mkPen(settings.axis_color, width=settings.axis_width))
            axis.setTextPen(pg.mkPen(settings.axis_color))
            axis.setTickFont(axis_font)
            axis.setStyle(
                showValues=bool(visible and axis_values_visible[axis_name]),
                tickLength=abs(int(settings.tick_length)) if visible else 0,
            )
            label, unit, label_visible = axis_labels[axis_name]
            label, unit = self._display_axis_label(axis_name, label, unit)
            self.match_plot.setLabel(
                axis_name,
                self._axis_label(label, unit) if visible and label_visible else "",
                color=settings.axis_color,
                **{"font-size": f"{settings.label_font_size}pt"},
            )
            major = settings.x_major_tick_spacing if axis_name in {"bottom", "top"} else settings.y_major_tick_spacing
            minor = settings.x_minor_tick_spacing if axis_name in {"bottom", "top"} else settings.y_minor_tick_spacing
            try:
                if major > 0.0 or minor > 0.0:
                    axis.setTickSpacing(major=major if major > 0.0 else None, minor=minor if minor > 0.0 else None)
                else:
                    axis.setTickSpacing()
            except Exception:
                pass
        self._configure_axis_tick_formatters()

        self.match_plot.showGrid(
            x=bool(settings.grid_visible),
            y=bool(settings.grid_visible),
            alpha=max(0.0, min(float(settings.grid_alpha), 1.0)) if settings.grid_visible else 0.0,
        )
        self._set_legend_visible(settings.legend_visible)
        self._set_cursor_vertical_line_enabled(settings.cursor_vertical_line_visible)
        self._apply_plot_view_aspect()
        self._redraw_plot()

    def _apply_plot_view_aspect(self) -> None:
        aspect = getattr(self.plot_view_settings, "aspect_ratio", None)
        if aspect is None:
            self.match_plot.setMinimumSize(1, 1)
            self.match_plot.setMaximumSize(16777215, 16777215)
            self.match_plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.match_plot.updateGeometry()
            return
        source_width = max(int(self.plot_canvas.width()) - 22, 260) if hasattr(self, "plot_canvas") else 900
        source_height = max(int(self.plot_canvas.height()) - 22, 220) if hasattr(self, "plot_canvas") else 520
        target_width = source_width
        target_height = int(target_width / max(float(aspect), 0.1))
        if target_height > source_height:
            target_height = source_height
            target_width = int(target_height * float(aspect))
        self.match_plot.setMinimumSize(240, 180)
        self.match_plot.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.match_plot.setFixedSize(max(240, target_width), max(180, target_height))
        self.match_plot.updateGeometry()

    def _set_legend_visible(self, visible: bool) -> None:
        if visible:
            if self.legend_item is None:
                self.legend_item = self.match_plot.addLegend()
            self.legend_item.setVisible(True)
            try:
                self.legend_item.setLabelTextSize(f"{self.plot_view_settings.legend_font_size}pt")
            except Exception:
                pass
            try:
                self.legend_item.setLabelTextColor(getattr(self.plot_view_settings, "legend_color", "#111111") or "#111111")
            except Exception:
                pass
            return
        if self.legend_item is not None:
            self.legend_item.setVisible(False)

    def _prepare_legend_for_image_export(self, scale: float) -> dict | None:
        legend = self.legend_item
        if legend is None or scale <= 1.0:
            return None
        state = {
            "label_size": legend.opts.get("labelTextSize", f"{self.plot_view_settings.legend_font_size}pt"),
            "horizontal_spacing": legend.layout.horizontalSpacing(),
            "vertical_spacing": legend.layout.verticalSpacing(),
            "samples": [],
        }
        base_font = max(float(getattr(self.plot_view_settings, "legend_font_size", 10)), 1.0)
        legend.setLabelTextSize(f"{base_font * scale:.3f}pt")
        legend.layout.setHorizontalSpacing(max(1.0, float(legend.layout.horizontalSpacing()) * scale))
        legend.layout.setVerticalSpacing(float(legend.layout.verticalSpacing()) * scale)
        for sample, _label in legend.items:
            state["samples"].append(
                (
                    sample,
                    float(sample.minimumWidth()),
                    float(sample.maximumWidth()),
                    float(sample.minimumHeight()),
                    float(sample.maximumHeight()),
                )
            )
            sample.setFixedWidth(max(1.0, float(sample.width()) * scale))
            sample.setFixedHeight(max(1.0, float(sample.height()) * scale))
        legend.updateSize()
        legend.update()
        return state

    def _restore_legend_after_image_export(self, state: dict | None) -> None:
        legend = self.legend_item
        if legend is None or not state:
            return
        legend.setLabelTextSize(state.get("label_size", f"{self.plot_view_settings.legend_font_size}pt"))
        legend.layout.setHorizontalSpacing(float(state.get("horizontal_spacing", 5.0)))
        legend.layout.setVerticalSpacing(float(state.get("vertical_spacing", 0.0)))
        for sample, min_width, max_width, min_height, max_height in state.get("samples", []):
            sample.setMinimumWidth(min_width)
            sample.setMaximumWidth(max_width)
            sample.setMinimumHeight(min_height)
            sample.setMaximumHeight(max_height)
        legend.updateSize()
        legend.update()

    def _ensure_cursor_position_items(self) -> None:
        if self.cursor_position_line is None:
            pen = pg.mkPen("#5f6368", width=1.2, style=Qt.PenStyle.SolidLine)
            self.cursor_position_line = pg.InfiniteLine(angle=90, movable=False, pen=pen)
            self.cursor_position_line.setZValue(5000)
            self.cursor_position_line.setVisible(False)
        try:
            if self.cursor_position_line.scene() is None:
                self.match_plot.addItem(self.cursor_position_line, ignoreBounds=True)
        except RuntimeError:
            try:
                self.match_plot.addItem(self.cursor_position_line, ignoreBounds=True)
            except Exception:
                pass

    def _set_cursor_vertical_line_enabled(self, visible: bool) -> None:
        self._ensure_cursor_position_items()
        if self.cursor_position_line is not None:
            self.cursor_position_line.setVisible(bool(visible))

    def _update_profile_view_context(self) -> None:
        panel = getattr(self, "plot_settings_panel", None)
        if panel is None:
            return
        active = self.active_spectrum.name if self.active_spectrum is not None else ""
        kind = self.active_spectrum.kind.value.upper() if self.active_spectrum is not None else ""
        panel.set_active_profile_label(f"Active spectrum: {active or '-'} {kind}".strip())
        rows = []
        for result in self.results[:25]:
            rows.append(
                {
                    "_Color": self._plot_reference_color(),
                    "Source": result.candidate.source,
                    "Entry": result.candidate.entry_id,
                    "Compound": result.candidate.name,
                    "Match": f"{result.score.combined:.1f}",
                    "Method": result.candidate.kind.value.upper(),
                }
            )
        panel.set_profile_candidates(rows)

    def _view_plot_area_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["System", "Light", "Dark"])
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["Single", "Multi compare"])
        self.title_visible_checkbox = QCheckBox()
        self.title_visible_checkbox.setChecked(True)
        self.grid_checkbox = QCheckBox()
        self.grid_checkbox.setChecked(False)
        self.grid_checkbox.toggled.connect(lambda value: self.match_plot.showGrid(x=value, y=value, alpha=0.18))
        self.background_input = QLineEdit("#ffffff")
        export_button = QPushButton("Export image...")
        export_button.clicked.connect(self._export_plot_image)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Notes for selected project object")
        layout.addRow("Theme", self.theme_combo)
        layout.addRow("Spectrum view mode", self.view_mode_combo)
        layout.addRow("Title", self.title_visible_checkbox)
        layout.addRow("Grid", self.grid_checkbox)
        layout.addRow("Background", self.background_input)
        layout.addRow("Figure", export_button)
        layout.addRow("Notes", self.notes)
        return widget

    def _view_axes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        grid = QGridLayout()
        grid.addWidget(self._axis_card("Top", default_visible=False), 0, 0)
        grid.addWidget(self._axis_card("Right", default_visible=False), 0, 1)
        grid.addWidget(self._axis_card("Left", default_visible=True), 1, 0)
        grid.addWidget(self._axis_card("Bottom", default_visible=True), 1, 1)
        layout.addLayout(grid)
        common = QFormLayout()
        self.axis_color_input = QLineEdit("#111111")
        self.axis_width_spin = QDoubleSpinBox()
        self.axis_width_spin.setRange(0.5, 4.0)
        self.axis_width_spin.setValue(1.2)
        self.tick_length_spin = QSpinBox()
        self.tick_length_spin.setRange(0, 24)
        self.tick_length_spin.setValue(5)
        common.addRow("Color", self.axis_color_input)
        common.addRow("Width", self.axis_width_spin)
        common.addRow("Tick length", self.tick_length_spin)
        layout.addLayout(common)
        layout.addStretch(1)
        return widget

    def _axis_card(self, title: str, *, default_visible: bool) -> QWidget:
        card = QWidget()
        card.setObjectName("axisCard")
        card.setStyleSheet(
            "QWidget#axisCard { background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 4px; }"
        )
        layout = QFormLayout(card)
        caption = QLabel(title)
        caption.setStyleSheet("font-weight: 700;")
        axis = QCheckBox()
        axis.setChecked(default_visible)
        values = QCheckBox()
        values.setChecked(True)
        label = QCheckBox()
        label.setChecked(True)
        text = QLineEdit("Wavenumber" if title in {"Top", "Bottom"} else "Intensity")
        unit = QLineEdit("cm-1" if title in {"Top", "Bottom"} else "a.u.")
        layout.addRow(caption)
        layout.addRow("Axis", axis)
        layout.addRow("Values", values)
        layout.addRow("Label", label)
        layout.addRow("Text", text)
        layout.addRow("Unit", unit)
        return card

    def _view_lines_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        self.observed_color_input = QLineEdit("#202124")
        self.reference_color_input = QLineEdit("#1a73e8")
        self.background_color_input = QLineEdit("#9aa0a6")
        self.observed_color_input.textEdited.connect(self._line_color_edited)
        self.reference_color_input.textEdited.connect(self._line_color_edited)
        self.observed_width_spin = QDoubleSpinBox()
        self.observed_width_spin.setRange(0.5, 5.0)
        self.observed_width_spin.setValue(1.35)
        self.reference_width_spin = QDoubleSpinBox()
        self.reference_width_spin.setRange(0.5, 5.0)
        self.reference_width_spin.setValue(1.7)
        layout.addRow("Observed color", self.observed_color_input)
        layout.addRow("Observed width", self.observed_width_spin)
        layout.addRow("Reference color", self.reference_color_input)
        layout.addRow("Reference width", self.reference_width_spin)
        layout.addRow("Background color", self.background_color_input)
        return widget

    def _view_markers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QFormLayout(widget)
        self.band_markers_checkbox = QCheckBox()
        self.band_markers_checkbox.setChecked(True)
        self.unassigned_bands_checkbox = QCheckBox()
        self.unassigned_bands_checkbox.setChecked(True)
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(2, 24)
        self.marker_size_spin.setValue(8)
        layout.addRow("Band markers", self.band_markers_checkbox)
        layout.addRow("Unassigned bands", self.unassigned_bands_checkbox)
        layout.addRow("Marker size", self.marker_size_spin)
        return widget

    def _new_project(self) -> None:
        self._close_preprocessing_panel()
        self.active_spectrum = None
        self.raman_spectra.clear()
        self.ftir_spectra.clear()
        self.reference_records.clear()
        self.reference_spectra.clear()
        self.user_libraries.clear()
        self._original_observed.clear()
        self.sample_metadata.clear()
        self.sample_bands.clear()
        self.rruff_source.refresh_index()
        self.openspecy_source.refresh_index()
        self.results.clear()
        self.browse_records.clear()
        self.selected_results.clear()
        self.spectrum_profile_states.clear()
        self.active_profile_spectrum_key = None
        self.visible_observed_paths.clear()
        self.visible_selected_candidate_keys.clear()
        self.selected_candidate_colors.clear()
        self._current_preview_reference = None
        self._current_preview_result = None
        self.element_states.clear()
        self.required_elements.clear()
        self.optional_elements.clear()
        self.excluded_elements.clear()
        self.selected_element_order.clear()
        self.exclude_all_other_elements = True
        self.candidate_table.set_results([])
        self.selected_table.set_selected([], set(), {})
        self._refresh_element_table()
        self._set_card(None)
        self._update_database_table()
        self._refresh_project_tree()
        self._redraw_plot()
        self._load_saved_user_references()

    def _project_file_filter(self) -> str:
        return "IR/Raman projects (*.irraman.json *.json);;All files (*)"

    def _save_project_file(self) -> None:
        self._save_sample_card_fields()
        self._save_active_spectrum_profile_state()
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save IR/Raman project",
            str(Path(self._last_directory()) / "ir_raman_project.irraman.json"),
            self._project_file_filter(),
        )
        if not path:
            return
        if not path.lower().endswith((".irraman.json", ".json")):
            path += ".irraman.json"
        payload = {
            "format": "ir-raman-phase-finder-project",
            "version": 1,
            "active_spectrum_key": self._current_spectrum_profile_key(),
            "visible_observed_paths": sorted(self.visible_observed_paths),
            "spectra": {
                "raman": [self._observed_spectrum_to_project(spectrum) for spectrum in self.raman_spectra],
                "ftir": [self._observed_spectrum_to_project(spectrum) for spectrum in self.ftir_spectra],
            },
            "sample_metadata": self.sample_metadata,
            "sample_bands": {
                key: [self._spectral_band_to_project(band) for band in bands]
                for key, bands in self.sample_bands.items()
            },
            "display": {
                "mode": self.action_bar.display_mode.currentText(),
                "normalize": self.action_bar.normalize_checkbox.isChecked(),
                "laser_nm": self.action_bar.laser_wavelength_spin.value(),
            },
        }
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Save project", f"Could not save project:\n{exc}")
            return
        self.statusBar().showMessage(f"Project saved: {path}", 8000)

    def _load_project_file(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Load IR/Raman project",
            "",
            self._project_file_filter(),
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if payload.get("format") != "ir-raman-phase-finder-project":
                raise ValueError("This is not an IR/Raman Phase Finder project file.")
            spectra = payload.get("spectra") or {}
            raman = [self._observed_spectrum_from_project(item) for item in spectra.get("raman") or []]
            ftir = [self._observed_spectrum_from_project(item) for item in spectra.get("ftir") or []]
            sample_bands = {
                str(key): [self._spectral_band_from_project(item) for item in value or []]
                for key, value in dict(payload.get("sample_bands") or {}).items()
            }
        except Exception as exc:
            QMessageBox.warning(self, "Load project", f"Could not load project:\n{exc}")
            return

        self._new_project()
        self.raman_spectra = raman
        self.ftir_spectra = ftir
        self.sample_metadata = {
            str(key): {str(field): str(value) for field, value in dict(metadata).items()}
            for key, metadata in dict(payload.get("sample_metadata") or {}).items()
        }
        self.sample_bands = sample_bands
        self.visible_observed_paths = set(str(value) for value in payload.get("visible_observed_paths") or [])
        for spectrum in [*self.raman_spectra, *self.ftir_spectra]:
            key = self._spectrum_visibility_key(spectrum)
            self._original_observed[spectrum.source_path] = self._copy_observed_spectrum(spectrum) or spectrum
            self.sample_metadata.setdefault(
                key,
                {
                    "name": spectrum.name,
                    "source_path": spectrum.source_path,
                    "method": spectrum.kind.value.upper(),
                    "laser_nm": "",
                    "orientation": "",
                    "polarization": "",
                    "instrument": "",
                    "notes": "",
                },
            )
            self.sample_bands.setdefault(key, detect_bands(spectrum, BandDetectionOptions(backend="auto", fit_peaks=False)))
        display = payload.get("display") or {}
        mode_index = self.action_bar.display_mode.findText(str(display.get("mode") or "One"))
        if mode_index >= 0:
            self.action_bar.display_mode.setCurrentIndex(mode_index)
        self.action_bar.normalize_checkbox.setChecked(bool(display.get("normalize", self.action_bar.normalize_checkbox.isChecked())))
        try:
            self.action_bar.laser_wavelength_spin.setValue(float(display.get("laser_nm", self.action_bar.laser_wavelength_spin.value())))
        except (TypeError, ValueError):
            pass

        active_key = str(payload.get("active_spectrum_key") or "")
        all_spectra = [*self.raman_spectra, *self.ftir_spectra]
        self.active_spectrum = next(
            (spectrum for spectrum in all_spectra if self._spectrum_visibility_key(spectrum) == active_key),
            all_spectra[0] if all_spectra else None,
        )
        if self.active_spectrum is not None and not self.visible_observed_paths:
            self.visible_observed_paths.add(self._spectrum_visibility_key(self.active_spectrum))
        self.active_profile_spectrum_key = None
        self._activate_spectrum_profile_state(self.active_spectrum)
        self._refresh_project_tree()
        self._refresh_sample_card()
        self._set_card(None)
        self._redraw_plot()
        self.statusBar().showMessage(f"Project loaded: {path}", 8000)

    def _observed_spectrum_to_project(self, spectrum: ObservedSpectrum) -> dict:
        return {
            "x": [float(value) for value in spectrum.x],
            "y": [float(value) for value in spectrum.y],
            "kind": spectrum.kind.value,
            "name": spectrum.name,
            "source_path": spectrum.source_path,
            "x_unit": spectrum.x_unit,
            "y_unit": spectrum.y_unit,
        }

    def _observed_spectrum_from_project(self, payload: dict) -> ObservedSpectrum:
        return ObservedSpectrum(
            x=[float(value) for value in payload.get("x") or []],
            y=[float(value) for value in payload.get("y") or []],
            kind=SignalKind(str(payload.get("kind") or SignalKind.UNKNOWN.value)),
            name=str(payload.get("name") or ""),
            source_path=str(payload.get("source_path") or ""),
            x_unit=str(payload.get("x_unit") or "cm-1"),
            y_unit=str(payload.get("y_unit") or "a.u."),
        )

    def _spectral_band_to_project(self, band: SpectralBand) -> dict:
        return {
            "position": float(band.position),
            "intensity": float(band.intensity),
            "width": float(band.width),
            "mode": band.mode,
            "assignment": band.assignment,
            "symmetry": band.symmetry,
            "polarization": band.polarization,
            "orientation": band.orientation,
            "source_comment": band.source_comment,
            "confidence": float(band.confidence),
        }

    def _spectral_band_from_project(self, payload: dict) -> SpectralBand:
        return SpectralBand(
            position=float(payload.get("position") or 0.0),
            intensity=float(payload.get("intensity") or 0.0),
            width=float(payload.get("width") or 0.0),
            mode=str(payload.get("mode") or ""),
            assignment=str(payload.get("assignment") or ""),
            symmetry=str(payload.get("symmetry") or ""),
            polarization=str(payload.get("polarization") or ""),
            orientation=str(payload.get("orientation") or ""),
            source_comment=str(payload.get("source_comment") or ""),
            confidence=float(payload.get("confidence") or 1.0),
        )

    def dragEnterEvent(self, event) -> None:  # type: ignore[override]
        if self._drop_paths(event):
            event.acceptProposedAction()
            self.statusBar().showMessage("Drop to import spectra or load a reference folder.", 3000)
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drop_paths(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        paths = self._drop_paths(event)
        if not paths:
            super().dropEvent(event)
            return
        event.acceptProposedAction()
        self._import_dropped_paths(paths)

    def _drop_paths(self, event) -> list[Path]:
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return []
        paths: list[Path] = []
        suffixes = set(supported_spectrum_extensions())
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir() or path.suffix.lower() in suffixes:
                paths.append(path)
        return paths

    def _import_dropped_paths(self, paths: list[Path]) -> None:
        imported = 0
        loaded_folders = 0
        failures: list[str] = []
        for path in paths:
            try:
                if path.is_dir():
                    self._load_library_folder_path(str(path))
                    loaded_folders += 1
                    continue
                self._load_experiment_path(str(path), self._kind_from_path(path))
                imported += 1
            except Exception as exc:
                failures.append(f"{path.name}: {exc}")
        if loaded_folders and self.active_spectrum is not None:
            self._search_active_spectrum()
        elif loaded_folders:
            self._browse_reference_sources()
        if failures:
            QMessageBox.warning(self, "Drop import", "Some dropped items could not be imported:\n\n" + "\n".join(failures[:8]))
        message_parts = []
        if imported:
            message_parts.append(f"imported {imported} spectrum/spectra")
        if loaded_folders:
            message_parts.append(f"loaded {loaded_folders} reference folder(s)")
        if message_parts:
            self.statusBar().showMessage("Drop complete: " + ", ".join(message_parts), 7000)

    def _kind_from_path(self, path: Path) -> SignalKind:
        guess = guess_spectrum_metadata(path)
        if guess.kind != SignalKind.UNKNOWN:
            return guess.kind
        text = " ".join([path.stem.lower(), *(part.lower() for part in path.parts)])
        if "ftir" in text or "infrared" in text or re.search(r"(^|[_\-\s])ir($|[_\-\s])", text):
            return SignalKind.FTIR
        return SignalKind.RAMAN

    def _import_scientific_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Raman or FTIR spectra",
            "",
            SPECTRUM_FILE_FILTER,
        )
        for path in paths:
            self._load_experiment_path(path, self._kind_from_path(Path(path)))

    def _show_import_dialog(self) -> None:
        dialog = ImportMethodDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.selected_kind in {SignalKind.RAMAN, SignalKind.FTIR}:
            self._import_experiment(dialog.selected_kind)

    def _show_reference_load_dialog(self) -> None:
        self._create_reference()

    def _import_experiment(self, kind: SignalKind) -> None:
        title = "Import Raman spectra" if kind == SignalKind.RAMAN else "Import FTIR spectra"
        paths, _ = QFileDialog.getOpenFileNames(self, title, "", SPECTRUM_FILE_FILTER)
        for path in paths:
            self._load_experiment_path(path, kind)

    def _user_reference_root(self) -> Path:
        root = app_cache_dir() / "user_references"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _user_reference_cache(self) -> ReferenceSpectrumCache:
        return ReferenceSpectrumCache(self._user_reference_root())

    def _load_saved_user_references(self) -> None:
        root = self._user_reference_root()
        if not any(root.glob("*.vsref")):
            return
        if any(isinstance(source, EditableReferenceSource) and source.path == root for source in self.user_libraries):
            return
        self._add_user_library_source(EditableReferenceSource(root, cache_root=root))

    def _create_reference(self) -> None:
        default_kind = self.active_spectrum.kind if self.active_spectrum is not None else SignalKind.RAMAN
        dialog = ReferenceEditorDialog(
            self,
            default_kind=default_kind,
            laser_nm=self._selected_laser_wavelength_nm(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dialog.payload()
        name = str(payload.get("metadata", {}).get("name") or "untitled-reference")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_.") or "untitled-reference"
        target = self._user_reference_root() / f"{slug}_{int(time.time())}.vsref"
        try:
            write_editable_reference(target, payload)
        except Exception as exc:
            QMessageBox.warning(self, "Reference save failed", str(exc))
            return
        self._replace_editable_reference_source()
        if "User Library" in getattr(self, "source_checks", {}):
            self.source_checks["User Library"].setChecked(True)
        if self.active_spectrum is not None:
            self._search_active_spectrum()
        else:
            self._browse_reference_sources()
        self.statusBar().showMessage(f"Reference saved to user library: {target}", 10000)

    def _load_reference_template(self, kind: SignalKind) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load filled reference template",
            "",
            "Reference templates (*.vsref *.json);;All files (*)",
        )
        if not path:
            return
        self._load_reference_template_path(Path(path), kind)

    def _load_reference_template_path(self, source_path: Path, kind: SignalKind) -> bool:
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(self, "Template import failed", str(exc))
            return False
        payload_kind = str(payload.get("kind") or "").strip().lower()
        if payload_kind in {"ir", "infrared"}:
            payload_kind = "ftir"
        if not payload_kind:
            payload["kind"] = kind.value
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("origin", "experimental")
        payload["metadata"] = metadata
        name = str(metadata.get("name") or source_path.stem or "user-reference")
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_.") or "user-reference"
        target = self._user_reference_root() / f"{slug}_{int(time.time())}.vsref"
        try:
            write_editable_reference(target, payload)
        except Exception as exc:
            QMessageBox.warning(self, "Template import failed", str(exc))
            return False
        self._replace_editable_reference_source()
        if "User Library" in getattr(self, "source_checks", {}):
            self.source_checks["User Library"].setChecked(True)
        if self.active_spectrum is not None:
            self._search_active_spectrum()
        self.statusBar().showMessage(f"Loaded reference template into user library: {target.name}", 8000)
        return True

    def _load_reference_spectrum_files(self, kind: SignalKind) -> None:
        title = "Load Raman reference spectra/templates" if kind == SignalKind.RAMAN else "Load FTIR reference spectra/templates"
        file_filter = (
            f"Reference spectra/templates ({SPECTRUM_GLOBS} *.vsref *.json);;"
            "Reference templates (*.vsref *.json);;"
            f"{SPECTRUM_FILE_FILTER}"
        )
        paths, _ = QFileDialog.getOpenFileNames(self, title, "", file_filter)
        if not paths:
            return
        loaded = 0
        loaded_templates = 0
        failures: list[str] = []
        for path in paths:
            source_path = Path(path)
            try:
                if source_path.suffix.lower() in {".json", ".vsref"}:
                    if self._load_reference_template_path(source_path, kind):
                        loaded_templates += 1
                    continue
                spectrum = load_xy_spectrum(source_path, kind=kind, name=source_path.stem, reference=True)
                bands = detect_bands(
                    spectrum,
                    BandDetectionOptions(backend="auto", fit_peaks=False),
                )
                payload = {
                    "format": "vibrational-reference",
                    "version": 1,
                    "kind": kind.value,
                    "source": "User References",
                    "metadata": {
                        "name": source_path.stem,
                        "origin": "experimental",
                        "quality": "measured reference",
                    },
                    "profile": {
                        "x": [float(value) for value in spectrum.x],
                        "y": [float(value) for value in spectrum.y],
                        "source_path": str(source_path),
                    },
                    "bands": [
                        {
                            "position_cm1": float(band.position),
                            "intensity": float(band.intensity),
                            "fwhm_cm1": float(band.width),
                            "confidence": "detected",
                            "comment": "Detected from imported reference spectrum",
                        }
                        for band in bands
                    ],
                }
                slug = re.sub(r"[^A-Za-z0-9._-]+", "_", source_path.stem).strip("_.") or "reference"
                target = self._user_reference_root() / f"{slug}_{int(time.time())}.vsref"
                write_editable_reference(target, payload)
                loaded += 1
            except Exception as exc:
                failures.append(f"{source_path.name}: {exc}")
        if loaded:
            self._replace_editable_reference_source()
            if "User Library" in getattr(self, "source_checks", {}):
                self.source_checks["User Library"].setChecked(True)
            if self.active_spectrum is not None:
                self._search_active_spectrum()
            self.statusBar().showMessage(f"Loaded {loaded} reference spectrum file(s).", 8000)
        elif loaded_templates:
            self.statusBar().showMessage(f"Loaded {loaded_templates} reference template file(s).", 8000)
        if failures:
            QMessageBox.warning(self, "Reference import", "Some reference spectra could not be imported:\n\n" + "\n".join(failures[:8]))

    def _load_experiment_path(self, path: str, kind: SignalKind) -> None:
        self._close_preprocessing_panel(restore=True)
        spectrum = load_xy_spectrum(path, kind=kind, name=Path(path).stem)
        if not isinstance(spectrum, ObservedSpectrum):
            spectrum = ObservedSpectrum(**spectrum.__dict__)
        self._save_active_spectrum_profile_state()
        self.active_spectrum = spectrum
        self.visible_observed_paths.add(self._spectrum_visibility_key(spectrum))
        self._original_observed[spectrum.source_path] = self._copy_observed_spectrum(spectrum) or spectrum
        if kind == SignalKind.RAMAN:
            self.raman_spectra.append(spectrum)
        else:
            self.ftir_spectra.append(spectrum)
        self._activate_spectrum_profile_state(spectrum)
        self._initialize_sample_card(spectrum)
        self._refresh_project_tree()
        self._refresh_sample_card()
        self._redraw_plot()

    def _close_preprocessing_panel(self, *, restore: bool = False) -> None:
        panel = self._preprocessing_panel
        cancel_callback = self._preprocessing_cancel_callback
        self._preprocessing_panel = None
        self._preprocessing_panel_key = None
        self._preprocessing_cancel_callback = None
        if restore and cancel_callback is not None:
            cancel_callback()
        if panel is not None:
            panel.hide()
            panel.deleteLater()

    def _begin_preprocessing_panel(self, key: str) -> bool:
        if self._preprocessing_panel is None:
            return True
        same_panel = self._preprocessing_panel_key == key
        self._close_preprocessing_panel(restore=True)
        return not same_panel

    def _show_preprocessing_panel(
        self,
        key: str,
        button: QWidget,
        panel: QWidget,
        preview_callback,
        cancel_callback,
    ) -> None:
        if self._preprocessing_panel is not None:
            same_panel = self._preprocessing_panel_key == key
            self._close_preprocessing_panel(restore=True)
            if same_panel:
                return

        panel.setParent(self)
        panel.setWindowFlags(Qt.WindowType.Widget)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setAutoFillBackground(True)
        panel.setStyleSheet(preprocessing_panel_style(self.current_theme == "Dark"))
        panel.adjustSize()
        position = button.mapTo(self, button.rect().bottomLeft())
        max_x = max(0, self.width() - panel.width() - 8)
        max_y = max(0, self.height() - panel.height() - 8)
        panel.move(min(max(position.x(), 8), max_x), min(max(position.y() + 4, 8), max_y))
        panel.raise_()

        def accept_panel() -> None:
            preview_callback()
            self._close_preprocessing_panel()

        def cancel_panel() -> None:
            self._close_preprocessing_panel(restore=True)

        panel.previewRequested.connect(preview_callback)
        panel.applyRequested.connect(accept_panel)
        panel.cancelRequested.connect(cancel_panel)
        self._preprocessing_panel = panel
        self._preprocessing_panel_key = key
        self._preprocessing_cancel_callback = cancel_callback
        panel.show()

    def _smooth_active_spectrum(self) -> None:
        if not self._begin_preprocessing_panel("smooth"):
            return
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        base = replace(self.active_spectrum, x=list(self.active_spectrum.x), y=list(self.active_spectrum.y))
        x = np.asarray(base.x, dtype=float)
        y = np.asarray(base.y, dtype=float)
        panel = SmoothPanel(auto_smoothing_window(x, y), self)

        def preview() -> None:
            smoothed_y = np.asarray(y, dtype=float)
            for _ in range(panel.passes()):
                smoothed_y = smooth_spectrum_curve(
                    smoothed_y,
                    method=panel.method(),
                    window=panel.window_size(),
                    polyorder=panel.polyorder(),
                    gaussian_sigma=panel.gaussian_sigma(),
                )
            self._replace_active_spectrum(replace(base, y=smoothed_y.tolist()))
            self.statusBar().showMessage(
                f"Smoothing preview: {panel.method()}, window {panel.window_size()}, {panel.passes()} pass(es).",
                5000,
            )

        def cancel() -> None:
            self._replace_active_spectrum(replace(base, x=list(base.x), y=list(base.y)))
            self.statusBar().showMessage("Smoothing preview cancelled.", 4000)

        self._show_preprocessing_panel("smooth", self.action_bar.smooth_button, panel, preview, cancel)

    def _despike_active_spectrum(self) -> None:
        if not self._begin_preprocessing_panel("despike"):
            return
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        base = replace(self.active_spectrum, x=list(self.active_spectrum.x), y=list(self.active_spectrum.y))
        y = np.asarray(base.y, dtype=float)
        panel = DespikePanel(self)

        def preview() -> None:
            corrected_y = np.asarray(y, dtype=float)
            for _ in range(panel.passes()):
                corrected_y = remove_narrow_spikes(
                    corrected_y,
                    threshold=panel.threshold(),
                    max_width=panel.max_width(),
                    median_window=panel.median_window(),
                )
            changed = int(np.count_nonzero(corrected_y != y))
            self._replace_active_spectrum(replace(base, y=corrected_y.tolist()))
            self.statusBar().showMessage(f"Despike preview: {changed} point(s) replaced.", 5000)

        def cancel() -> None:
            self._replace_active_spectrum(replace(base, x=list(base.x), y=list(base.y)))
            self.statusBar().showMessage("Despike preview cancelled.", 4000)

        self._show_preprocessing_panel("despike", self.action_bar.despike_button, panel, preview, cancel)

    def _remove_background_active_spectrum(self) -> None:
        if not self._begin_preprocessing_panel("background"):
            return
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        base = replace(self.active_spectrum, x=list(self.active_spectrum.x), y=list(self.active_spectrum.y))
        x = np.asarray(base.x, dtype=float)
        y = np.asarray(base.y, dtype=float)
        panel = BackgroundRemovalPanel(parent=self)

        def preview() -> None:
            method = panel.method()
            if method == "constant":
                background = np.full_like(y, float(np.nanpercentile(y, panel.floor_percentile())))
            else:
                background = estimate_background(
                    x,
                    y,
                    degree=panel.degree(),
                    method=method,
                    lam=panel.lambda_value(),
                    asymmetry=panel.asymmetry(),
                    half_window=panel.half_window(),
                )
            corrected_y = y - background
            self._replace_active_spectrum(replace(base, y=corrected_y.tolist()))
            self.statusBar().showMessage(
                f"Background preview: {background_method_label(method, panel.degree())}.",
                5000,
            )

        def cancel() -> None:
            self._replace_active_spectrum(replace(base, x=list(base.x), y=list(base.y)))
            self.statusBar().showMessage("Background preview cancelled.", 4000)

        self._show_preprocessing_panel(
            "background",
            self.action_bar.remove_background_button,
            panel,
            preview,
            cancel,
        )

    def _reset_active_spectrum_data(self) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        self._close_preprocessing_panel()
        original = self._original_observed.get(self.active_spectrum.source_path)
        if original is None:
            QMessageBox.information(self, "Reset data", "Original spectrum is not available for this item.")
            return
        self._replace_active_spectrum(self._copy_observed_spectrum(original) or original)
        self.statusBar().showMessage("Reset active spectrum to imported data.", 5000)

    def _replace_active_spectrum(self, spectrum: ObservedSpectrum) -> None:
        if self.active_spectrum is None:
            return
        old_key = self._spectrum_visibility_key(self.active_spectrum)
        self._replace_spectrum_in_store(spectrum, old_key=old_key)
        self.active_spectrum = spectrum
        self.sample_bands[self._sample_key(spectrum)] = detect_bands(
            spectrum,
            BandDetectionOptions(backend="auto", fit_peaks=False),
        )
        self.results = []
        self.browse_records = []
        self.selected_results = []
        self.visible_selected_candidate_keys.clear()
        self.candidate_table.set_results([])
        self._refresh_selected_table()
        self._save_active_spectrum_profile_state()
        self._set_card(None)
        self._current_preview_reference = None
        self._current_preview_result = None
        self._refresh_project_tree()
        self._refresh_sample_card()
        self._redraw_plot()

    def _load_user_library(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open user reference library", "", "CSV files (*.csv);;All files (*)")
        if not path:
            return
        self._load_user_library_path(path)
        if self.active_spectrum is not None:
            self._search_active_spectrum()

    def _load_user_library_path(self, path: str) -> None:
        source = UserLibrarySource(path)
        self._add_user_library_source(source)

    def _load_library_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder with Raman / FTIR reference spectra", "")
        if not path:
            return
        self._load_library_folder_path(path)
        if self.active_spectrum is not None:
            self._search_active_spectrum()

    def _load_library_folder_path(self, path: str) -> None:
        source = FolderLibrarySource(path)
        records = source.search(SourceQuery())
        if not records:
            QMessageBox.warning(self, "Empty library folder", "No supported Raman/FTIR spectrum files were found in this folder.")
            return
        self._add_user_library_source(source)
        self.statusBar().showMessage(f"Loaded {len(records)} reference spectra from folder: {path}", 7000)

    def _load_dft_library_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder with calculated DFT Raman / FTIR spectra", "")
        if not path:
            return
        self._load_dft_library_folder_path(path)
        if self.active_spectrum is not None:
            self._search_active_spectrum()

    def _load_dft_library_folder_path(self, path: str) -> None:
        source = FolderLibrarySource(path, library_type="dft", source_name=f"DFT {Path(path).name}")
        records = source.search(SourceQuery())
        if not records:
            QMessageBox.warning(self, "Empty DFT folder", "No supported calculated spectrum files were found in this folder.")
            return
        self._add_user_library_source(source)
        self.statusBar().showMessage(f"Loaded {len(records)} calculated spectra from folder: {path}", 7000)

    def _load_cif_library_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Open folder with CIF structures for IR band hints", "")
        if not path:
            return
        self._load_cif_library_folder_path(path)
        if self.active_spectrum is not None:
            self._search_active_spectrum()

    def _load_cif_library_folder_path(self, path: str) -> None:
        source = CifStructureSource(path)
        records = source.search(SourceQuery())
        if not records:
            QMessageBox.warning(self, "Empty CIF folder", "No CIF files were found in this folder.")
            return
        self._add_user_library_source(source)
        self.statusBar().showMessage(f"Loaded {len(records)} CIF IR hint records from folder: {path}", 7000)

    def _load_cif_library_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open CIF structure for IR hints", "", "CIF files (*.cif);;All files (*)")
        if not path:
            return
        source = CifStructureSource(path)
        records = source.search(SourceQuery())
        if not records:
            QMessageBox.warning(self, "CIF import failed", "No CIF structure record could be created from this file.")
            return
        self._add_user_library_source(source)
        if self.active_spectrum is not None:
            self._search_active_spectrum()
        self.statusBar().showMessage(f"Loaded CIF IR hint record: {Path(path).name}", 7000)

    def _add_user_library_source(
        self,
        source: UserLibrarySource | FolderLibrarySource | CifStructureSource | EditableReferenceSource,
    ) -> None:
        self.user_libraries.append(source)
        for record in source.search(SourceQuery()):
            if record.key in self.removed_user_reference_keys:
                continue
            reference = source.load_spectrum(record)
            self.reference_records.append(record)
            self.reference_spectra.append(reference)
        self._update_database_table()
        self._refresh_project_tree()

    def _manage_user_references(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("User reference library")
        dialog.resize(920, 520)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(["Source", "Entry", "Formula", "Compound", "Method", "Library", "Path"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for column, width in enumerate((120, 120, 120, 210, 80, 140, 260)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, width)
        layout.addWidget(table, 1)

        def populate() -> None:
            table.setRowCount(0)
            for record in self.reference_records:
                path = str(record.metadata.get("path", "") or "")
                library = Path(path).parent.name if path else record.source
                values = [
                    record.source,
                    record.entry_id,
                    record.formula,
                    record.name,
                    record.kind.value.upper(),
                    library,
                    path,
                ]
                row = table.rowCount()
                table.insertRow(row)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value or "-"))
                    item.setData(Qt.ItemDataRole.UserRole, record.key)
                    table.setItem(row, column, item)
            table.resizeRowsToContents()

        def selected_keys() -> set[str]:
            keys: set[str] = set()
            for index in table.selectedIndexes():
                item = table.item(index.row(), 0)
                if item is not None:
                    key = str(item.data(Qt.ItemDataRole.UserRole) or "")
                    if key:
                        keys.add(key)
            return keys

        buttons = QHBoxLayout()
        remove_button = QPushButton("Remove selected")
        remove_button.setStyleSheet(_glass_button_style("#8a5a16", "#c68a2e"))
        close_button = QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        buttons.addStretch(1)
        buttons.addWidget(remove_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        def remove_selected() -> None:
            keys = selected_keys()
            if not keys:
                QMessageBox.information(dialog, "User references", "Select one or more references first.")
                return
            response = QMessageBox.question(
                dialog,
                "Remove references",
                "Remove selected references from the user library list?\n\n"
                "References saved by this program as .vsref files will be deleted from the user reference cache. "
                "References loaded from external folders are removed only from this session.",
            )
            if response != QMessageBox.StandardButton.Yes:
                return
            removed, deleted = self._remove_user_reference_keys(keys)
            populate()
            self.statusBar().showMessage(
                f"Removed {removed} reference(s)" + (f", deleted {deleted} .vsref file(s)." if deleted else "."),
                7000,
            )
            if table.rowCount() == 0:
                dialog.accept()

        remove_button.clicked.connect(remove_selected)
        populate()
        if table.rowCount() == 0:
            QMessageBox.information(self, "User references", "No user reference records are loaded.")
            return
        dialog.exec()

    def _remove_user_reference_keys(self, keys: set[str]) -> tuple[int, int]:
        if not keys:
            return 0, 0
        records_by_key = {record.key: record for record in self.reference_records}
        deleted_files = 0
        self._user_reference_cache().delete_keys(keys)
        user_root = self._user_reference_root().resolve()
        for key in keys:
            record = records_by_key.get(key)
            if record is None:
                continue
            raw_path = str(record.metadata.get("path", "") or "")
            path = Path(raw_path)
            if record.source == EditableReferenceSource.name and path.suffix.lower() == ".vsref":
                try:
                    resolved = path.expanduser().resolve()
                    if user_root in resolved.parents or resolved.parent == user_root:
                        resolved.unlink(missing_ok=True)
                        deleted_files += 1
                except OSError:
                    pass
            self.removed_user_reference_keys.add(key)

        self.reference_records = [record for record in self.reference_records if record.key not in keys]
        self.reference_spectra = [
            spectrum
            for spectrum in self.reference_spectra
            if spectrum.record is None or spectrum.record.key not in keys
        ]
        self.results = [result for result in self.results if result.candidate.key not in keys]
        self.browse_records = [record for record in self.browse_records if record.key not in keys]
        self.selected_results = [result for result in self.selected_results if result.candidate.key not in keys]
        self.visible_selected_candidate_keys.difference_update(keys)
        for state in self.spectrum_profile_states.values():
            state.results = [result for result in state.results if result.candidate.key not in keys]
            state.browse_records = [record for record in state.browse_records if record.key not in keys]
            state.selected_results = [result for result in state.selected_results if result.candidate.key not in keys]
            state.visible_selected_candidate_keys.difference_update(keys)
        for key in keys:
            self.selected_candidate_colors.pop(key, None)
        self.candidate_table.set_results(self.results if self.results else self.browse_records)
        self._refresh_selected_table()
        self._update_database_table()
        self._refresh_project_tree()
        self._redraw_plot()
        return len(keys), deleted_files

    def _auto_match_active_spectrum(self, _checked: bool = False) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        self._search_active_spectrum(auto_match=True)

    def _search_active_spectrum(self, _checked: bool = False, *, auto_match: bool = False) -> None:
        if self.active_spectrum is None:
            self._browse_reference_sources()
            return
        use_user_library = (
            True
            if auto_match
            else self.source_checks.get("User Library").isChecked()
            if hasattr(self, "source_checks") and "User Library" in self.source_checks
            else True
        )
        use_rruff = (
            True
            if auto_match
            else self.source_checks.get("RRUFF").isChecked()
            if hasattr(self, "source_checks") and "RRUFF" in self.source_checks
            else False
        )
        use_rod = (
            True
            if auto_match
            else self.source_checks.get("ROD").isChecked()
            if hasattr(self, "source_checks") and "ROD" in self.source_checks
            else False
        )
        use_openspecy = (
            True
            if auto_match
            else self.source_checks.get("OpenSpecy").isChecked()
            if hasattr(self, "source_checks") and "OpenSpecy" in self.source_checks
            else False
        )
        use_jarvis = (
            True
            if auto_match
            else self.source_checks.get("JARVIS-DFT").isChecked()
            if hasattr(self, "source_checks") and "JARVIS-DFT" in self.source_checks
            else False
        )
        if (
            not self.user_libraries
            and not (use_rruff and self.rruff_source.search(SourceQuery(kind=self.active_spectrum.kind)))
            and not (use_rod and self.rod_source.search(SourceQuery(kind=self.active_spectrum.kind)))
            and not (use_openspecy and self.openspecy_source.search(SourceQuery(kind=self.active_spectrum.kind)))
            and not (use_jarvis and self.jarvis_source.search(SourceQuery(kind=self.active_spectrum.kind), limit=1))
        ):
            QMessageBox.warning(self, "No reference source", "Load a user library or update RRUFF, ROD, OpenSpecy, or JARVIS-DFT first.")
            return
        text = "" if auto_match else self._reference_search_text()
        formula = "" if auto_match else self._element_formula_query()
        observed = self.active_spectrum
        query = SourceQuery(text=text, kind=observed.kind, formula=formula)
        matching_options = self._matching_options()
        user_libraries = list(self.user_libraries)
        required_elements = set(self.required_elements)
        excluded_elements = set(self._excluded_elements())
        selected_laser = 0.0 if auto_match else self._selected_laser_wavelength_nm()

        def passes_gate(record: CandidateRecord) -> bool:
            if auto_match:
                return True
            if not self._record_passes_origin_gate(record):
                return False
            if selected_laser > 0.0 and record.kind == SignalKind.RAMAN:
                laser_match = re.search(r"(\d+(?:[.,]\d+)?)", str(record.metadata.get("laser_nm", "") or ""))
                if laser_match is None or abs(float(laser_match.group(1).replace(",", ".")) - selected_laser) > 2.0:
                    return False
            elements = parse_formula_elements(record.formula)
            if excluded_elements and not elements:
                return False
            if required_elements and not required_elements.issubset(elements):
                return False
            return not bool(excluded_elements & elements)

        def task() -> list[VibrationalMatchResult]:
            prefilter_bands = detect_bands(
                observed,
                BandDetectionOptions(min_prominence=0.04, max_bands=60, backend="auto", fit_peaks=False),
            )
            observed_processed = preprocess_spectrum(observed, matching_options.preprocessing)
            observed_bands = detect_bands(observed_processed, matching_options.band_detection)
            candidates: list[CompoundCandidate] = []
            if use_user_library:
                for source in user_libraries:
                    if isinstance(source, EditableReferenceSource):
                        candidates.extend(source.load_candidates(query, observed=observed, observed_bands=prefilter_bands, limit=80))
                    else:
                        candidates.extend(source.load_candidates(query))
            if use_rruff:
                candidates.extend(self.rruff_source.load_candidates(query, observed=observed, observed_bands=prefilter_bands, limit=80))
            if use_rod:
                candidates.extend(self.rod_source.load_candidates(query, observed=observed, observed_bands=prefilter_bands, limit=80))
            if use_openspecy:
                candidates.extend(
                    candidate
                    for candidate in self.openspecy_source.load_candidates(
                        query,
                        observed=observed,
                        observed_bands=prefilter_bands,
                        limit=80,
                    )
                    if candidate.reference is not None
                )
            if use_jarvis:
                candidates.extend(self.jarvis_source.load_candidates(query, observed=observed, observed_bands=prefilter_bands))
            return rank_candidates(
                observed,
                [candidate for candidate in candidates if passes_gate(candidate)],
                matching_options,
                observed_processed=observed_processed,
                observed_bands=observed_bands,
            )

        def success(results: list[VibrationalMatchResult]) -> None:
            self.results = results
            self.browse_records = []
            self.candidate_table.set_results(self.results)
            self._update_database_table()
            self._update_profile_view_context()
            self._preview_result(self.results[0] if self.results else None)
            self._save_active_spectrum_profile_state()
            if self.results:
                prefix = "Auto match" if auto_match else "Found"
                self.statusBar().showMessage(f"{prefix}: {len(self.results)} candidates. Top match: {self.results[0].candidate.name}", 7000)
            else:
                self.statusBar().showMessage(
                    "No candidates matched. Load/update reference databases or add user references.",
                    9000,
                )

        self._run_background_task(
            "Auto match" if auto_match else "Search references",
            "Searching all available databases..." if auto_match else "Loading reference spectra and ranking candidates...",
            task,
            success,
            lambda message, _details: QMessageBox.warning(self, "Reference search failed", message),
        )

    def _reference_search_text(self) -> str:
        if not hasattr(self, "reference_search_input"):
            return ""
        return self.reference_search_input.text().strip()

    def _browse_reference_sources(self) -> None:
        text = self._reference_search_text()
        formula = self._element_formula_query()
        kinds = self._selected_reference_kinds()
        if not kinds:
            QMessageBox.warning(self, "No reference method", "Enable Raman references, FTIR references, or both.")
            return
        records: list[CandidateRecord] = []
        for kind in kinds:
            query = SourceQuery(text=text, kind=kind, formula=formula)
            records.extend(self._search_reference_records(query))
        self.results = []
        self.browse_records = self._dedupe_records([record for record in records if self._record_passes_element_gate(record)])
        self.candidate_table.set_records(self.browse_records)
        self._set_card(None)
        self._save_active_spectrum_profile_state()
        if self.browse_records:
            self._preview_browse_record(0)
            self.statusBar().showMessage(f"Found {len(self.browse_records)} reference records. Import an experiment to calculate match scores.", 8000)
        else:
            self._redraw_plot()
            self.statusBar().showMessage("No reference records found. Update RRUFF/ROD, load a library, or relax filters.", 9000)

    def _selected_reference_kinds(self) -> list[SignalKind]:
        include_raman = getattr(self, "include_raman_checkbox", None) is None or self.include_raman_checkbox.isChecked()
        include_ftir = getattr(self, "include_ftir_checkbox", None) is None or self.include_ftir_checkbox.isChecked()
        if include_raman and include_ftir:
            return [SignalKind.UNKNOWN]
        kinds = []
        if include_raman:
            kinds.append(SignalKind.RAMAN)
        if include_ftir:
            kinds.append(SignalKind.FTIR)
        return kinds

    def _search_reference_records(self, query: SourceQuery) -> list[CandidateRecord]:
        use_user_library = self.source_checks.get("User Library").isChecked() if hasattr(self, "source_checks") and "User Library" in self.source_checks else True
        use_rruff = self.source_checks.get("RRUFF").isChecked() if hasattr(self, "source_checks") and "RRUFF" in self.source_checks else False
        use_rod = self.source_checks.get("ROD").isChecked() if hasattr(self, "source_checks") and "ROD" in self.source_checks else False
        use_openspecy = self.source_checks.get("OpenSpecy").isChecked() if hasattr(self, "source_checks") and "OpenSpecy" in self.source_checks else False
        use_jarvis = self.source_checks.get("JARVIS-DFT").isChecked() if hasattr(self, "source_checks") and "JARVIS-DFT" in self.source_checks else False
        records: list[CandidateRecord] = []
        if use_user_library:
            for source in self.user_libraries:
                records.extend(
                    record
                    for record in source.search(query)
                    if record.key not in self.removed_user_reference_keys
                )
        if use_rruff:
            records.extend(self.rruff_source.search(query))
        if use_rod:
            records.extend(self.rod_source.search(query))
        if use_openspecy:
            records.extend(self.openspecy_source.search(query))
        if use_jarvis:
            records.extend(self.jarvis_source.search(query))
        return records

    def _dedupe_records(self, records: list[CandidateRecord]) -> list[CandidateRecord]:
        deduped: list[CandidateRecord] = []
        seen: set[str] = set()
        for record in records:
            if record.key in seen:
                continue
            seen.add(record.key)
            deduped.append(record)
        return deduped

    def _element_formula_query(self) -> str:
        return " ".join(self.selected_element_order)

    def _toggle_required_element(self, element: str) -> None:
        self.exclude_all_other_elements = True
        current = self.element_states.get(element, "excluded")
        self._set_element_state(element, "excluded" if current == "required" else "required")
        if not any(state == "required" for state in self.element_states.values()):
            for symbol in self._element_symbols():
                if self.element_states.get(symbol) != "optional":
                    self._set_element_state(symbol, "excluded")
        self._update_element_fields()

    def _toggle_optional_element(self, element: str) -> None:
        self.exclude_all_other_elements = True
        current = self.element_states.get(element, "excluded")
        self._set_element_state(element, "excluded" if current == "optional" else "optional")
        if not any(state == "required" for state in self.element_states.values()):
            for symbol in self._element_symbols():
                if symbol != element and self.element_states.get(symbol) != "optional":
                    self._set_element_state(symbol, "excluded")
        self._update_element_fields()

    def _reset_element_filters(self) -> None:
        self.element_states.clear()
        self.selected_element_order.clear()
        self.exclude_all_other_elements = True
        for element in self._element_symbols():
            self._set_element_state(element, "excluded")
        self._update_element_fields()

    def _refresh_element_table(self) -> None:
        if not hasattr(self, "element_table"):
            return
        for element in self.element_table.element_symbols:
            self.element_table.set_element_state(element, self.element_states.get(element, "excluded"))
        self._update_element_fields()

    def _update_element_fields(self) -> None:
        self.required_elements = {
            element for element, state in self.element_states.items() if state == "required"
        }
        self.optional_elements = {
            element for element, state in self.element_states.items() if state == "optional"
        }
        self.excluded_elements = {
            element for element, state in self.element_states.items() if state == "excluded"
        }
        self.selected_element_order = [
            element for element in self.selected_element_order if element in self.required_elements
        ]
        for element in sorted(self.required_elements, key=element_sort_key):
            if element not in self.selected_element_order:
                self.selected_element_order.append(element)
        for element in self._element_symbols():
            self.element_table.set_element_state(element, self.element_states.get(element, "excluded"))
        required = ", ".join(sorted(self.required_elements, key=element_sort_key)) or "none"
        optional = ", ".join(sorted(self.optional_elements, key=element_sort_key)) or "none"
        if self.exclude_all_other_elements:
            excluded = "all others" if self.required_elements or self.optional_elements else "all elements"
        else:
            excluded = ", ".join(sorted(self._excluded_elements(), key=element_sort_key)) or "none"
        if hasattr(self, "element_gate_label"):
            self.element_gate_label.setText(f"Required: {required}    Optional: {optional}    Excluded: {excluded}")

    def _set_element_state(self, element: str, state: str) -> None:
        if not hasattr(self, "element_table"):
            return
        if state == "neutral":
            self.element_states.pop(element, None)
            if element in self.selected_element_order:
                self.selected_element_order.remove(element)
        else:
            self.element_states[element] = state
            if state == "required" and element not in self.selected_element_order:
                self.selected_element_order.append(element)
            elif state != "required" and element in self.selected_element_order:
                self.selected_element_order.remove(element)
        self.element_table.set_element_state(element, state)

    def _excluded_elements(self) -> list[str]:
        if self.exclude_all_other_elements:
            allowed_elements = self.required_elements | self.optional_elements
            return [
                element
                for element in self._element_symbols()
                if element not in allowed_elements
                and self.element_states.get(element, "excluded") not in {"optional", "any"}
            ]
        return [element for element, state in self.element_states.items() if state == "excluded"]

    def _element_symbols(self) -> list[str]:
        return self.element_table.element_symbols if hasattr(self, "element_table") else []

    def _record_passes_element_gate(self, record: CandidateRecord) -> bool:
        if not self._record_passes_laser_gate(record):
            return False
        if not self._record_passes_origin_gate(record):
            return False
        excluded = set(self._excluded_elements())
        if not self.required_elements and not self.optional_elements and not excluded:
            return True
        elements = parse_formula_elements(record.formula)
        if excluded and not elements:
            return False
        if self.required_elements and not self.required_elements.issubset(elements):
            return False
        if excluded and elements & excluded:
            return False
        return True

    def _reference_origin(self, record: CandidateRecord) -> str:
        metadata = record.metadata
        explicit = str(metadata.get("origin", "") or "").strip().lower()
        if explicit in {"experimental", "calculated"}:
            return explicit
        determination = str(metadata.get("determination_method", "") or "").strip().lower()
        quality = str(metadata.get("quality", "") or "").strip().lower()
        calculated_tokens = ("dft", "dfpt", "theoretical", "calculated", "computed")
        if record.source == self.jarvis_source.name or any(token in determination or token in quality for token in calculated_tokens):
            return "calculated"
        return "experimental"

    def _record_passes_origin_gate(self, record: CandidateRecord) -> bool:
        selected = str(self.reference_origin_combo.currentData() or "both")
        return selected == "both" or self._reference_origin(record) == selected

    def _selected_laser_wavelength_nm(self) -> float:
        if not hasattr(self, "action_bar"):
            return 0.0
        return float(self.action_bar.laser_wavelength_spin.value())

    @staticmethod
    def _parse_laser_wavelength_nm(raw_value) -> float | None:
        match = re.search(r"(\d+(?:[.,]\d+)?)", str(raw_value or ""))
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    @staticmethod
    def _format_nm(value: float) -> str:
        return f"{value:g} nm"

    @staticmethod
    def _format_excitation_nm(value: float) -> str:
        return f"ex {value:g} nm"

    def _legend_laser_suffix(self, kind: SignalKind, metadata: dict) -> str:
        if kind != SignalKind.RAMAN:
            return ""
        selected_laser = self._selected_laser_wavelength_nm()
        if selected_laser <= 0.0:
            return ""
        record_laser = self._parse_laser_wavelength_nm(metadata.get("laser_nm", ""))
        if record_laser is None:
            return " [laser unknown]"
        if abs(record_laser - selected_laser) <= 2.0:
            return ""
        return f" [{self._format_excitation_nm(record_laser)}]"

    def _legend_candidate_name(self, candidate: CompoundCandidate) -> str:
        base = candidate.name or candidate.entry_id or "Reference"
        return f"{base}{self._legend_laser_suffix(candidate.kind, candidate.metadata)}"

    def _legend_reference_name(self, reference: ReferenceSpectrum) -> str:
        metadata = dict(reference.record.metadata) if reference.record is not None else {}
        base = reference.name or (reference.record.name if reference.record is not None else "Reference")
        return f"{base}{self._legend_laser_suffix(reference.kind, metadata)}"

    def _record_laser_wavelength_nm(self, record: CandidateRecord) -> float | None:
        return self._parse_laser_wavelength_nm(record.metadata.get("laser_nm", ""))

    def _record_passes_laser_gate(self, record: CandidateRecord) -> bool:
        selected_laser = self._selected_laser_wavelength_nm()
        if selected_laser <= 0.0 or record.kind != SignalKind.RAMAN:
            return True
        record_laser = self._record_laser_wavelength_nm(record)
        if record_laser is None:
            return False
        return abs(record_laser - selected_laser) <= 2.0

    def _refresh_project_tree(self) -> None:
        self._updating_project_tree = True
        self.project_tree.clear()
        root = QTreeWidgetItem(["IR/Raman Phase Finder Project"])
        self.project_tree.addTopLevelItem(root)

        raman_root = QTreeWidgetItem(["Raman spectra"])
        ftir_root = QTreeWidgetItem(["FTIR spectra"])
        root.addChild(raman_root)
        root.addChild(ftir_root)

        active_item: QTreeWidgetItem | None = None
        for index, spectrum in enumerate(self.raman_spectra):
            item = QTreeWidgetItem([f"{index + 1:02d}  {spectrum.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("raman", index))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if self._spectrum_visibility_key(spectrum) in self.visible_observed_paths
                else Qt.CheckState.Unchecked,
            )
            raman_root.addChild(item)
            if (
                self.active_spectrum is not None
                and self._spectrum_visibility_key(spectrum) == self._spectrum_visibility_key(self.active_spectrum)
            ):
                active_item = item
        for index, spectrum in enumerate(self.ftir_spectra):
            item = QTreeWidgetItem([f"{index + 1:02d}  {spectrum.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("ftir", index))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                0,
                Qt.CheckState.Checked
                if self._spectrum_visibility_key(spectrum) in self.visible_observed_paths
                else Qt.CheckState.Unchecked,
            )
            ftir_root.addChild(item)
            if (
                self.active_spectrum is not None
                and self._spectrum_visibility_key(spectrum) == self._spectrum_visibility_key(self.active_spectrum)
            ):
                active_item = item

        root.setExpanded(True)
        raman_root.setExpanded(True)
        ftir_root.setExpanded(True)
        if active_item is not None:
            self.project_tree.setCurrentItem(active_item)
        self._updating_project_tree = False

    def _spectrum_visibility_key(self, spectrum: ObservedSpectrum) -> str:
        identity = spectrum.source_path or spectrum.name
        return f"{spectrum.kind.value}:{identity}"

    def _current_spectrum_profile_key(self) -> str | None:
        if self.active_spectrum is None:
            return None
        return self._spectrum_visibility_key(self.active_spectrum)

    @staticmethod
    def _copy_observed_spectrum(spectrum: ObservedSpectrum | None) -> ObservedSpectrum | None:
        if spectrum is None:
            return None
        return replace(spectrum, x=list(spectrum.x), y=list(spectrum.y))

    def _replace_spectrum_in_store(self, spectrum: ObservedSpectrum, *, old_key: str | None = None) -> None:
        key = old_key or self._spectrum_visibility_key(spectrum)
        target_list = self.raman_spectra if spectrum.kind == SignalKind.RAMAN else self.ftir_spectra
        for index, item in enumerate(target_list):
            if self._spectrum_visibility_key(item) == key or item.source_path == spectrum.source_path:
                target_list[index] = spectrum
                return

    def _save_active_spectrum_profile_state(self) -> None:
        if getattr(self, "_profile_state_loading", False):
            return
        key = self.active_profile_spectrum_key or self._current_spectrum_profile_key()
        if not key:
            return
        self.spectrum_profile_states[key] = SpectrumProfileState(
            spectrum=self._copy_observed_spectrum(self.active_spectrum),
            results=list(self.results),
            browse_records=list(self.browse_records),
            selected_results=list(self.selected_results),
            visible_selected_candidate_keys=set(self.visible_selected_candidate_keys),
        )

    def _load_spectrum_profile_state(self, key: str | None) -> None:
        self._profile_state_loading = True
        try:
            state = self.spectrum_profile_states.get(key or "", SpectrumProfileState())
            stored_spectrum = self._copy_observed_spectrum(state.spectrum)
            if stored_spectrum is not None and key:
                self._replace_spectrum_in_store(stored_spectrum, old_key=key)
                if (
                    self.active_spectrum is not None
                    and self._spectrum_visibility_key(self.active_spectrum) == key
                ):
                    self.active_spectrum = stored_spectrum
            self.results = list(state.results)
            self.browse_records = list(state.browse_records)
            self.selected_results = list(state.selected_results)
            self.visible_selected_candidate_keys = set(state.visible_selected_candidate_keys)
            if self.results:
                self.candidate_table.set_results(self.results)
            elif self.browse_records:
                self.candidate_table.set_records(self.browse_records)
            else:
                self.candidate_table.set_results([])
            self._refresh_selected_table()
        finally:
            self._profile_state_loading = False

    def _activate_spectrum_profile_state(self, spectrum: ObservedSpectrum | None) -> None:
        key = self._spectrum_visibility_key(spectrum) if spectrum is not None else None
        previous_key = self.active_profile_spectrum_key
        if previous_key == key:
            return
        if previous_key:
            self._save_active_spectrum_profile_state()
        self.active_profile_spectrum_key = key
        self._load_spectrum_profile_state(key)

    def _selected_results_for_spectrum(
        self,
        spectrum: ObservedSpectrum | None,
    ) -> tuple[list[VibrationalMatchResult], set[str]]:
        if spectrum is None:
            return [], set()
        key = self._spectrum_visibility_key(spectrum)
        if key == self.active_profile_spectrum_key:
            return list(self.selected_results), set(self.visible_selected_candidate_keys)
        state = self.spectrum_profile_states.get(key)
        if state is None:
            return [], set()
        return list(state.selected_results), set(state.visible_selected_candidate_keys)

    def _on_project_tree_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating_project_tree:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, index = data
        spectrum: ObservedSpectrum | None = None
        if kind == "raman" and 0 <= index < len(self.raman_spectra):
            spectrum = self.raman_spectra[index]
        elif kind == "ftir" and 0 <= index < len(self.ftir_spectra):
            spectrum = self.ftir_spectra[index]
        if spectrum is None:
            return
        key = self._spectrum_visibility_key(spectrum)
        if item.checkState(0) == Qt.CheckState.Checked:
            self.visible_observed_paths.add(key)
        else:
            self.visible_observed_paths.discard(key)
        if self.action_bar.display_mode.currentText() == "All selected":
            view_range = self._plot_view_range()
            self._redraw_plot()
            self._restore_plot_view_range(view_range)

    def _on_display_mode_changed(self, _mode: str) -> None:
        multi_enabled = self.action_bar.display_mode.currentText() == "All selected"
        self.action_bar.multi_offset_slider.setEnabled(multi_enabled)
        self.action_bar.multi_offset_value.setEnabled(multi_enabled)
        self._redraw_plot()
        self._reset_plot_view()

    def _on_multi_offset_changed(self, value: int) -> None:
        self.action_bar.multi_offset_value.setText(f"{value}%")
        if self.action_bar.display_mode.currentText() == "All selected":
            self._redraw_plot()
            self._reset_plot_view()

    def _observed_spectra_to_display(self) -> list[ObservedSpectrum]:
        if self.action_bar.display_mode.currentText() != "All selected":
            return [self.active_spectrum] if self.active_spectrum is not None else []
        spectra = [
            spectrum
            for spectrum in [*self.raman_spectra, *self.ftir_spectra]
            if self._spectrum_visibility_key(spectrum) in self.visible_observed_paths
        ]
        if spectra:
            return spectra
        return [self.active_spectrum] if self.active_spectrum is not None else []

    def _reference_label(self, record: CandidateRecord) -> str:
        name = record.name or record.entry_id
        formula = f" ({record.formula})" if record.formula else ""
        return f"{name}{formula}"

    def _on_project_tree_selection_changed(self) -> None:
        if self._updating_project_tree:
            return
        item = self.project_tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        self._close_preprocessing_panel(restore=True)
        view_range = (
            self._plot_view_range()
            if self.action_bar.display_mode.currentText() == "All selected"
            else None
        )
        kind, index = data
        try:
            if kind == "raman" and 0 <= index < len(self.raman_spectra):
                self._save_sample_card_fields()
                self._save_active_spectrum_profile_state()
                self.active_spectrum = self.raman_spectra[index]
                self._current_preview_result = None
                self._current_preview_reference = None
                self._activate_spectrum_profile_state(self.active_spectrum)
                self._set_card(None)
                self._refresh_sample_card()
                self._redraw_plot()
            elif kind == "ftir" and 0 <= index < len(self.ftir_spectra):
                self._save_sample_card_fields()
                self._save_active_spectrum_profile_state()
                self.active_spectrum = self.ftir_spectra[index]
                self._current_preview_result = None
                self._current_preview_reference = None
                self._activate_spectrum_profile_state(self.active_spectrum)
                self._set_card(None)
                self._refresh_sample_card()
                self._redraw_plot()
        finally:
            self._restore_plot_view_range(view_range)

    def _redraw_plot(self) -> None:
        self._apply_x_axis_label()
        self.match_plot.clear()
        self._ensure_cursor_position_items()
        if self.legend_item is not None:
            self.legend_item = None
            self._set_legend_visible(bool(getattr(self.plot_view_settings, "legend_visible", True)))
        observed_spectra = self._observed_spectra_to_display()
        offset_step = self._multi_offset_step(observed_spectra)
        self._active_display_offset = 0.0
        self.observed_spectrum_plot_context = {}
        self._reference_label_boxes = []
        active_key = self._current_spectrum_profile_key()
        if getattr(self.plot_view_settings, "layer_observed_visible", True):
            for index, spectrum in enumerate(observed_spectra):
                x, y = self._display_trace_xy(spectrum)
                y_offset = float(index) * offset_step
                key = self._spectrum_visibility_key(spectrum)
                finite_y = np.asarray(y, dtype=float)
                finite_y = finite_y[np.isfinite(finite_y)]
                raw_min = float(np.nanmin(finite_y)) if finite_y.size else 0.0
                raw_max = float(np.nanmax(finite_y)) if finite_y.size else 1.0
                height = max(raw_max - raw_min, 1.0e-9)
                self.observed_spectrum_plot_context[key] = {
                    "offset": float(y_offset),
                    "raw_min": raw_min,
                    "raw_max": raw_max,
                    "plot_min": raw_min + float(y_offset),
                    "plot_max": raw_max + float(y_offset),
                    "height": height,
                }
                if key == active_key:
                    self._active_display_offset = y_offset
                color = (
                    self._plot_observed_color()
                    if key == active_key
                    else OBSERVED_OVERLAY_COLORS[(index + 1) % len(OBSERVED_OVERLAY_COLORS)]
                )
                self.match_plot.plot(
                    x,
                    self._shift_y(y, y_offset),
                    pen=pg.mkPen(
                        color,
                        width=float(getattr(self.plot_view_settings, "observed_width", 1.35)),
                    ),
                    name=spectrum.name,
                )
        self._reference_line_lane_count = 0
        self._draw_selected_references()
        self._draw_observed_band_markers()

    def _draw_selected_references(self) -> None:
        width = float(getattr(self.plot_view_settings, "calculated_width", 1.7))
        observed_spectra = self._observed_spectra_to_display()
        if self.action_bar.display_mode.currentText() == "All selected":
            offset_step = self._multi_offset_step(observed_spectra)
            contexts = [(spectrum, float(index) * offset_step) for index, spectrum in enumerate(observed_spectra)]
        else:
            contexts = [(self.active_spectrum, self._active_display_offset)] if self.active_spectrum is not None else []
        for spectrum, y_offset in contexts:
            selected_results, visible_keys = self._selected_results_for_spectrum(spectrum)
            for result in selected_results:
                key = result.candidate.key
                if key not in visible_keys:
                    continue
                color = self._selected_candidate_color(key)
                reference = result.aligned_reference or result.candidate.reference
                legend_name = self._legend_candidate_name(result.candidate)
                if self._reference_view_shows_profiles() and getattr(self.plot_view_settings, "layer_phase_profiles_visible", True):
                    if reference is not None:
                        x, y = self._display_trace_xy(reference)
                        self.match_plot.plot(
                            x,
                            self._shift_y(y, y_offset),
                            pen=pg.mkPen(color, width=width),
                            name=legend_name,
                        )
                if self._reference_view_shows_lines() and getattr(self.plot_view_settings, "layer_phase_ticks_visible", True):
                    bands = self._reference_bands_for_result(result)
                    self._draw_reference_peak_sticks(
                        bands,
                        color=color,
                        name=legend_name,
                        shift=float(result.score.x_shift),
                        kind=result.candidate.kind,
                        observed_spectrum=spectrum,
                        y_offset=y_offset,
                    )
                    self._draw_band_sticks(
                        bands,
                        color=color,
                        name=legend_name,
                        shift=float(result.score.x_shift),
                        kind=result.candidate.kind,
                    )

    def _reference_view_mode(self) -> str:
        if self.plot_settings_panel is not None:
            return str(self.plot_settings_panel.reference_view_combo.currentData() or "profiles")
        return "profiles"

    def _reference_view_shows_profiles(self) -> bool:
        return self._reference_view_mode() in {"profiles", "both"}

    def _reference_view_shows_lines(self) -> bool:
        return self._reference_view_mode() in {"lines", "both"}

    def _on_reference_view_changed(self) -> None:
        self._redraw_plot()
        self._reset_plot_view()

    def _reference_bands_for_result(self, result: VibrationalMatchResult) -> list:
        if result.reference_bands:
            return result.reference_bands
        band_set = result.candidate.band_set
        if band_set is None and result.candidate.reference is not None:
            band_set = result.candidate.reference.band_set
        if band_set is None and result.candidate.reference is not None:
            band_set = extract_reference_band_set(
                result.candidate.reference,
                BandDetectionOptions(backend="auto", fit_peaks=False),
                origin=self._reference_origin(result.candidate),
            )
            result.candidate.band_set = band_set
            result.candidate.reference.band_set = band_set
        return list(band_set.bands) if band_set is not None else []

    def _visible_observed_y_extent(self) -> tuple[float, float]:
        spectra = self._observed_spectra_to_display()
        offset_step = self._multi_offset_step(spectra)
        values: list[float] = []
        for index, spectrum in enumerate(spectra):
            _x, y = self._display_trace_xy(spectrum)
            array = np.asarray(y, dtype=float) + float(index) * offset_step
            values.extend(array[np.isfinite(array)].tolist())
        if not values:
            return 0.0, 1.0
        y_min, y_max = float(min(values)), float(max(values))
        if y_max <= y_min:
            y_max = y_min + 1.0
        return y_min, y_max

    def _visible_observed_x_extent(self) -> tuple[float, float]:
        spectra = self._observed_spectra_to_display()
        values: list[float] = []
        for spectrum in spectra:
            x, _y = self._display_trace_xy(spectrum)
            array = np.asarray(x, dtype=float)
            values.extend(array[np.isfinite(array)].tolist())
        if not values:
            return 0.0, 1.0
        x_min, x_max = float(min(values)), float(max(values))
        if x_max <= x_min:
            x_max = x_min + 1.0
        return x_min, x_max

    @staticmethod
    def _boxes_overlap(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> bool:
        return not (
            first[2] <= second[0]
            or second[2] <= first[0]
            or first[3] <= second[1]
            or second[3] <= first[1]
        )

    def _place_reference_label(
        self,
        position: float,
        top: float,
        text: str,
        *,
        place_below: bool,
        x_span: float,
        y_min: float,
        y_max: float,
    ) -> tuple[float, float, tuple[float, float, float, float]]:
        y_span = max(y_max - y_min, 1.0e-9)
        width = max(x_span * (0.018 + 0.006 * len(text)), x_span * 0.028)
        height = y_span * 0.038
        base_offset = y_span * 0.028
        row_step = y_span * 0.052
        directions = [-1] if place_below else [1]
        directions.extend([1, -1] if place_below else [-1, 1])
        for direction in directions:
            for row in range(8):
                label_y = top + direction * (base_offset + row * row_step)
                box = (
                    position - width * 0.5,
                    label_y - height * 0.5,
                    position + width * 0.5,
                    label_y + height * 0.5,
                )
                if any(self._boxes_overlap(box, occupied) for occupied in self._reference_label_boxes):
                    continue
                self._reference_label_boxes.append(box)
                return position, label_y, box
        fallback_y = top + (-1 if place_below else 1) * (base_offset + 8 * row_step)
        box = (
            position - width * 0.5,
            fallback_y - height * 0.5,
            position + width * 0.5,
            fallback_y + height * 0.5,
        )
        self._reference_label_boxes.append(box)
        return position, fallback_y, box

    def _draw_band_sticks(
        self,
        bands: list,
        *,
        color: str,
        name: str,
        shift: float = 0.0,
        kind: SignalKind = SignalKind.UNKNOWN,
    ) -> None:
        if not bands:
            return
        y_min, y_max = self._visible_observed_y_extent()
        span = max(y_max - y_min, 1.0e-9)
        lane = self._reference_line_lane_count
        self._reference_line_lane_count += 1
        base = y_min - span * (0.075 + 0.065 * lane)
        stick_height = span * 0.05
        x_values: list[float] = []
        y_values: list[float] = []
        for band in bands:
            position_cm1 = float(band.position) + shift
            display_kind = kind
            if display_kind == SignalKind.UNKNOWN and self.active_spectrum is not None:
                display_kind = self.active_spectrum.kind
            position = float(self._convert_display_x([position_cm1], display_kind)[0])
            if not np.isfinite(position):
                continue
            x_values.extend((position, position, np.nan))
            y_values.extend((base, base + stick_height, np.nan))
        self.match_plot.plot(
            x_values,
            y_values,
            pen=pg.mkPen(color, width=max(float(getattr(self.plot_view_settings, "calculated_width", 1.7)), 1.5)),
            name=f"{name} bands",
            connect="finite",
        )

    def _band_has_literature_peak_metadata(self, band) -> bool:
        if str(getattr(band, "mode", "") or "").strip():
            return True
        if str(getattr(band, "symmetry", "") or "").strip():
            return True
        if str(getattr(band, "assignment", "") or "").strip():
            return True
        comment = str(getattr(band, "source_comment", "") or "").strip().lower()
        if not comment:
            return False
        return any(
            token in comment
            for token in (
                "doi",
                "article",
                "literature",
                "reported",
                "table",
                "figure",
                "journal",
                "reference",
                "ferre",
            )
        )

    def _reference_peak_label(self, band) -> str:
        symmetry = str(getattr(band, "symmetry", "") or "").strip()
        if symmetry:
            return symmetry
        mode = str(getattr(band, "mode", "") or "").strip()
        return mode if len(mode) <= 18 else ""

    def _draw_reference_peak_sticks(
        self,
        bands: list,
        *,
        color: str,
        name: str,
        shift: float = 0.0,
        kind: SignalKind = SignalKind.UNKNOWN,
        observed_spectrum: ObservedSpectrum | None = None,
        y_offset: float | None = None,
    ) -> None:
        if not bands:
            return
        literature_bands = [band for band in bands if self._band_has_literature_peak_metadata(band)]
        if not literature_bands:
            return
        y_min, y_max = self._visible_observed_y_extent()
        span = max(y_max - y_min, 1.0e-9)
        intensities = np.asarray([max(float(band.intensity), 0.0) for band in literature_bands], dtype=float)
        scale = float(np.nanmax(intensities)) if intensities.size else 0.0
        if scale <= 0.0:
            intensities = np.ones(len(literature_bands), dtype=float)
            scale = 1.0

        spectrum = observed_spectrum if observed_spectrum is not None else self.active_spectrum
        offset = float(self._active_display_offset if y_offset is None else y_offset)
        raw_observed_x = np.asarray(spectrum.x, dtype=float) if spectrum is not None else np.asarray([])
        observed_y = np.asarray([], dtype=float)
        if spectrum is not None:
            _display_x, display_y = self._display_trace_xy(spectrum)
            observed_y = np.asarray(display_y, dtype=float) + offset

        x_values: list[float] = []
        y_values: list[float] = []
        known_labels: list[tuple[float, float, str]] = []
        unknown_x: list[float] = []
        unknown_y: list[float] = []
        display_kind = kind if kind != SignalKind.UNKNOWN else (spectrum.kind if spectrum is not None else kind)
        zero_line = offset if spectrum is not None else 0.0

        for band, intensity in zip(literature_bands, intensities):
            position_cm1 = float(band.position) + shift
            position = float(self._convert_display_x([position_cm1], display_kind)[0])
            if not np.isfinite(position):
                continue
            baseline = zero_line
            top = baseline + span * 0.92 * max(float(intensity) / scale, 0.025)
            if raw_observed_x.size and observed_y.size == raw_observed_x.size:
                half_window = max(float(getattr(band, "width", 0.0)) * 1.5, 12.0)
                mask = (np.abs(raw_observed_x - position_cm1) <= half_window) & np.isfinite(observed_y)
                local = observed_y[mask]
                if local.size:
                    top = max(float(np.nanmax(local)), baseline + span * 0.025)
            top = min(top, y_max + span * 0.03)
            x_values.extend((position, position, np.nan))
            y_values.extend((baseline, top, np.nan))

            mode_label = self._reference_peak_label(band)
            if mode_label:
                known_labels.append((position, top, mode_label))
            else:
                unknown_x.append(position)
                unknown_y.append(top + span * 0.018)

        self.match_plot.plot(
            x_values,
            y_values,
            pen=pg.mkPen(color, width=max(float(getattr(self.plot_view_settings, "calculated_width", 1.7)), 1.5)),
            name=f"{name} peaks",
            connect="finite",
        )
        if unknown_x:
            self.match_plot.plot(
                unknown_x,
                unknown_y,
                pen=None,
                symbol="o",
                symbolSize=max(int(getattr(self.plot_view_settings, "marker_size", 7)) - 1, 4),
                symbolPen=pg.mkPen(color, width=1.0),
                symbolBrush=pg.mkBrush(color),
            )
        x_min, x_max = self._visible_observed_x_extent()
        x_span = max(x_max - x_min, 1.0e-9)
        for position, top, mode_label in sorted(known_labels, key=lambda item: (item[0], -item[1])):
            place_below = top > y_min + 0.86 * span
            _label_x, label_y, _box = self._place_reference_label(
                position,
                top,
                mode_label,
                place_below=place_below,
                x_span=x_span,
                y_min=y_min,
                y_max=y_max,
            )
            label = pg.TextItem(
                mode_label,
                color=color,
                anchor=(0.5, 0.0 if place_below else 1.0),
                border=pg.mkPen(color, width=0.8),
                fill=pg.mkBrush(255, 255, 255, 220),
            )
            label.setPos(position, label_y)
            self.match_plot.addItem(label)

    def _draw_observed_band_markers(self) -> None:
        result = self._current_preview_result
        spectrum = self.active_spectrum
        if result is None or spectrum is None or not result.observed_bands:
            return

        raw_x = np.asarray(spectrum.x, dtype=float)
        display_x, display_y = self._display_trace_xy(spectrum)
        shown_x = np.asarray(display_x, dtype=float)
        shown_y = np.asarray(display_y, dtype=float) + self._active_display_offset
        if raw_x.size == 0 or shown_x.size != raw_x.size or shown_y.size != raw_x.size:
            return

        marker_size = int(getattr(self.plot_view_settings, "marker_size", 7))
        color = self.selected_candidate_colors.get(result.candidate.key, self._plot_reference_color())

        def points(bands) -> tuple[list[float], list[float]]:
            x_points: list[float] = []
            y_points: list[float] = []
            for band in bands:
                index = int(np.nanargmin(np.abs(raw_x - float(band.position))))
                if np.isfinite(shown_x[index]) and np.isfinite(shown_y[index]):
                    x_points.append(float(shown_x[index]))
                    y_points.append(float(shown_y[index]))
            return x_points, y_points

        if result.unassigned_bands and getattr(self.plot_view_settings, "layer_unknown_peaks_visible", True):
            x_points, y_points = points(result.unassigned_bands)
            self.match_plot.plot(
                x_points,
                y_points,
                pen=None,
                symbol="t",
                symbolSize=marker_size + 2,
                symbolPen=pg.mkPen("#d93025", width=1.5),
                symbolBrush=pg.mkBrush(217, 48, 37, 170),
                name="Unassigned bands",
            )

        if getattr(self.plot_view_settings, "layer_peak_labels_visible", False):
            for band in result.observed_bands:
                index = int(np.nanargmin(np.abs(raw_x - float(band.position))))
                label = pg.TextItem(f"{float(band.position):.1f}", color=color, anchor=(0.5, 1.15))
                label.setPos(float(shown_x[index]), float(shown_y[index]))
                self.match_plot.addItem(label)

    def _multi_offset_step(self, spectra: list[ObservedSpectrum]) -> float:
        if self.action_bar.display_mode.currentText() != "All selected" or len(spectra) < 2:
            return 0.0
        finite_y: list[float] = []
        for spectrum in spectra:
            _x, y = self._display_trace_xy(spectrum)
            values = np.asarray(y, dtype=float)
            finite_y.extend(values[np.isfinite(values)].tolist())
        if not finite_y:
            return 0.0
        amplitude = float(max(finite_y) - min(finite_y))
        if amplitude <= 0.0:
            amplitude = max(abs(float(finite_y[0])), 1.0)
        return amplitude * float(self.action_bar.multi_offset_slider.value()) / 100.0

    def _shift_y(self, y: list[float], offset: float) -> list[float]:
        if offset == 0.0:
            return y
        return [float(value) + offset for value in y]

    def _selected_candidate_color(self, key: str) -> str:
        color = self.selected_candidate_colors.get(key)
        if color is not None:
            return color
        used = set(self.selected_candidate_colors.values())
        color = next((candidate for candidate in REFERENCE_OVERLAY_COLORS if candidate not in used), None)
        if color is None:
            color = REFERENCE_OVERLAY_COLORS[len(self.selected_candidate_colors) % len(REFERENCE_OVERLAY_COLORS)]
        self.selected_candidate_colors[key] = color
        return color

    def _refresh_selected_table(self) -> None:
        for result in self.selected_results:
            self._selected_candidate_color(result.candidate.key)
        self.selected_table.set_selected(
            self.selected_results,
            self.visible_selected_candidate_keys,
            self.selected_candidate_colors,
        )

    def _on_selected_reference_visibility_changed(self, key: str, visible: bool) -> None:
        if visible:
            self.visible_selected_candidate_keys.add(key)
        else:
            self.visible_selected_candidate_keys.discard(key)
        self._save_active_spectrum_profile_state()
        self._redraw_plot()
        if self._reference_view_shows_lines():
            self._reset_plot_view()

    def _show_plot_context_menu(self, point) -> None:
        menu = QMenu(self)
        menu.addAction("Export image...", self._export_plot_image)
        menu.addSeparator()
        menu.addAction("Show full spectrum", self._show_full_plot_range)
        menu.addSeparator()
        menu.addAction(self._plot_setting_action("Grid", "grid_visible"))
        menu.addAction(self._plot_setting_action("Legend", "legend_visible"))
        menu.addAction(self._plot_setting_action("Cursor vertical line", "cursor_vertical_line_visible"))
        menu.addSeparator()
        menu.addAction(self._plot_setting_action("Observed spectrum", "layer_observed_visible"))
        menu.addAction(self._plot_setting_action("Reference preview", "layer_preview_peak_positions_visible"))
        menu.addAction(self._plot_setting_action("Processed spectrum", "layer_total_profile_visible"))
        menu.addAction(self._plot_setting_action("Reference components", "layer_phase_profiles_visible"))
        menu.addAction(self._plot_setting_action("Background", "layer_background_visible"))
        menu.addAction(self._plot_setting_action("Band tick marks", "layer_phase_ticks_visible"))
        menu.addAction(self._plot_setting_action("Assignment markers", "layer_coverage_markers_visible"))
        menu.addAction(self._plot_setting_action("Band labels", "layer_peak_labels_visible"))
        menu.addAction(self._plot_setting_action("Unassigned bands", "layer_unknown_peaks_visible"))
        menu.exec(self.match_plot.mapToGlobal(point))

    def _plot_setting_action(self, label: str, field: str):
        action = QAction(label, self)
        action.setCheckable(True)
        action.setChecked(bool(getattr(self.plot_view_settings, field, False)))
        action.toggled.connect(lambda visible, setting=field: self._set_plot_view_setting(setting, visible))
        return action

    def _set_plot_view_setting(self, field: str, value: bool) -> None:
        self.plot_view_settings = replace(self.plot_view_settings, **{field: bool(value)})
        panel = getattr(self, "plot_settings_panel", None)
        if panel is not None and hasattr(panel, "_apply_settings"):
            blocked = panel.blockSignals(True)
            panel._apply_settings(self.plot_view_settings)
            panel.blockSignals(blocked)
            self.plot_view_settings = panel.settings()
        self._apply_plot_view_settings(self.plot_view_settings)

    def _export_plot_image(self) -> None:
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export image",
            str(Path(self._last_directory()) / "ir_raman_phase_finder_plot.png"),
            "PNG image (*.png);;JPEG image (*.jpg *.jpeg)",
        )
        if not path:
            return
        self._remember_directory(path)
        if not re.search(r"\.(png|jpe?g)$", path, flags=re.IGNORECASE):
            path += ".png"
        try:
            from pyqtgraph.exporters import ImageExporter

            exporter = ImageExporter(self.match_plot.plotItem)
            params = exporter.parameters()
            current_width = max(float(self.match_plot.width()), 1.0)
            export_width = max(3200.0, current_width * 2.0)
            params["width"] = export_width
            legend_state = self._prepare_legend_for_image_export(export_width / current_width)
            try:
                exporter.export(path)
            finally:
                self._restore_legend_after_image_export(legend_state)
        except Exception as exc:
            if not self.match_plot.grab().save(path):
                QMessageBox.warning(self, "Export image", f"Could not save current plot image:\n{exc}")
                return
        self.statusBar().showMessage(f"Exported image: {path}", 6000)

    def _export_active_spectrum(self) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No spectrum", "Import or select a Raman/FTIR spectrum first.")
            return
        default_name = f"{Path(self.active_spectrum.name).stem}_{self.active_spectrum.kind.value}_processed"
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export active spectrum",
            str(Path(self._last_directory()) / default_name),
            "CSV data (*.csv);;JCAMP-DX (*.jdx *.dx)",
        )
        if not path:
            return
        try:
            if selected_filter.startswith("JCAMP") or path.lower().endswith((".jdx", ".dx")):
                if not path.lower().endswith((".jdx", ".dx")):
                    path += ".jdx"
                write_spectrum_jcamp(path, self.active_spectrum)
            else:
                if not path.lower().endswith(".csv"):
                    path += ".csv"
                write_spectrum_csv(path, self.active_spectrum)
        except Exception as exc:
            QMessageBox.warning(self, "Export spectrum", f"Could not export spectrum:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported spectrum: {path}", 6000)

    def _export_candidate_table(self) -> None:
        if not self.results and not self.browse_records:
            QMessageBox.warning(self, "No candidates", "Run a search or browse a reference database first.")
            return
        path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export candidate table",
            str(Path(self._last_directory()) / "ir_raman_candidates.csv"),
            "CSV table (*.csv)",
        )
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        rows: list[dict[str, object]] = []
        if self.results:
            for result in self.results:
                candidate = result.candidate
                rows.append(
                    {
                        "source": candidate.source,
                        "entry": candidate.entry_id,
                        "formula": candidate.formula,
                        "compound": candidate.name,
                        "method": candidate.kind.value,
                        "determination": candidate.metadata.get("determination_method", ""),
                        "orientation": candidate.metadata.get("orientation", "unknown"),
                        "polarization": candidate.metadata.get("polarization", "unknown"),
                        "laser_nm": candidate.metadata.get("laser_nm", ""),
                        "match_percent": round(result.score.combined, 4),
                        "position_score": round(result.score.position, 4),
                        "intensity_score": round(result.score.intensity, 4),
                        "correlation_score": round(result.score.correlation, 4),
                        "coverage_percent": round(result.score.coverage, 4),
                        "matched_bands": result.score.matched_features,
                        "total_bands": result.score.total_features,
                        "shift_cm1": result.score.x_shift,
                        "reference_url": candidate.metadata.get("reference_url", ""),
                    }
                )
        else:
            for record in self.browse_records:
                rows.append(
                    {
                        "source": record.source,
                        "entry": record.entry_id,
                        "formula": record.formula,
                        "compound": record.name,
                        "method": record.kind.value,
                        "determination": record.metadata.get("determination_method", ""),
                        "orientation": record.metadata.get("orientation", "unknown"),
                        "polarization": record.metadata.get("polarization", "unknown"),
                        "laser_nm": record.metadata.get("laser_nm", ""),
                        "reference_url": record.metadata.get("reference_url", ""),
                    }
                )
        try:
            write_match_table(path, rows)
        except Exception as exc:
            QMessageBox.warning(self, "Export candidates", f"Could not export candidate table:\n{exc}")
            return
        self.statusBar().showMessage(f"Exported {len(rows)} candidates: {path}", 6000)

    def _last_directory(self) -> str:
        for spectrum in (self.active_spectrum,):
            if spectrum is not None and spectrum.source_path:
                return str(Path(spectrum.source_path).expanduser().parent)
        return str(Path.cwd())

    def _remember_directory(self, path: str) -> None:
        # Reserved for parity with XRD Finder; current default follows the active spectrum.
        return None

    def _preview_candidate_row(self, row: int, _column: int, previous_row: int, _previous_column: int) -> None:
        if row >= 0 and row != previous_row and row < len(self.results):
            self._preview_result(self.results[row])
        elif row >= 0 and row != previous_row and row < len(self.browse_records):
            self._preview_browse_record(row)

    def _preview_result(self, result: VibrationalMatchResult | None) -> None:
        if result is None:
            self._current_preview_reference = None
            self._current_preview_result = None
            self._redraw_plot()
            self._set_card(None)
            return
        ref = result.aligned_reference
        self._current_preview_reference = ref
        self._current_preview_result = result
        self._redraw_plot()
        self._set_card(result)
        already_visible = result.candidate.key in self.visible_selected_candidate_keys
        if (
            ref is not None
            and self._reference_view_shows_profiles()
            and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True)
            and not already_visible
        ):
            x, y = self._display_trace_xy(ref)
            legend_name = self._legend_candidate_name(result.candidate)
            self.match_plot.plot(
                x,
                self._shift_y(y, self._active_display_offset),
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=legend_name,
            )
        if self._reference_view_shows_lines() and not already_visible:
            bands = self._reference_bands_for_result(result)
            legend_name = self._legend_candidate_name(result.candidate)
            self._draw_reference_peak_sticks(
                bands,
                color=self._plot_reference_color(),
                name=legend_name,
                shift=float(result.score.x_shift),
                kind=result.candidate.kind,
            )
            self._draw_band_sticks(
                bands,
                color=self._plot_reference_color(),
                name=legend_name,
                shift=float(result.score.x_shift),
                kind=result.candidate.kind,
            )

    def _preview_reference(self, reference: ReferenceSpectrum) -> None:
        self._current_preview_result = None
        self._current_preview_reference = reference
        self._redraw_plot()
        if (
            reference.x
            and reference.y
            and self._reference_view_shows_profiles()
            and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True)
        ):
            x, y = self._display_trace_xy(reference)
            legend_name = self._legend_reference_name(reference)
            self.match_plot.plot(
                x,
                self._shift_y(y, self._active_display_offset),
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=legend_name,
            )
        if self._reference_view_shows_lines():
            if reference.band_set is None:
                origin = "experimental"
                if reference.record is not None:
                    origin = self._reference_origin(reference.record)
                reference.band_set = extract_reference_band_set(reference, origin=origin)
            legend_name = self._legend_reference_name(reference)
            self._draw_reference_peak_sticks(
                reference.band_set.bands,
                color=self._plot_reference_color(),
                name=legend_name,
                kind=reference.kind,
            )
            self._draw_band_sticks(
                reference.band_set.bands,
                color=self._plot_reference_color(),
                name=legend_name,
                kind=reference.kind,
            )

    def _preview_browse_record(self, row: int) -> None:
        if row < 0 or row >= len(self.browse_records):
            return
        record = self.browse_records[row]
        try:
            reference = self._load_reference_record(record)
        except Exception as exc:
            candidate = CompoundCandidate(
                key=record.key,
                source=record.source,
                entry_id=record.entry_id,
                name=record.name,
                formula=record.formula,
                kind=record.kind,
                metadata=dict(record.metadata),
                reference=None,
            )
            self._set_reference_card(VibrationalMatchResult(candidate=candidate, score=MatchScore()))
            self.statusBar().showMessage(f"Could not load reference spectrum: {exc}", 8000)
            return
        candidate = CompoundCandidate(
            key=record.key,
            source=record.source,
            entry_id=record.entry_id,
            name=record.name,
            formula=record.formula,
            kind=record.kind,
            metadata=dict(record.metadata),
            reference=reference,
            band_set=reference.band_set,
        )
        reference_bands = (
            list(reference.band_set.bands)
            if reference.band_set is not None
            else extract_reference_band_set(
                reference,
                origin=self._reference_origin(record),
            ).bands
        )
        result = VibrationalMatchResult(
            candidate=candidate,
            score=MatchScore(),
            reference_bands=reference_bands,
            aligned_reference=reference,
        )
        self._current_preview_result = result
        self._current_preview_reference = reference
        self._redraw_plot()
        if (
            reference.x
            and reference.y
            and self._reference_view_shows_profiles()
            and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True)
        ):
            x, y = self._display_trace_xy(reference)
            legend_name = self._legend_candidate_name(candidate)
            self.match_plot.plot(
                x,
                self._shift_y(y, self._active_display_offset),
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=legend_name,
            )
        if self._reference_view_shows_lines():
            legend_name = self._legend_candidate_name(candidate)
            self._draw_reference_peak_sticks(
                result.reference_bands,
                color=self._plot_reference_color(),
                name=legend_name,
                kind=reference.kind,
            )
            self._draw_band_sticks(
                result.reference_bands,
                color=self._plot_reference_color(),
                name=legend_name,
                kind=reference.kind,
            )
        self._set_reference_card(result)

    def _set_reference_card(self, result: VibrationalMatchResult) -> None:
        self._set_card(result)
        for key in ("Match", "Position score", "Intensity score", "Correlation", "Coverage", "X shift"):
            if key in self.card_labels:
                self.card_labels[key].setText("-")

    def _sample_key(self, spectrum: ObservedSpectrum | None = None) -> str:
        spectrum = spectrum or self.active_spectrum
        if spectrum is None:
            return ""
        return spectrum.source_path or f"{spectrum.kind.value}:{spectrum.name}"

    def _initialize_sample_card(self, spectrum: ObservedSpectrum) -> None:
        key = self._sample_key(spectrum)
        self.sample_metadata.setdefault(
            key,
            {
                "name": spectrum.name,
                "source_path": spectrum.source_path,
                "method": spectrum.kind.value.upper(),
                "laser_nm": f"{self._selected_laser_wavelength_nm():g}" if spectrum.kind == SignalKind.RAMAN else "",
                "orientation": "",
                "polarization": "",
                "instrument": "",
                "notes": "",
            },
        )
        self.sample_bands[key] = detect_bands(spectrum, BandDetectionOptions(backend="auto", fit_peaks=False))
        self._refresh_sample_card()

    def _refresh_sample_card(self) -> None:
        if not hasattr(self, "sample_card_fields"):
            return
        spectrum = self.active_spectrum
        if spectrum is None:
            self.sample_card_title.setText("No sample selected")
            for field in self.sample_card_fields.values():
                field.clear()
            self.sample_band_table.setRowCount(0)
            return
        key = self._sample_key(spectrum)
        if key not in self.sample_metadata:
            self._initialize_sample_card(spectrum)
            return
        metadata = self.sample_metadata[key]
        self.sample_card_title.setText(metadata.get("name") or spectrum.name or "Sample")
        for field_key, field in self.sample_card_fields.items():
            blocked = field.blockSignals(True)
            field.setText(metadata.get(field_key, ""))
            field.blockSignals(blocked)
        bands = self.sample_bands.get(key, [])
        self._updating_card_tables = True
        self.sample_band_table.setRowCount(len(bands))
        for row, band in enumerate(bands):
            values = [
                f"{band.position:.3f}",
                f"{band.intensity:.5g}",
                f"{band.width:.3f}" if band.width else "",
                getattr(band, "mode", ""),
                band.symmetry,
                band.assignment,
                f"{band.confidence:.3f}",
                getattr(band, "source_comment", ""),
            ]
            for column, value in enumerate(values):
                self.sample_band_table.setItem(row, column, QTableWidgetItem(value))
        self._updating_card_tables = False

    def _save_sample_card_fields(self) -> None:
        spectrum = self.active_spectrum
        if spectrum is None:
            return
        key = self._sample_key(spectrum)
        metadata = self.sample_metadata.setdefault(key, {})
        for field_key, field in self.sample_card_fields.items():
            metadata[field_key] = field.text().strip()
        if spectrum.kind == SignalKind.RAMAN:
            try:
                laser = float(metadata.get("laser_nm", "").replace(",", "."))
            except ValueError:
                laser = 0.0
            if laser > 0:
                self.action_bar.laser_wavelength_spin.setValue(laser)
        self.sample_card_title.setText(metadata.get("name") or spectrum.name or "Sample")

    @staticmethod
    def _editable_number(text: str, current: float) -> float:
        try:
            return float(text.strip().replace(",", "."))
        except ValueError:
            return current

    def _on_sample_band_cell_changed(self, row: int, column: int) -> None:
        if self._updating_card_tables or self.active_spectrum is None:
            return
        bands = self.sample_bands.get(self._sample_key(), [])
        if not (0 <= row < len(bands)):
            return
        band = bands[row]
        text = self.sample_band_table.item(row, column).text().strip()
        if column == 0:
            band.position = self._editable_number(text, band.position)
        elif column == 1:
            band.intensity = self._editable_number(text, band.intensity)
        elif column == 2:
            band.width = self._editable_number(text, band.width)
        elif column == 3:
            band.mode = text
        elif column == 4:
            band.symmetry = text
        elif column == 5:
            band.assignment = text
        elif column == 6:
            band.confidence = self._editable_number(text, band.confidence)
        elif column == 7:
            band.source_comment = text

    def _on_reference_band_cell_changed(self, row: int, column: int) -> None:
        if self._updating_card_tables or self._current_preview_result is None:
            return
        result = self._current_preview_result
        reference_changed = False
        if not result.observed_bands and 0 <= row < len(result.reference_bands):
            band = result.reference_bands[row]
            item = self.band_table.item(row, column)
            text = item.text().strip() if item is not None else ""
            if column == 1:
                band.position = self._editable_number(text, band.position)
                reference_changed = True
            elif column == 3:
                band.intensity = self._editable_number(text, band.intensity)
                reference_changed = True
            elif column == 4:
                band.width = self._editable_number(text, band.width)
                reference_changed = True
            elif column == 5:
                band.mode = text
                reference_changed = True
            elif column == 6:
                band.symmetry = text
                reference_changed = True
            elif column == 7:
                band.assignment = text
                reference_changed = True
            if reference_changed:
                self._save_current_user_reference_card()
            return
        if not (0 <= row < len(result.observed_bands)):
            return
        observed = result.observed_bands[row]
        item = self.band_table.item(row, column)
        text = item.text().strip() if item is not None else ""
        if column == 0:
            observed.position = self._editable_number(text, observed.position)
            return
        nearest = (
            min(result.reference_bands, key=lambda band: abs(band.position - observed.position))
            if result.reference_bands
            else None
        )
        if nearest is None:
            return
        if column == 1:
            nearest.position = self._editable_number(text, nearest.position)
            reference_changed = True
        elif column == 3:
            observed.intensity = self._editable_number(text, observed.intensity)
        elif column == 4:
            nearest.width = self._editable_number(text, nearest.width)
            reference_changed = True
        elif column == 5:
            nearest.mode = text
            reference_changed = True
        elif column == 6:
            nearest.symmetry = text
            reference_changed = True
        elif column == 7:
            nearest.assignment = text
            reference_changed = True
        if reference_changed:
            self._save_current_user_reference_card()

    def _current_user_reference_path(self) -> Path | None:
        result = self._current_preview_result
        if result is None or result.candidate.source != EditableReferenceSource.name:
            return None
        raw_path = str(result.candidate.metadata.get("path", "") or "")
        if not raw_path:
            return None
        path = Path(raw_path)
        if path.suffix.lower() != ".vsref":
            return None
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            return None
        user_root = self._user_reference_root().resolve()
        if user_root not in resolved.parents and resolved.parent != user_root:
            return None
        return resolved

    def _save_current_user_reference_card(self) -> None:
        result = self._current_preview_result
        path = self._current_user_reference_path()
        if result is None or path is None:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.statusBar().showMessage(f"Could not read reference card: {exc}", 6000)
            return
        payload["bands"] = [self._reference_band_to_payload(band) for band in result.reference_bands]
        try:
            write_editable_reference(path, payload)
            band_set = ReferenceBandSet(
                bands=list(result.reference_bands),
                origin=str(result.candidate.metadata.get("origin") or "experimental"),
                extraction_method="manual/reference-card",
            )
            result.candidate.band_set = band_set
            if result.candidate.reference is not None:
                result.candidate.reference.band_set = band_set
            if result.aligned_reference is not None:
                result.aligned_reference.band_set = band_set
            self._user_reference_cache().upsert_band_set(
                result.candidate.key,
                band_set,
                USER_REFERENCE_BAND_RECIPE_VERSION,
            )
            self._update_database_table()
            self.statusBar().showMessage(f"Reference card saved: {path.name}", 3000)
        except Exception as exc:
            self.statusBar().showMessage(f"Could not save reference card: {exc}", 6000)

    def _reference_band_to_payload(self, band: SpectralBand) -> dict[str, object]:
        return {
            "position_cm1": float(band.position),
            "intensity": float(band.intensity),
            "fwhm_cm1": float(band.width),
            "mode": band.mode,
            "symmetry": band.symmetry,
            "assignment": band.assignment,
            "polarization": band.polarization,
            "orientation": band.orientation,
            "confidence": "manual",
            "confidence_value": float(band.confidence),
            "comment": band.source_comment,
        }

    def _load_reference_record(self, record: CandidateRecord) -> ReferenceSpectrum:
        if record.source == self.rruff_source.name:
            return self.rruff_source.load_spectrum(record)
        if record.source == self.rod_source.name:
            return self.rod_source.load_spectrum(record)
        if record.source == self.openspecy_source.name:
            return self.openspecy_source.load_spectrum(record)
        if record.source == self.jarvis_source.name:
            return self.jarvis_source.load_spectrum(record)
        for source in self.user_libraries:
            if any(candidate.key == record.key for candidate in source.search(SourceQuery())):
                return source.load_spectrum(record)
        raise FileNotFoundError(record.key)

    def _add_selected_candidate(self) -> None:
        row = self.candidate_table.currentRow()
        if row < 0 or row >= len(self.results):
            return
        result = self.results[row]
        key = result.candidate.key
        if all(selected.candidate.key != key for selected in self.selected_results):
            self.selected_results.append(result)
        self.visible_selected_candidate_keys.add(key)
        self._selected_candidate_color(key)
        self._refresh_selected_table()
        self._save_active_spectrum_profile_state()
        self._redraw_plot()
        if self._reference_view_shows_lines():
            self._reset_plot_view()

    def _set_card(self, result: VibrationalMatchResult | None) -> None:
        if result is None:
            self.card_title.setText("No compound selected")
            for label in self.card_labels.values():
                label.setText("-")
            self.band_table.setRowCount(0)
            return
        candidate = result.candidate
        self.card_title.setText(candidate.name or candidate.entry_id or "Selected compound")
        values = {
            "Name": candidate.name,
            "Formula": candidate.formula,
            "Method": candidate.kind.value.upper(),
            "Source": candidate.source,
            "Entry": candidate.entry_id,
            "Quality": candidate.metadata.get("quality", "measured reference" if candidate.source else "-"),
            "Orientation": candidate.metadata.get("orientation", "unknown"),
            "Polarization": candidate.metadata.get("polarization", "unknown"),
            "Match": f"{result.score.combined:.1f}%",
            "Position score": f"{result.score.position:.1f}%",
            "Intensity score": f"{result.score.intensity:.1f}%",
            "Correlation": f"{result.score.correlation:.1f}%",
            "Coverage": f"{result.score.coverage:.1f}%",
            "X shift": f"{result.score.x_shift:.1f} cm-1",
            "Raman available": "yes" if candidate.kind == SignalKind.RAMAN else "unknown",
            "FTIR available": "yes" if candidate.kind == SignalKind.FTIR else "unknown",
            "XRD available": "unknown",
            "Reference path": self._reference_path_label(candidate),
        }
        for key, label in self.card_labels.items():
            label.setText(str(values.get(key, "-") or "-"))
            if key == "Reference path":
                label.setToolTip(candidate.metadata.get("path", "-"))
        self._set_band_rows(result)

    def _reference_path_label(self, candidate: CompoundCandidate) -> str:
        raw_path = candidate.metadata.get("path", "")
        if not raw_path:
            return "-"
        member_name = raw_path.split(":", 1)[-1]
        laser = candidate.metadata.get("laser_nm", "")
        if candidate.source == "RRUFF":
            variant = "processed" if "processed" in member_name.lower() else "raw" if "raw" in member_name.lower() else ""
            parts = [candidate.entry_id, candidate.kind.value.upper()]
            if laser:
                parts.append(f"{laser} nm")
            if variant:
                parts.append(variant)
            return " / ".join(parts)
        return Path(member_name).name

    def _set_band_rows(self, result: VibrationalMatchResult) -> None:
        self._updating_card_tables = True
        if not result.observed_bands:
            self.band_table.setRowCount(len(result.reference_bands))
            for row, band in enumerate(result.reference_bands):
                values = [
                    "-",
                    f"{band.position:.2f}",
                    "-",
                    f"{band.intensity:.3f}",
                    f"{band.width:.3f}" if band.width else "",
                    getattr(band, "mode", ""),
                    band.symmetry,
                    band.assignment,
                ]
                for column, value in enumerate(values):
                    self.band_table.setItem(row, column, QTableWidgetItem(value))
            self._updating_card_tables = False
            return
        self.band_table.setRowCount(len(result.observed_bands))
        for row, band in enumerate(result.observed_bands):
            nearest_band = (
                min(result.reference_bands, key=lambda candidate: abs(candidate.position - band.position))
                if result.reference_bands
                else None
            )
            nearest = nearest_band.position if nearest_band is not None else None
            delta = band.position - nearest if nearest is not None else None
            values = [
                f"{band.position:.2f}",
                f"{nearest:.2f}" if nearest is not None else "-",
                f"{delta:.2f}" if delta is not None else "-",
                f"{band.intensity:.3f}",
                f"{nearest_band.width:.3f}" if nearest_band is not None and nearest_band.width else "",
                getattr(nearest_band, "mode", "") if nearest_band is not None else "",
                nearest_band.symmetry if nearest_band is not None else "",
                nearest_band.assignment if nearest_band is not None else "",
            ]
            for column, value in enumerate(values):
                self.band_table.setItem(row, column, QTableWidgetItem(value))
        self._updating_card_tables = False

    def _section_style(self) -> str:
        colors = _theme_palette(getattr(self, "current_theme", "Light"))
        return (
            f"background: {colors['section']}; border: 1px solid {colors['border']}; border-radius: 3px; "
            "color: #f1f3f4; font-weight: 700; padding: 5px 7px;"
        )

    def _section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(self._section_style())
        return label

    def _field_grid(self, rows: list[tuple[str, str]]) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        for row_index, (key, caption) in enumerate(rows):
            name = QLabel(caption)
            name.setProperty("fieldNameLabel", True)
            name.setStyleSheet(
                "background: #282c31; border-left: 3px solid #e9328f; "
                "color: #d4dde7; font-weight: 700; padding: 4px 7px;"
            )
            value = QLabel("-")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setMinimumWidth(1)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            colors = _theme_palette(getattr(self, "current_theme", "Light"))
            value.setStyleSheet(f"background: {colors['field_value']}; color: {colors['text']}; padding: 4px 6px;")
            self.card_labels[key] = value
            grid.addWidget(name, row_index, 0)
            grid.addWidget(value, row_index, 1)
        grid.setColumnStretch(1, 1)
        return grid

    def _card_table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            table.setColumnWidth(column, 112)
        return table

    def _management_button_style(self, role: str) -> str:
        colors = {
            "download": ("#0b8043", "#35a96c"),
            "clear": ("#9f2424", "#d45b5b"),
            "sql": ("#7b4fb3", "#a782d8"),
            "create": ("#2367a5", "#5a9bd8"),
            "open": ("#5f6368", "#8a8d91"),
        }
        background, border = colors.get(role, ("#2367a5", "#5a9bd8"))
        return _glass_button_style(background, border)

    def _management_row(self, label_text: str, actions: list[tuple[str, object] | tuple[str, object, str]]) -> QWidget:
        row = QWidget()
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(label_text)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title, 0, 0, 1, 2)
        for index, action in enumerate(actions):
            button_text = action[0]
            callback = action[1]
            role = action[2] if len(action) > 2 else "default"
            button = QPushButton(button_text)
            button.setMinimumHeight(28)
            button.setStyleSheet(self._management_button_style(str(role)))
            button.clicked.connect(callback)
            layout.addWidget(button, 1 + index // 2, index % 2)
        return row

    def _update_database_table(self) -> None:
        if not hasattr(self, "database_table"):
            return
        raman_count = sum(1 for record in self.reference_records if record.kind == SignalKind.RAMAN)
        ftir_count = sum(1 for record in self.reference_records if record.kind == SignalKind.FTIR)
        user_cache = self._user_reference_cache()
        user_sql_records = user_cache.indexed_count(source=EditableReferenceSource.name)
        user_sql_band_refs = user_cache.indexed_band_reference_count(
            EditableReferenceSource.name,
            USER_REFERENCE_BAND_RECIPE_VERSION,
        )
        user_sql_bands = user_cache.indexed_band_count(
            EditableReferenceSource.name,
            USER_REFERENCE_BAND_RECIPE_VERSION,
        )
        user_sql_size = user_cache.size_bytes()
        rruff_row = self.rruff_source.status_row()
        rod_row = self.rod_source.status_row()
        openspecy_row = self.openspecy_source.status_row()
        jarvis_row = self.jarvis_source.status_row()
        rows = [
            [
                "User Library",
                "Loaded" if self.user_libraries else "Empty",
                f"{len(self.user_libraries)} libraries, {raman_count} Raman, {ftir_count} FTIR",
                str(len(self.reference_records)),
                "-",
            ],
            [
                "User SQL line index",
                "Indexed" if user_sql_records else "Empty",
                f"{user_sql_band_refs} references with lines, {user_sql_bands} bands; local user-built SQLite",
                str(user_sql_records),
                _format_bytes(user_sql_size),
            ],
            [
                "Import formats",
                "Available" if ramanchada2_available() else "Basic",
                "ramanchada2 vendor backend" if ramanchada2_available() else "TXT/CSV/JCAMP; install optional formats extra for SPC/SPA/WDF/NGS",
                "-",
                "-",
            ],
            [rruff_row[0], rruff_row[1], rruff_row[2], rruff_row[3], rruff_row[4]],
            [rod_row[0], rod_row[1], rod_row[2], rod_row[3], rod_row[4]],
            [openspecy_row[0], openspecy_row[1], openspecy_row[2], openspecy_row[3], openspecy_row[4]],
            [jarvis_row[0], jarvis_row[1], jarvis_row[2], jarvis_row[3], jarvis_row[4]],
        ]
        self.database_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column, value in enumerate(row):
                self.database_table.setItem(row_index, column, QTableWidgetItem(value))

    def _clear_user_libraries(self) -> None:
        self.user_libraries.clear()
        self.reference_records.clear()
        self.reference_spectra.clear()
        self.results.clear()
        self.candidate_table.set_results([])
        self._update_database_table()
        self._refresh_project_tree()

    def _replace_editable_reference_source(self) -> EditableReferenceSource | None:
        root = self._user_reference_root()
        if not any(root.glob("*.vsref")):
            return None
        self.user_libraries = [
            source
            for source in self.user_libraries
            if not (isinstance(source, EditableReferenceSource) and source.path == root)
        ]
        self.reference_records = [record for record in self.reference_records if record.source != EditableReferenceSource.name]
        self.reference_spectra = [
            spectrum
            for spectrum in self.reference_spectra
            if spectrum.record is None or spectrum.record.source != EditableReferenceSource.name
        ]
        source = EditableReferenceSource(root, cache_root=root)
        self._add_user_library_source(source)
        return source

    def _build_user_reference_band_index(self) -> None:
        root = self._user_reference_root()
        if not any(root.glob("*.vsref")):
            QMessageBox.information(self, "User SQL line index", "No .vsref user references found.")
            return
        cache = self._user_reference_cache()
        cache.clear_source(EditableReferenceSource.name)
        source = self._replace_editable_reference_source()
        records = source.indexed_record_count() if source is not None else 0
        bands = source.indexed_band_count() if source is not None else 0
        self._update_database_table()
        self.statusBar().showMessage(
            f"User SQL line index updated: {records} records, {bands} bands, {_format_bytes(cache.size_bytes())}.",
            8000,
        )

    def _clear_user_reference_band_index(self) -> None:
        cache = self._user_reference_cache()
        cache.clear_source(EditableReferenceSource.name)
        self._update_database_table()
        self.statusBar().showMessage("User SQL line index cleared.", 6000)

    def _build_all_band_indexes(self) -> None:
        def task() -> list[str]:
            messages: list[str] = []
            root = self._user_reference_root()
            if any(root.glob("*.vsref")):
                cache = self._user_reference_cache()
                cache.clear_source(EditableReferenceSource.name)
                source = EditableReferenceSource(root, cache_root=root)
                messages.append(
                    f"User: {source.indexed_record_count()} records, {source.indexed_band_count()} bands"
                )
            else:
                messages.append("User: skipped, no .vsref references")

            try:
                indexed, skipped = self.rruff_source.build_band_index()
                messages.append(f"RRUFF: {indexed} new, {skipped} skipped")
            except Exception as exc:
                messages.append(f"RRUFF: skipped, {exc}")

            if self.rod_source.indexed_count() > 0:
                try:
                    indexed, skipped = self.rod_source.build_band_index()
                    messages.append(f"ROD: {indexed} new, {skipped} skipped")
                except Exception as exc:
                    messages.append(f"ROD: skipped, {exc}")
            else:
                messages.append("ROD: skipped, download database first")

            if self.jarvis_source.indexed_count() > 0:
                try:
                    indexed, skipped = self.jarvis_source.build_band_index()
                    messages.append(f"JARVIS-DFT: {indexed} new, {skipped} skipped")
                except Exception as exc:
                    messages.append(f"JARVIS-DFT: skipped, {exc}")
            else:
                messages.append("JARVIS-DFT: skipped, download database first")

            if self.openspecy_source.search(SourceQuery()):
                try:
                    indexed, skipped = self.openspecy_source.build_band_index()
                    messages.append(f"OpenSpecy: {indexed} new, {skipped} skipped")
                except Exception as exc:
                    messages.append(f"OpenSpecy: skipped, {exc}")
            else:
                messages.append("OpenSpecy: skipped, download library first")

            return messages

        def success(messages: list[str]) -> None:
            self._replace_editable_reference_source()
            self._update_database_table()
            QMessageBox.information(self, "SQL line indexes updated", "\n".join(messages))

        self._run_background_task(
            "Update SQL line indexes",
            "Updating SQL line indexes for all available databases...",
            task,
            success,
            lambda message, _details: QMessageBox.warning(self, "SQL index update failed", message),
        )

    def _clear_all_band_indexes(self) -> None:
        cache = self._user_reference_cache()
        cache.clear_source(EditableReferenceSource.name)
        self.rruff_source.clear_band_index()
        self.rod_source.clear_band_index()
        self.jarvis_source.clear_band_index()
        self.openspecy_source.clear_band_index()
        self._update_database_table()
        self.statusBar().showMessage("All SQL line indexes cleared.", 6000)

    def _run_background_task(self, title: str, label: str, task, success, failure=None) -> None:
        progress = QProgressDialog(label, None, 0, 0, self)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(250)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        handle = BackgroundTaskHandle(task, self)
        self._background_tasks.append(handle)

        def cleanup() -> None:
            progress.close()
            if handle in self._background_tasks:
                self._background_tasks.remove(handle)

        def on_finished(result) -> None:
            cleanup()
            success(result)

        def on_failed(message: str, details: str) -> None:
            cleanup()
            if failure is not None:
                failure(message, details)
            else:
                QMessageBox.warning(self, f"{title} failed", message)

        handle.finished.connect(on_finished)
        handle.failed.connect(on_failed)
        handle.start()

    def _update_rruff(self) -> None:
        archive_key = "excellent_unoriented"
        if hasattr(self, "rruff_archive_combo"):
            archive_key = str(self.rruff_archive_combo.currentData() or archive_key)

        def success(result) -> None:
            path = Path(str(result))
            self._refresh_rruff_archive_combo()
            self._update_database_table()
            if "RRUFF" in getattr(self, "source_checks", {}):
                self.source_checks["RRUFF"].setChecked(True)
            QMessageBox.information(self, "RRUFF updated", f"Downloaded and indexed:\n{path}")

        self._run_background_task(
            "Update RRUFF",
            "Downloading and indexing RRUFF spectra...",
            lambda: self.rruff_source.download_archive(archive_key),
            success,
            lambda message, _details: QMessageBox.warning(self, "RRUFF update failed", message),
        )

    def _clear_rruff(self) -> None:
        for archive in self.rruff_source.available_archives():
            try:
                archive.path.unlink(missing_ok=True)
                archive.path.with_suffix(archive.path.suffix + ".part").unlink(missing_ok=True)
            except OSError:
                pass
        self.rruff_source.refresh_index()
        self._refresh_rruff_archive_combo()
        self._update_database_table()

    def _build_rruff_band_index(self) -> None:
        def success(result) -> None:
            indexed, skipped = result
            self._update_database_table()
            QMessageBox.information(
                self,
                "RRUFF line index",
                f"SQL line index updated.\n\nNew records: {indexed}\nSkipped: {skipped}\n"
                f"Total indexed: {self.rruff_source.indexed_band_count()}",
            )

        self._run_background_task(
            "Build RRUFF line index",
            "Extracting normalized Raman/FTIR bands and writing SQLite index...",
            self.rruff_source.build_band_index,
            success,
            lambda message, _details: QMessageBox.warning(self, "RRUFF line indexing failed", message),
        )

    def _clear_rruff_band_index(self) -> None:
        self.rruff_source.clear_band_index()
        self._update_database_table()
        self.statusBar().showMessage("RRUFF SQL line index cleared.", 6000)

    def _update_rod(self) -> None:
        def success(result) -> None:
            path = Path(str(result))
            self._update_database_table()
            if "ROD" in getattr(self, "source_checks", {}):
                enabled = self.rod_source.indexed_count() > 0
                self.source_checks["ROD"].setEnabled(enabled)
                self.source_checks["ROD"].setChecked(enabled)
            QMessageBox.information(
                self,
                "ROD updated",
                f"Downloaded and indexed {self.rod_source.indexed_count()} Raman records:\n{path}",
            )

        self._run_background_task(
            "Update ROD",
            "Downloading and indexing the Raman Open Database...",
            self.rod_source.download_archive,
            success,
            lambda message, _details: QMessageBox.warning(self, "ROD update failed", message),
        )

    def _clear_rod(self) -> None:
        self.rod_source.clear()
        self._update_database_table()
        if "ROD" in getattr(self, "source_checks", {}):
            self.source_checks["ROD"].setChecked(False)
            self.source_checks["ROD"].setEnabled(False)

    def _build_rod_band_index(self) -> None:
        if self.rod_source.indexed_count() <= 0:
            QMessageBox.information(self, "ROD line index", "Download/index the Raman Open Database first.")
            return

        def success(result) -> None:
            indexed, skipped = result
            self._update_database_table()
            QMessageBox.information(
                self,
                "ROD line index",
                f"SQL line index updated.\n\nNew records: {indexed}\nSkipped: {skipped}\n"
                f"Total indexed: {self.rod_source.indexed_band_count()}",
            )

        self._run_background_task(
            "Build ROD line index",
            "Extracting normalized ROD Raman bands and writing SQLite index...",
            self.rod_source.build_band_index,
            success,
            lambda message, _details: QMessageBox.warning(self, "ROD line indexing failed", message),
        )

    def _clear_rod_band_index(self) -> None:
        self.rod_source.clear_band_index()
        self._update_database_table()
        self.statusBar().showMessage("ROD SQL line index cleared.", 6000)

    def _update_jarvis(self) -> None:
        def success(result) -> None:
            path = Path(str(result))
            self._update_database_table()
            if "JARVIS-DFT" in getattr(self, "source_checks", {}):
                enabled = self.jarvis_source.indexed_count() > 0
                self.source_checks["JARVIS-DFT"].setEnabled(enabled)
                self.source_checks["JARVIS-DFT"].setChecked(enabled)
            QMessageBox.information(
                self,
                "JARVIS-DFT updated",
                f"Indexed {self.jarvis_source.indexed_count(SignalKind.FTIR)} calculated FTIR records:\n{path}",
            )

        self._run_background_task(
            "Update JARVIS-DFT",
            "Downloading and indexing JARVIS-DFT vibrational metadata...",
            self.jarvis_source.download_metadata,
            success,
            lambda message, _details: QMessageBox.warning(self, "JARVIS-DFT update failed", message),
        )

    def _clear_jarvis(self) -> None:
        self.jarvis_source.clear()
        self._update_database_table()
        if "JARVIS-DFT" in getattr(self, "source_checks", {}):
            self.source_checks["JARVIS-DFT"].setChecked(False)
            self.source_checks["JARVIS-DFT"].setEnabled(False)

    def _build_jarvis_band_index(self) -> None:
        if self.jarvis_source.indexed_count() <= 0:
            QMessageBox.information(self, "JARVIS-DFT line index", "Download/index JARVIS-DFT metadata first.")
            return

        def success(result) -> None:
            indexed, skipped = result
            self._update_database_table()
            QMessageBox.information(
                self,
                "JARVIS-DFT line index",
                f"SQL line index updated.\n\nNew records: {indexed}\nSkipped: {skipped}\n"
                f"Total indexed: {self.jarvis_source.indexed_band_count()}",
            )

        self._run_background_task(
            "Build JARVIS-DFT line index",
            "Writing calculated JARVIS-DFT vibrational modes to SQLite index...",
            self.jarvis_source.build_band_index,
            success,
            lambda message, _details: QMessageBox.warning(self, "JARVIS-DFT line indexing failed", message),
        )

    def _clear_jarvis_band_index(self) -> None:
        self.jarvis_source.clear_band_index()
        self._update_database_table()
        self.statusBar().showMessage("JARVIS-DFT SQL line index cleared.", 6000)

    def _update_openspecy(self) -> None:
        library_key = "medoid_derivative"
        if hasattr(self, "openspecy_library_combo"):
            library_key = str(self.openspecy_library_combo.currentData() or library_key)

        def success(result) -> None:
            path = Path(str(result))
            self._refresh_openspecy_library_combo()
            self._update_database_table()
            if "OpenSpecy" in getattr(self, "source_checks", {}):
                enabled = bool(self.openspecy_source.search(SourceQuery()))
                self.source_checks["OpenSpecy"].setEnabled(enabled)
                self.source_checks["OpenSpecy"].setChecked(enabled)
            QMessageBox.information(self, "OpenSpecy updated", f"Downloaded and indexed if possible:\n{path}")

        self._run_background_task(
            "Update OpenSpecy",
            "Downloading and indexing OpenSpecy library...",
            lambda: self.openspecy_source.download_library(library_key),
            success,
            lambda message, _details: QMessageBox.warning(self, "OpenSpecy update failed", message),
        )

    def _clear_openspecy(self) -> None:
        self.openspecy_source.clear()
        self._refresh_openspecy_library_combo()
        self._update_database_table()
        if "OpenSpecy" in getattr(self, "source_checks", {}):
            self.source_checks["OpenSpecy"].setEnabled(False)
            self.source_checks["OpenSpecy"].setChecked(False)

    def _build_openspecy_band_index(self) -> None:
        if not self.openspecy_source.search(SourceQuery()):
            QMessageBox.information(self, "OpenSpecy line index", "Download/index an OpenSpecy library first.")
            return

        def success(result) -> None:
            indexed, skipped = result
            self._update_database_table()
            QMessageBox.information(
                self,
                "OpenSpecy line index",
                f"SQL line index updated.\n\nNew records: {indexed}\nSkipped: {skipped}\n"
                f"Total indexed: {self.openspecy_source.indexed_band_count()}",
            )

        self._run_background_task(
            "Build OpenSpecy line index",
            "Extracting normalized OpenSpecy bands and writing SQLite index...",
            self.openspecy_source.build_band_index,
            success,
            lambda message, _details: QMessageBox.warning(self, "OpenSpecy line indexing failed", message),
        )

    def _clear_openspecy_band_index(self) -> None:
        self.openspecy_source.clear_band_index()
        self._update_database_table()
        self.statusBar().showMessage("OpenSpecy SQL line index cleared.", 6000)

    def _refresh_rruff_archive_combo(self) -> None:
        if not hasattr(self, "rruff_archive_combo"):
            return
        current = self.rruff_archive_combo.currentData()
        self.rruff_archive_combo.blockSignals(True)
        self.rruff_archive_combo.clear()
        restore_index = 0
        for index, archive in enumerate(self.rruff_source.available_archives()):
            cache_text = "cached" if archive.is_cached else "not cached"
            self.rruff_archive_combo.addItem(f"{archive.label} ({cache_text})", archive.key)
            if archive.key == current:
                restore_index = index
        self.rruff_archive_combo.setCurrentIndex(restore_index)
        self.rruff_archive_combo.blockSignals(False)

    def _refresh_openspecy_library_combo(self) -> None:
        if not hasattr(self, "openspecy_library_combo"):
            return
        current = self.openspecy_library_combo.currentData()
        self.openspecy_library_combo.blockSignals(True)
        self.openspecy_library_combo.clear()
        restore_index = 0
        for index, library in enumerate(self.openspecy_source.available_libraries()):
            cache_text = "cached" if library.is_cached else "not cached"
            self.openspecy_library_combo.addItem(f"{library.label} ({cache_text})", library.key)
            if library.key == current:
                restore_index = index
        self.openspecy_library_combo.setCurrentIndex(restore_index)
        self.openspecy_library_combo.blockSignals(False)

    def _set_rruff_archive_combo_key(self, key: str) -> None:
        if not hasattr(self, "rruff_archive_combo"):
            return
        for index in range(self.rruff_archive_combo.count()):
            if self.rruff_archive_combo.itemData(index) == key:
                self.rruff_archive_combo.setCurrentIndex(index)
                return

    def _set_openspecy_library_combo_key(self, key: str) -> None:
        if not hasattr(self, "openspecy_library_combo"):
            return
        for index in range(self.openspecy_library_combo.count()):
            if self.openspecy_library_combo.itemData(index) == key:
                self.openspecy_library_combo.setCurrentIndex(index)
                return

    def _open_external_source(self, key: str) -> None:
        try:
            source = external_source_by_key(key)
        except KeyError:
            QMessageBox.warning(self, "External source", f"Unknown external source: {key}")
            return
        query = SourceQuery(
            text=self._reference_search_text(),
            formula=self._element_formula_query(),
        )
        url = source.search_url(query)
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "External source", f"Could not open:\n{url}")

    def _system_theme(self) -> str:
        try:
            return "Dark" if QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark else "Light"
        except Exception:
            return "Light"

    def _apply_theme(self, theme: str) -> None:
        self.theme_preference = theme or "System"
        self.current_theme = self._system_theme() if self.theme_preference == "System" else self.theme_preference
        colors = _theme_palette(self.current_theme)
        if getattr(self, "_auto_line_colors", True):
            self._set_default_line_colors_for_theme()
        self.setStyleSheet(_window_style(self.current_theme))
        if hasattr(self, "plot_canvas"):
            self.plot_canvas.setStyleSheet(
                f"QWidget#plotCanvas {{ background: {colors['plot_canvas']}; border: 1px solid {colors['border']}; }}"
            )
        if hasattr(self, "match_plot"):
            self.match_plot.setBackground(colors["plot_bg"])
            self.match_plot.setTitle(
                "IR/Raman Phase Finder: spectrum and candidate markers",
                color=colors["axis"],
                size="13pt",
            )
            self.match_plot.setLabel("bottom", "Wavenumber", units="cm-1", color=colors["axis"], **{"font-size": "12pt"})
            self.match_plot.setLabel("left", "Intensity", units="a.u.", color=colors["axis"], **{"font-size": "12pt"})
            self.match_plot.getAxis("bottom").enableAutoSIPrefix(False)
            self.match_plot.getAxis("left").enableAutoSIPrefix(False)
            for axis_name in ("bottom", "left", "top", "right"):
                axis = self.match_plot.getAxis(axis_name)
                axis.setPen(colors["axis"])
                axis.setTextPen(colors["axis"])
        self._apply_card_theme()
        if self._preprocessing_panel is not None:
            self._preprocessing_panel.setStyleSheet(preprocessing_panel_style(self.current_theme == "Dark"))
        self._redraw_plot()

    def _apply_card_theme(self) -> None:
        if not hasattr(self, "card_labels"):
            return
        colors = _theme_palette(self.current_theme)
        if hasattr(self, "card_title"):
            self.card_title.setStyleSheet(self._section_style())
        for key, label in self.card_labels.items():
            label.setStyleSheet(f"background: {colors['field_value']}; color: {colors['text']}; padding: 4px 6px;")
        for label in self.findChildren(QLabel):
            if label.property("fieldNameLabel"):
                label.setStyleSheet(
                    f"background: {colors['field_name']}; border-left: 3px solid #e9328f; "
                    "color: #d4dde7; font-weight: 700; padding: 4px 7px;"
                )

    def _plot_observed_color(self) -> str:
        if hasattr(self, "plot_view_settings"):
            text = getattr(self.plot_view_settings, "observed_color", "").strip()
            if text:
                return text
        if hasattr(self, "observed_color_input"):
            text = self.observed_color_input.text().strip()
            if text:
                return text
        return "#f8fafc" if self.current_theme == "Dark" else "#202124"

    def _plot_reference_color(self) -> str:
        if hasattr(self, "plot_view_settings"):
            text = getattr(self.plot_view_settings, "reference_color", "").strip()
            if text:
                return text
        if hasattr(self, "reference_color_input"):
            text = self.reference_color_input.text().strip()
            if text:
                return text
        return "#8ab4f8" if self.current_theme == "Dark" else "#1a73e8"

    def _set_default_line_colors_for_theme(self) -> None:
        if not hasattr(self, "observed_color_input") or not hasattr(self, "reference_color_input"):
            return
        if self.current_theme == "Dark":
            self.observed_color_input.setText("#f8fafc")
            self.reference_color_input.setText("#8ab4f8")
        else:
            self.observed_color_input.setText("#202124")
            self.reference_color_input.setText("#1a73e8")

    def _line_color_edited(self) -> None:
        self._auto_line_colors = False

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._close_preprocessing_panel(restore=True)
        self._save_ui_state()
        super().closeEvent(event)

    def _settings_bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _save_header_state(self, key: str, table: QTableWidget | None) -> None:
        if table is not None:
            self.settings.setValue(key, table.horizontalHeader().saveState())

    def _restore_header_state(self, key: str, table: QTableWidget | None) -> None:
        if table is None:
            return
        state = self.settings.value(key)
        if state:
            table.horizontalHeader().restoreState(state)
        header = table.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)

    def _table_header_settings(self) -> list[tuple[str, QTableWidget | None]]:
        profile_table = None
        if self.plot_settings_panel is not None:
            profile_table = getattr(self.plot_settings_panel, "profile_candidate_table", None)
        return [
            ("headers/candidates", getattr(self, "candidate_table", None)),
            ("headers/selected", getattr(self, "selected_table", None)),
            ("headers/databases", getattr(self, "database_table", None)),
            ("headers/bands", getattr(self, "band_table", None)),
            ("headers/sample_bands", getattr(self, "sample_band_table", None)),
            ("headers/profile_candidates", profile_table),
        ]

    def _connect_table_header_persistence(self) -> None:
        if self._header_persistence_connected:
            return
        for _key, table in self._table_header_settings():
            if table is not None:
                table.horizontalHeader().sectionResized.connect(self._queue_table_header_save)
        self._header_persistence_connected = True

    def _queue_table_header_save(self, _section: int, _old_size: int, _new_size: int) -> None:
        self._header_save_timer.start()

    def _flush_table_header_states(self) -> None:
        for key, table in self._table_header_settings():
            self._save_header_state(key, table)
        self.settings.sync()

    def _save_ui_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("splitters/main", self.main_splitter.saveState())
        self.settings.setValue("splitters/center", self.center_splitter.saveState())
        if hasattr(self, "elements_splitter"):
            self.settings.setValue("splitters/elements", self.elements_splitter.saveState())
        self.settings.setValue("tabs/right_index", self.right_tabs.currentIndex())
        self.settings.setValue("controls/display_mode", self.action_bar.display_mode.currentText())
        self.settings.setValue("controls/reference_origin", self.reference_origin_combo.currentData())
        if self.plot_settings_panel is not None:
            self.settings.setValue("controls/reference_view", self.plot_settings_panel.reference_view_combo.currentData())
        self.settings.setValue("controls/normalization", self._normalization_mode())
        self.settings.setValue("controls/x_axis_unit", self._x_axis_unit())
        self.settings.setValue("controls/laser_nm", self.action_bar.laser_wavelength_spin.value())
        self.settings.setValue("controls/multi_offset", self.action_bar.multi_offset_slider.value())
        self.settings.setValue("controls/panels_pinned", self.pin_panels_button.isChecked())
        self.settings.setValue("controls/include_raman", self.include_raman_checkbox.isChecked())
        self.settings.setValue("controls/include_ftir", self.include_ftir_checkbox.isChecked())
        self.settings.setValue("theme/preference", self.theme_preference)
        for label, checkbox in getattr(self, "source_checks", {}).items():
            self.settings.setValue(f"sources/{label}", checkbox.isChecked())
        for key, table in self._table_header_settings():
            self._save_header_state(key, table)
        self.settings.sync()

    def _splitters(self) -> list[QSplitter]:
        splitters = [self.main_splitter, self.center_splitter]
        if hasattr(self, "elements_splitter"):
            splitters.append(self.elements_splitter)
        return splitters

    def _set_panels_pinned(self, pinned: bool) -> None:
        handle_width = self._default_splitter_handle_width
        for splitter in self._splitters():
            splitter.setHandleWidth(handle_width)
            for index in range(splitter.count()):
                splitter.setCollapsible(index, False)
            if pinned:
                self._pinned_splitter_sizes[id(splitter)] = splitter.sizes()
                self._connect_pinned_splitter(splitter)
            else:
                self._pinned_splitter_sizes.pop(id(splitter), None)
        if hasattr(self, "pin_panels_button"):
            self.pin_panels_button.setText("Pinned" if pinned else "Pin")
        self.settings.setValue("controls/panels_pinned", bool(pinned))
        self.settings.sync()
        self.statusBar().showMessage(
            "Panel positions are locked." if pinned else "Panel positions are unlocked.",
            5000,
        )

    def _connect_pinned_splitter(self, splitter: QSplitter) -> None:
        key = id(splitter)
        if key in self._pinned_splitter_connections:
            return
        splitter.splitterMoved.connect(lambda _pos, _index, locked_splitter=splitter: self._restore_pinned_splitter(locked_splitter))
        self._pinned_splitter_connections.add(key)

    def _restore_pinned_splitter(self, splitter: QSplitter) -> None:
        if self._restoring_pinned_splitter:
            return
        if not hasattr(self, "pin_panels_button") or not self.pin_panels_button.isChecked():
            return
        sizes = self._pinned_splitter_sizes.get(id(splitter))
        if not sizes:
            return
        self._restoring_pinned_splitter = True
        try:
            splitter.setSizes(sizes)
        finally:
            self._restoring_pinned_splitter = False

    def _show_about_dialog(self) -> None:
        AboutDialog(self).exec()

    def _restore_ui_state(self) -> None:
        geometry = self.settings.value("window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        window_state = self.settings.value("window/state")
        if window_state:
            self.restoreState(window_state)
        main_state = self.settings.value("splitters/main")
        if main_state:
            self.main_splitter.restoreState(main_state)
        center_state = self.settings.value("splitters/center")
        if center_state:
            self.center_splitter.restoreState(center_state)
        elements_state = self.settings.value("splitters/elements")
        if elements_state and hasattr(self, "elements_splitter"):
            self.elements_splitter.restoreState(elements_state)
        self.pin_panels_button.setChecked(self._settings_bool("controls/panels_pinned", False))
        right_index = int(self.settings.value("tabs/right_index", self.right_tabs.currentIndex()) or 0)
        if 0 <= right_index < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(right_index)
        theme = str(self.settings.value("theme/preference", self.theme_preference, type=str) or self.theme_preference)
        if theme != self.theme_preference:
            self._apply_theme(theme)
        display_mode = str(self.settings.value("controls/display_mode", self.action_bar.display_mode.currentText(), type=str) or "")
        if display_mode:
            self.action_bar.display_mode.setCurrentText(display_mode)
        reference_origin = str(self.settings.value("controls/reference_origin", "both", type=str) or "both")
        origin_index = self.reference_origin_combo.findData(reference_origin)
        blocked = self.reference_origin_combo.blockSignals(True)
        self.reference_origin_combo.setCurrentIndex(max(0, origin_index))
        self.reference_origin_combo.blockSignals(blocked)
        reference_view = str(self.settings.value("controls/reference_view", "profiles", type=str) or "profiles")
        if self.plot_settings_panel is not None:
            view_index = self.plot_settings_panel.reference_view_combo.findData(reference_view)
            blocked = self.plot_settings_panel.reference_view_combo.blockSignals(True)
            self.plot_settings_panel.reference_view_combo.setCurrentIndex(max(0, view_index))
            self.plot_settings_panel.reference_view_combo.blockSignals(blocked)
        blocked = self.action_bar.laser_wavelength_spin.blockSignals(True)
        self.action_bar.laser_wavelength_spin.setValue(float(self.settings.value("controls/laser_nm", 532.0) or 532.0))
        self.action_bar.laser_wavelength_spin.blockSignals(blocked)
        offset_value = int(self.settings.value("controls/multi_offset", 10) or 0)
        blocked = self.action_bar.multi_offset_slider.blockSignals(True)
        self.action_bar.multi_offset_slider.setValue(max(0, min(offset_value, 100)))
        self.action_bar.multi_offset_slider.blockSignals(blocked)
        self.action_bar.multi_offset_value.setText(f"{self.action_bar.multi_offset_slider.value()}%")
        self._on_display_mode_changed(self.action_bar.display_mode.currentText())
        normalization = str(self.settings.value("controls/normalization", "", type=str) or "")
        if not normalization:
            normalization = "max" if self._settings_bool("controls/normalize", True) else "none"
        normalization_index = self.action_bar.normalization_combo.findData(normalization)
        self.action_bar.normalization_combo.setCurrentIndex(max(0, normalization_index))
        x_axis_unit = str(self.settings.value("controls/x_axis_unit", "cm-1", type=str) or "cm-1")
        if self.plot_settings_panel is not None:
            scale = self._unit_to_axis_scale(x_axis_unit)
            blocked = self.plot_settings_panel.bottom_scale_combo.blockSignals(True)
            self.plot_settings_panel._set_axis_scale_combo(self.plot_settings_panel.bottom_scale_combo, scale)
            self.plot_settings_panel.bottom_scale_combo.blockSignals(blocked)
            self.plot_view_settings = self.plot_settings_panel.settings()
        self.include_raman_checkbox.setChecked(self._settings_bool("controls/include_raman", True))
        self.include_ftir_checkbox.setChecked(self._settings_bool("controls/include_ftir", True))
        for label, checkbox in getattr(self, "source_checks", {}).items():
            checkbox.setChecked(self._settings_bool(f"sources/{label}", checkbox.isChecked()))
        for key, table in self._table_header_settings():
            self._restore_header_state(key, table)
        self._connect_table_header_persistence()
        self._redraw_plot()

    def _normalization_mode(self) -> str:
        if not hasattr(self, "action_bar"):
            return "none"
        return str(self.action_bar.normalization_combo.currentData() or "none")

    def _unit_to_axis_scale(self, unit: str) -> str:
        normalized = str(unit or "").strip().lower()
        if normalized in {"nm", "wavelength", "nanometer", "nanometers"}:
            return "nm"
        if normalized in {"ev", "energy"}:
            return "eV"
        return "wavenumber"

    def _axis_scale_to_unit(self, scale: str) -> str:
        normalized = self._unit_to_axis_scale(scale)
        if normalized == "nm":
            return "nm"
        if normalized == "eV":
            return "eV"
        return "cm-1"

    def _bottom_axis_scale(self) -> str:
        return self._unit_to_axis_scale(getattr(self.plot_view_settings, "bottom_axis_scale", "wavenumber"))

    def _top_axis_scale(self) -> str:
        return self._unit_to_axis_scale(getattr(self.plot_view_settings, "top_axis_scale", "wavenumber"))

    def _x_axis_unit(self) -> str:
        return self._axis_scale_to_unit(self._bottom_axis_scale())

    def _display_x_to_wavenumber(self, values, kind: SignalKind, scale: str) -> np.ndarray:
        display_values = np.asarray(values, dtype=float)
        normalized = self._unit_to_axis_scale(scale)
        if normalized == "eV":
            return display_values * WAVENUMBERS_PER_EV
        if normalized == "nm":
            result = np.full_like(display_values, np.nan, dtype=float)
            valid = np.isfinite(display_values) & (display_values > 0.0)
            if kind == SignalKind.RAMAN:
                laser_nm = self._selected_laser_wavelength_nm()
                if not np.isfinite(laser_nm) or laser_nm <= 0.0:
                    return result
                laser_wavenumber = 1.0e7 / laser_nm
                result[valid] = laser_wavenumber - (1.0e7 / display_values[valid])
            else:
                result[valid] = 1.0e7 / display_values[valid]
            return result
        return display_values

    def _wavenumber_to_axis_display(self, values, kind: SignalKind, scale: str) -> np.ndarray:
        normalized = self._unit_to_axis_scale(scale)
        if normalized == "nm":
            return spectral_x_to_nm(values, kind, self._selected_laser_wavelength_nm())
        if normalized == "eV":
            return wavenumber_to_energy_ev(values)
        return np.asarray(values, dtype=float)

    def _convert_display_x(self, values, kind: SignalKind) -> np.ndarray:
        return self._wavenumber_to_axis_display(values, kind, self._bottom_axis_scale())

    def _axis_tick_text(self, value: float, scale: str, spacing: float) -> str:
        if not np.isfinite(value):
            return ""
        if scale == "eV":
            return f"{value:.4g}"
        if scale == "nm":
            return f"{value:.0f}"
        if abs(value) >= 1000.0 or abs(spacing) >= 10.0:
            return f"{value:.0f}"
        return f"{value:.4g}"

    def _top_axis_tick_strings(self, values, scale, spacing) -> list[str]:
        kind = self.active_spectrum.kind if self.active_spectrum is not None else SignalKind.UNKNOWN
        bottom_scale = self._bottom_axis_scale()
        top_scale = self._top_axis_scale()
        wavenumbers = self._display_x_to_wavenumber(values, kind, bottom_scale)
        top_values = self._wavenumber_to_axis_display(wavenumbers, kind, top_scale)
        return [self._axis_tick_text(float(value), top_scale, float(spacing)) for value in top_values]

    def _bottom_axis_tick_strings(self, values, scale, spacing) -> list[str]:
        bottom_scale = self._bottom_axis_scale()
        return [self._axis_tick_text(float(value), bottom_scale, float(spacing)) for value in values]

    def _configure_axis_tick_formatters(self) -> None:
        if not hasattr(self, "match_plot"):
            return
        bottom_axis = self.match_plot.getAxis("bottom")
        bottom_axis.tickStrings = self._bottom_axis_tick_strings
        top_axis = self.match_plot.getAxis("top")
        top_axis.tickStrings = self._top_axis_tick_strings

    def _on_x_axis_unit_changed(self, unit: str) -> None:
        if unit == "nm" and self._selected_laser_wavelength_nm() <= 0.0:
            has_raman = any(spectrum.kind == SignalKind.RAMAN for spectrum in self._observed_spectra_to_display())
            if has_raman:
                self.statusBar().showMessage("Select a Raman laser wavelength before displaying scattered wavelength in nm.", 8000)
                if self.plot_settings_panel is not None:
                    blocked = self.plot_settings_panel.bottom_scale_combo.blockSignals(True)
                    self.plot_settings_panel._set_axis_scale_combo(self.plot_settings_panel.bottom_scale_combo, "wavenumber")
                    self.plot_settings_panel.bottom_scale_combo.blockSignals(blocked)
                unit = "cm-1"
        self.plot_view_settings = replace(
            self.plot_view_settings,
            x_display_unit=unit,
            bottom_axis_scale=self._unit_to_axis_scale(unit),
        )
        self._apply_x_axis_label()
        self._redraw_plot()
        self._reset_plot_view()

    def _on_laser_wavelength_changed(self, _value: float) -> None:
        self._search_active_spectrum()
        if self._bottom_axis_scale() == "nm" or self._top_axis_scale() == "nm":
            self._redraw_plot()
            self._reset_plot_view()

    def _apply_x_axis_label(self) -> None:
        if not hasattr(self, "match_plot"):
            return
        settings = self.plot_view_settings
        for axis_name, visible, label_visible, label, unit in (
            (
                "bottom",
                settings.bottom_axis_visible,
                settings.bottom_axis_label_visible,
                settings.bottom_axis_label,
                settings.bottom_axis_unit,
            ),
            (
                "top",
                settings.top_axis_visible,
                settings.top_axis_label_visible,
                settings.top_axis_label,
                settings.top_axis_unit,
            ),
            (
                "left",
                settings.left_axis_visible,
                settings.left_axis_label_visible,
                settings.left_axis_label,
                settings.left_axis_unit,
            ),
            (
                "right",
                settings.right_axis_visible,
                settings.right_axis_label_visible,
                settings.right_axis_label,
                settings.right_axis_unit,
            ),
        ):
            label, unit = self._display_axis_label(axis_name, label, unit)
            self.match_plot.setLabel(
                axis_name,
                self._axis_label(label, unit) if visible and label_visible else "",
                color=settings.axis_color,
                **{"font-size": f"{settings.label_font_size}pt"},
            )
        self._configure_axis_tick_formatters()

    def _display_axis_label(self, axis_name: str, label: str, unit: str) -> tuple[str, str]:
        if axis_name not in {"left", "right"} or self._normalization_mode() == "none":
            return label, unit
        stripped = label.strip() or "Intensity"
        if "norm" in stripped.lower():
            return stripped, unit
        if stripped.lower() == "intensity":
            return "Normalized intensity", unit
        return f"{stripped} (normalized)", unit

    def _matching_options(self) -> MatchingOptions:
        return MatchingOptions(preprocessing=PreprocessingOptions(normalize=self._normalization_mode()))

    def _display_trace_xy(self, trace) -> tuple[list[float], list[float]]:
        if self._normalization_mode() == "none":
            x_values, y_values = list(trace.x), list(trace.y)
        else:
            processed = preprocess_spectrum(trace, PreprocessingOptions(normalize=self._normalization_mode()))
            x_values, y_values = list(processed.x), list(processed.y)
        return self._convert_display_x(x_values, trace.kind).tolist(), y_values

    def _on_normalization_changed(self, _checked: bool) -> None:
        if self.active_spectrum is not None and self.results:
            current_row = self.candidate_table.currentRow()
            candidates = [result.candidate for result in self.results]
            self.results = rank_candidates(self.active_spectrum, candidates, self._matching_options())
            self.candidate_table.set_results(self.results)
            row = current_row if 0 <= current_row < len(self.results) else 0
            if self.results:
                self.candidate_table.setCurrentCell(row, 0)
                self._preview_result(self.results[row])
            self._update_profile_view_context()
            self._save_active_spectrum_profile_state()
            return
        self._redraw_plot()
        if self._current_preview_reference is not None and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            x, y = self._display_trace_xy(self._current_preview_reference)
            self.match_plot.plot(
                x,
                self._shift_y(y, self._active_display_offset),
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=self._current_preview_reference.name,
            )

    def _reset_plot_view(self) -> None:
        self._set_plot_range_for_traces(self._experimental_range_traces())

    def _plot_view_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        view_range = self.match_plot.plotItem.vb.viewRange()
        return (tuple(view_range[0]), tuple(view_range[1]))

    def _restore_plot_view_range(self, view_range: tuple[tuple[float, float], tuple[float, float]] | None) -> None:
        if view_range is None:
            return
        (xmin, xmax), (ymin, ymax) = view_range
        self.match_plot.setXRange(float(xmin), float(xmax), padding=0.0)
        self.match_plot.setYRange(float(ymin), float(ymax), padding=0.0)

    def _show_full_plot_range(self) -> None:
        traces = self._experimental_range_traces()
        if self._current_preview_reference is not None and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            traces.append(self._current_preview_reference)
        self._set_plot_range_for_traces(traces)

    def _experimental_range_traces(self) -> list[ObservedSpectrum]:
        traces = self._observed_spectra_to_display()
        if traces:
            return traces
        return [self.active_spectrum] if self.active_spectrum is not None else []

    def _set_plot_range_for_traces(self, traces: list) -> None:
        valid_x: list[float] = []
        valid_y: list[float] = []
        observed_spectra = self._observed_spectra_to_display()
        offset_step = self._multi_offset_step(observed_spectra)
        observed_offsets = {
            self._spectrum_visibility_key(spectrum): float(index) * offset_step
            for index, spectrum in enumerate(observed_spectra)
        }
        for trace in traces:
            x_values, y_values = self._display_trace_xy(trace)
            x_array = np.asarray(x_values, dtype=float)
            y_array = np.asarray(y_values, dtype=float)
            if isinstance(trace, ObservedSpectrum):
                y_array = y_array + observed_offsets.get(self._spectrum_visibility_key(trace), 0.0)
            elif isinstance(trace, ReferenceSpectrum):
                y_array = y_array + self._active_display_offset
            mask = np.isfinite(x_array) & np.isfinite(y_array)
            if not np.any(mask):
                continue
            valid_x.extend(x_array[mask].tolist())
            valid_y.extend(y_array[mask].tolist())
        if not valid_x or not valid_y:
            self.match_plot.enableAutoRange()
            return
        x_min = float(min(valid_x))
        x_max = float(max(valid_x))
        y_min = float(min(valid_y))
        y_max = float(max(valid_y))
        if x_min == x_max:
            x_min -= 1.0
            x_max += 1.0
        if y_min == y_max:
            y_min -= 0.5
            y_max += 0.5
        if self._reference_view_shows_lines():
            lane_count = max(int(getattr(self, "_reference_line_lane_count", 0)), 1)
            y_min -= (y_max - y_min) * (0.08 + 0.065 * max(lane_count - 1, 0))
        x_pad = (x_max - x_min) * 0.02
        y_pad = (y_max - y_min) * 0.08
        self.match_plot.setXRange(x_min - x_pad, x_max + x_pad, padding=0.0)
        self.match_plot.setYRange(y_min - y_pad, y_max + y_pad, padding=0.0)


    def _update_cursor_readout(self, position) -> None:
        if self.match_plot.sceneBoundingRect().contains(position):
            point = self.match_plot.plotItem.vb.mapSceneToView(position)
            if self.cursor_position_line is not None:
                self.cursor_position_line.setPos(point.x())
                self.cursor_position_line.setVisible(bool(getattr(self.plot_view_settings, "cursor_vertical_line_visible", False)))
            unit = self._x_axis_unit()
            unit_label = "cm⁻¹" if unit == "cm-1" else unit
            self.cursor_label.setText(f"{unit_label}: {point.x():.4g}    I: {point.y():.4g}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = VibrationalFinderWindow()
    prepared_file = os.environ.get("IR_RAMAN_PHASE_FINDER_PREPARED_FILE")
    if prepared_file:
        try:
            Path(prepared_file).write_text("prepared", encoding="utf-8")
        except OSError:
            pass
    show_signal_file = os.environ.get("IR_RAMAN_PHASE_FINDER_SHOW_SIGNAL_FILE")
    if show_signal_file:
        signal_path = Path(show_signal_file)
        deadline = time.monotonic() + 180.0
        while not signal_path.exists() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
    window.show()
    app.processEvents()
    ready_file = os.environ.get("IR_RAMAN_PHASE_FINDER_READY_FILE")
    if ready_file:
        try:
            Path(ready_file).write_text("ready", encoding="utf-8")
        except OSError:
            pass
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
