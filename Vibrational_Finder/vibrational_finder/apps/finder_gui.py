from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import pyqtgraph as pg
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtCore import QSettings
from PySide6.QtCore import QTimer
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
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
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finder_core.data_sources import SourceQuery
from finder_core.chemistry import parse_formula_elements
from finder_core.models import CandidateRecord, MatchScore, SignalKind
from vibrational_finder.io import load_xy_spectrum, supported_spectrum_extensions
from vibrational_finder.matching import MatchingOptions, rank_candidates
from vibrational_finder.models import CompoundCandidate, ObservedSpectrum, ReferenceSpectrum, VibrationalMatchResult
from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum
from vibrational_finder.services import CifStructureSource, FolderLibrarySource, RruffSource, UserLibrarySource
from vibrational_finder.services.openspecy_source import OpenSpecyLibrarySource
from vibrational_finder.services.public_sources import external_source_by_key, external_source_catalog
from vibrational_finder.ui import PeriodicTableWidget, element_sort_key
from vibrational_finder.ui.background_task import BackgroundTaskHandle
from vibrational_finder.ui.plot_view_settings import PlotViewSettings, PlotViewSettingsWidget
from vibrational_finder.ui.vibrational_plot import create_vibrational_plot_widget


SPECTRUM_FILE_FILTER = (
    "Spectra (*.txt *.xy *.csv *.tsv *.dat *.asc *.ascii *.jdx *.dx *.spc *.spa *.0 *.1 *.2);;"
    "Text spectra (*.txt *.xy *.csv *.tsv *.dat *.asc *.ascii);;"
    "JCAMP-DX (*.jdx *.dx);;"
    "Binary vendor spectra (*.spc *.spa *.0 *.1 *.2);;"
    "All files (*)"
)


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
        self.search_input = QLineEdit()
        self.display_mode = QComboBox()
        self.normalize_checkbox = QCheckBox("Normalize")
        self.laser_wavelength_spin = QDoubleSpinBox()
        self.smooth_button = QPushButton("Smooth")
        self.remove_background_button = QPushButton("Remove background")
        self.reset_data_button = QPushButton("Reset data")
        self.search_button = QPushButton("Search active")
        self.reset_view_button = QPushButton("Reset view")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.smooth_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.remove_background_button.setStyleSheet(_glass_button_style("#8a5a16", "#c68a2e"))
        self.reset_data_button.setStyleSheet(_glass_button_style("#7b4fb3", "#a782d8"))
        self.search_button.setStyleSheet(_glass_button_style("#8a5a16", "#c68a2e"))
        self.reset_view_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))

        self.display_mode.addItems(["One", "All selected"])
        self.laser_wavelength_spin.setRange(0.0, 2000.0)
        self.laser_wavelength_spin.setDecimals(1)
        self.laser_wavelength_spin.setSingleStep(1.0)
        self.laser_wavelength_spin.setValue(532.0)
        self.laser_wavelength_spin.setSuffix(" nm")
        self.laser_wavelength_spin.setSpecialValueText("All lasers")
        self.laser_wavelength_spin.setToolTip("User laser wavelength for Raman references. Set 0 to show all.")
        self.laser_wavelength_spin.setKeyboardTracking(False)
        self.laser_wavelength_spin.setMinimumWidth(96)
        self.search_input.setPlaceholderText("Formula / compound name / entry id")

        layout.addWidget(self.smooth_button)
        layout.addWidget(self.remove_background_button)
        layout.addWidget(self.reset_data_button)
        layout.addWidget(QLabel("Show"))
        layout.addWidget(self.display_mode)
        layout.addWidget(self.normalize_checkbox)
        layout.addWidget(QLabel("Laser"))
        layout.addWidget(self.laser_wavelength_spin)
        layout.addStretch(1)
        layout.addWidget(self.search_input, 1)
        layout.addWidget(self.search_button)
        layout.addWidget(self.reset_view_button)


class ProjectControlsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.new_button = QPushButton("New project")
        self.load_button = QPushButton("Load project")
        self.save_button = QPushButton("Save project")
        self.import_raman_button = QPushButton("Import Raman")
        self.import_ftir_button = QPushButton("Import FTIR")
        self.load_library_button = QPushButton("Load CSV library")
        self.load_folder_button = QPushButton("Load folder")
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
        self.import_raman_button.setMinimumHeight(34)
        self.import_ftir_button.setMinimumHeight(34)
        self.load_library_button.setMinimumHeight(34)
        self.load_folder_button.setMinimumHeight(34)
        self.new_button.setStyleSheet(_glass_button_style("#5f6368", "#8a8d91"))
        self.load_button.setStyleSheet(_glass_button_style("#0b8043", "#35a96c"))
        self.save_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.import_raman_button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
        self.import_ftir_button.setStyleSheet(_glass_button_style("#0b8043", "#35a96c"))
        self.load_library_button.setStyleSheet(_glass_button_style("#e9328f", "#ff65b3"))
        self.load_folder_button.setStyleSheet(_glass_button_style("#7b4fb3", "#a782d8"))

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
        layout.addWidget(self.import_raman_button)
        layout.addWidget(self.import_ftir_button)
        layout.addWidget(self.load_library_button)
        layout.addWidget(self.load_folder_button)
        layout.addLayout(order_row)


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
        self.resizeColumnsToContents()
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for column in (4, 5, 6, 7, 8, 9):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(4, 72)
        self.setColumnWidth(5, 104)
        self.setColumnWidth(6, 108)
        self.setColumnWidth(7, 82)
        self.setColumnWidth(8, 82)
        self.setColumnWidth(9, 72)


class SelectedCompoundsTableWidget(QTableWidget):
    HEADERS = ["Color", "Compound", "Method", "Bands", "Match (%)"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(self.HEADERS), parent)
        self.setToolTip("Selected compounds")
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.setMinimumHeight(150)
        self._resize_columns()

    def set_selected(self, results: list[VibrationalMatchResult]) -> None:
        self.setRowCount(len(results))
        for row, result in enumerate(results):
            values = [
                "#1a73e8",
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
                self.setItem(row, column, item)

    def _resize_columns(self) -> None:
        self.resizeColumnsToContents()
        header = self.horizontalHeader()
        for column in range(self.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 82)
        self.setColumnWidth(2, 76)
        self.setColumnWidth(3, 82)
        self.setColumnWidth(4, 82)


class VibrationalFinderWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("IR/Raman Phase Finder")
        self.resize(1500, 850)
        self.settings = QSettings("IRRamanPhaseFinder", "Standalone")
        self.setAcceptDrops(True)
        self.theme_preference = "System"
        self.current_theme = self._system_theme()
        self.plot_settings_panel: PlotViewSettingsWidget | None = None
        self.plot_view_settings = PlotViewSettings()
        self.legend_item = None
        self.cursor_position_line = None
        self._auto_line_colors = True
        self.setStyleSheet(_window_style(self.current_theme))

        self.active_spectrum: ObservedSpectrum | None = None
        self.raman_spectra: list[ObservedSpectrum] = []
        self.ftir_spectra: list[ObservedSpectrum] = []
        self.reference_records: list[CandidateRecord] = []
        self.reference_spectra: list[ReferenceSpectrum] = []
        self._current_preview_reference: ReferenceSpectrum | None = None
        self.user_libraries: list[UserLibrarySource | FolderLibrarySource | CifStructureSource] = []
        self.rruff_source = RruffSource()
        self.openspecy_source = OpenSpecyLibrarySource()
        self.results: list[VibrationalMatchResult] = []
        self.browse_records: list[CandidateRecord] = []
        self.selected_results: list[VibrationalMatchResult] = []
        self.element_states: dict[str, str] = {}
        self.required_elements: set[str] = set()
        self.optional_elements: set[str] = set()
        self.excluded_elements: set[str] = set()
        self.selected_element_order: list[str] = []
        self.exclude_all_other_elements = True
        self._background_tasks: list[BackgroundTaskHandle] = []
        self._original_observed: dict[str, ObservedSpectrum] = {}

        self._create_sidebar()
        self._create_center()
        self._create_right_tabs()
        self._create_main_splitter()
        QApplication.styleHints().colorSchemeChanged.connect(lambda _scheme: self._apply_theme("System") if self.theme_preference == "System" else None)
        self._apply_theme(self.theme_preference)
        QTimer.singleShot(0, self._restore_ui_state)

    def _create_sidebar(self) -> None:
        self.sidebar = QWidget()
        self.sidebar.setMinimumWidth(170)
        self.sidebar.setMaximumWidth(360)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)

        self.project_controls = ProjectControlsWidget()
        self.project_controls.import_raman_button.clicked.connect(lambda: self._import_experiment(SignalKind.RAMAN))
        self.project_controls.import_ftir_button.clicked.connect(lambda: self._import_experiment(SignalKind.FTIR))
        self.project_controls.load_library_button.clicked.connect(self._load_user_library)
        self.project_controls.load_folder_button.clicked.connect(self._load_library_folder)
        self.project_controls.new_button.clicked.connect(self._new_project)
        self.project_controls.load_button.clicked.connect(self._not_implemented_project_files)
        self.project_controls.save_button.clicked.connect(self._not_implemented_project_files)
        sidebar_layout.addWidget(self.project_controls)

        self.project_tree = QTreeWidget()
        self.project_tree.setHeaderLabel("Data")
        self.project_tree.setToolTip(
            "Project tree\n"
            "Select a Raman or FTIR spectrum to make it active.\n"
            "Select a reference spectrum to preview it."
        )
        self.project_tree.itemSelectionChanged.connect(self._on_project_tree_selection_changed)
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
        self.action_bar.reset_data_button.clicked.connect(self._reset_active_spectrum_data)
        self.action_bar.search_button.clicked.connect(self._search_active_spectrum)
        self.action_bar.search_input.returnPressed.connect(self._search_active_spectrum)
        self.action_bar.reset_view_button.clicked.connect(self._reset_plot_view)
        self.action_bar.normalize_checkbox.setChecked(True)
        self.action_bar.normalize_checkbox.toggled.connect(self._on_normalization_changed)
        self.action_bar.laser_wavelength_spin.valueChanged.connect(lambda _value: self._search_active_spectrum())
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
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(460)
        self.right_tabs.addTab(self._elements_tab(), "Elements")
        self.right_tabs.addTab(self._compound_card_tab(), "Card")
        self.right_tabs.addTab(self._database_tab(), "Databases")
        self.right_tabs.addTab(self._plot_view_tab(), "View")

    def _create_main_splitter(self) -> None:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.center)
        self.main_splitter.addWidget(self.right_tabs)
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
        controls_layout.addWidget(self.element_gate_label)

        method_row = QHBoxLayout()
        method_row.setContentsMargins(0, 0, 0, 0)
        self.include_raman_checkbox = QCheckBox("Raman references")
        self.include_ftir_checkbox = QCheckBox("FTIR references")
        self.include_raman_checkbox.setChecked(True)
        self.include_ftir_checkbox.setChecked(True)
        method_row.addWidget(self.include_raman_checkbox)
        method_row.addWidget(self.include_ftir_checkbox)
        method_row.addStretch(1)
        controls_layout.addLayout(method_row)

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        card_layout = QVBoxLayout(content)
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

        card_layout.addWidget(self._section_title("Detected bands"))
        self.band_table = self._card_table(["Observed cm-1", "Reference cm-1", "Delta", "Intensity"])
        self.band_table.setMinimumHeight(220)
        card_layout.addWidget(self.band_table)
        return outer

    def _database_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.database_table = QTableWidget(0, 3)
        self.database_table.setHorizontalHeaderLabels(["Database", "Status", "Details"])
        self.database_table.verticalHeader().setVisible(False)
        self.database_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.database_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.database_table.setAlternatingRowColors(True)
        self.database_table.setMinimumHeight(220)
        self.database_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.database_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.database_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
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
            "SDBS",
            "OpenSpecy",
            "SpectraBase",
            "NIST",
            "JARVIS-DFT",
            "Materials Project",
            "PhononDB",
            "NOMAD",
        ]
        for index, label in enumerate(source_labels):
            checkbox = QCheckBox(label)
            enabled = label in {"User Library", "RRUFF"} or (label == "OpenSpecy" and bool(self.openspecy_source.search(SourceQuery())))
            checkbox.setChecked(label in {"User Library", "RRUFF"} or (label == "OpenSpecy" and enabled))
            checkbox.setEnabled(enabled)
            self.source_checks[label] = checkbox
            source_layout.addWidget(checkbox, index // 2, index % 2)
        layout.addWidget(source_box)

        layout.addWidget(self._section_title("Database management"))
        layout.addWidget(
            self._management_row(
                "User reference library",
                [
                    ("Load CSV", self._load_user_library),
                    ("Load folder", self._load_library_folder),
                    ("Load DFT", self._load_dft_library_folder),
                    ("Load CIF", self._load_cif_library_folder),
                    ("Clear", self._clear_user_libraries),
                ],
            )
        )
        self.rruff_archive_combo = QComboBox()
        for archive in self.rruff_source.available_archives():
            cache_text = "cached" if archive.is_cached else "not cached"
            self.rruff_archive_combo.addItem(f"{archive.label} ({cache_text})", archive.key)
        self._set_rruff_archive_combo_key("excellent_unoriented")
        layout.addWidget(self._rruff_archive_row())
        layout.addWidget(self._management_row("RRUFF downloadable ZIP database", [("Download / update", self._update_rruff), ("Clear cache", self._clear_rruff)]))
        self.openspecy_library_combo = QComboBox()
        for library in self.openspecy_source.available_libraries():
            cache_text = "cached" if library.is_cached else "not cached"
            self.openspecy_library_combo.addItem(f"{library.label} ({cache_text})", library.key)
        self._set_openspecy_library_combo_key("medoid_derivative")
        layout.addWidget(self._openspecy_library_row())
        layout.addWidget(self._management_row("OpenSpecy downloadable RDS library", [("Download / update", self._update_openspecy), ("Clear cache", self._clear_openspecy)]))
        layout.addWidget(
            self._management_row(
                "Synthetic spectra web sources",
                [
                    ("Open SDBS", lambda: self._open_external_source("SDBS")),
                    ("Open NIST", lambda: self._open_external_source("NIST")),
                    ("Open OpenSpecy", lambda: self._open_external_source("OpenSpecy")),
                    ("Open SpectraBase", lambda: self._open_external_source("SpectraBase")),
                ],
            )
        )
        layout.addWidget(
            self._management_row(
                "Computed materials web sources",
                [
                    ("Open JARVIS", lambda: self._open_external_source("JARVIS-DFT")),
                    ("Open MP", lambda: self._open_external_source("Materials Project")),
                    ("Open PhononDB", lambda: self._open_external_source("PhononDB")),
                    ("Open NOMAD", lambda: self._open_external_source("NOMAD")),
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
                tickLength=-abs(int(settings.tick_length)) if visible else 0,
            )
            label, unit, label_visible = axis_labels[axis_name]
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
            return
        if self.legend_item is not None:
            self.legend_item.setVisible(False)

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
        self.active_spectrum = None
        self.raman_spectra.clear()
        self.ftir_spectra.clear()
        self.reference_records.clear()
        self.reference_spectra.clear()
        self.user_libraries.clear()
        self._original_observed.clear()
        self.rruff_source.refresh_index()
        self.openspecy_source.refresh_index()
        self.results.clear()
        self.browse_records.clear()
        self.selected_results.clear()
        self.element_states.clear()
        self.required_elements.clear()
        self.optional_elements.clear()
        self.excluded_elements.clear()
        self.selected_element_order.clear()
        self.exclude_all_other_elements = True
        self.candidate_table.set_results([])
        self.selected_table.set_selected([])
        self._refresh_element_table()
        self._set_card(None)
        self._update_database_table()
        self._refresh_project_tree()
        self._redraw_plot()

    def _not_implemented_project_files(self) -> None:
        QMessageBox.information(self, "Project files", "Project save/load will be ported from XRD Finder in the next step.")

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

    def _import_experiment(self, kind: SignalKind) -> None:
        title = "Import Raman spectrum" if kind == SignalKind.RAMAN else "Import FTIR spectrum"
        path, _ = QFileDialog.getOpenFileName(self, title, "", SPECTRUM_FILE_FILTER)
        if path:
            self._load_experiment_path(path, kind)

    def _load_experiment_path(self, path: str, kind: SignalKind) -> None:
        spectrum = load_xy_spectrum(path, kind=kind, name=Path(path).stem)
        if not isinstance(spectrum, ObservedSpectrum):
            spectrum = ObservedSpectrum(**spectrum.__dict__)
        self.active_spectrum = spectrum
        self._original_observed[spectrum.source_path] = replace(spectrum)
        if kind == SignalKind.RAMAN:
            self.raman_spectra.append(spectrum)
        else:
            self.ftir_spectra.append(spectrum)
        self._refresh_project_tree()
        self._redraw_plot()

    def _smooth_active_spectrum(self) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        smoothed = preprocess_spectrum(
            self.active_spectrum,
            PreprocessingOptions(smoothing_window=9, normalize="none"),
        )
        self._replace_active_spectrum(ObservedSpectrum(**smoothed.__dict__))
        self.statusBar().showMessage("Smoothed active spectrum.", 5000)

    def _remove_background_active_spectrum(self) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        corrected = preprocess_spectrum(
            self.active_spectrum,
            PreprocessingOptions(baseline_order=3, normalize="none"),
        )
        self._replace_active_spectrum(ObservedSpectrum(**corrected.__dict__))
        self.statusBar().showMessage("Removed polynomial background from active spectrum.", 5000)

    def _reset_active_spectrum_data(self) -> None:
        if self.active_spectrum is None:
            QMessageBox.warning(self, "No experiment", "Import a Raman or FTIR spectrum first.")
            return
        original = self._original_observed.get(self.active_spectrum.source_path)
        if original is None:
            QMessageBox.information(self, "Reset data", "Original spectrum is not available for this item.")
            return
        self._replace_active_spectrum(replace(original))
        self.statusBar().showMessage("Reset active spectrum to imported data.", 5000)

    def _replace_active_spectrum(self, spectrum: ObservedSpectrum) -> None:
        if self.active_spectrum is None:
            return
        old_path = self.active_spectrum.source_path
        target_list = self.raman_spectra if self.active_spectrum.kind == SignalKind.RAMAN else self.ftir_spectra
        for index, item in enumerate(target_list):
            if item.source_path == old_path:
                target_list[index] = spectrum
                break
        self.active_spectrum = spectrum
        self.results = []
        self.candidate_table.set_results([])
        self._set_card(None)
        self._current_preview_reference = None
        self._refresh_project_tree()
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

    def _add_user_library_source(self, source: UserLibrarySource | FolderLibrarySource | CifStructureSource) -> None:
        self.user_libraries.append(source)
        for record in source.search(SourceQuery()):
            reference = source.load_spectrum(record)
            self.reference_records.append(record)
            self.reference_spectra.append(reference)
        self._update_database_table()
        self._refresh_project_tree()

    def _search_active_spectrum(self) -> None:
        if self.active_spectrum is None:
            self._browse_reference_sources()
            return
        use_user_library = self.source_checks.get("User Library").isChecked() if hasattr(self, "source_checks") and "User Library" in self.source_checks else True
        use_rruff = self.source_checks.get("RRUFF").isChecked() if hasattr(self, "source_checks") and "RRUFF" in self.source_checks else False
        use_openspecy = self.source_checks.get("OpenSpecy").isChecked() if hasattr(self, "source_checks") and "OpenSpecy" in self.source_checks else False
        if not self.user_libraries and not (use_rruff and self.rruff_source.search(SourceQuery(kind=self.active_spectrum.kind))) and not (use_openspecy and self.openspecy_source.search(SourceQuery(kind=self.active_spectrum.kind))):
            QMessageBox.warning(self, "No reference source", "Load a user library or update RRUFF first.")
            return
        text = self.action_bar.search_input.text().strip()
        formula = self._element_formula_query()
        candidates: list[CompoundCandidate] = []
        if use_user_library:
            for source in self.user_libraries:
                candidates.extend(source.load_candidates(SourceQuery(text=text, kind=self.active_spectrum.kind, formula=formula)))
        if use_rruff:
            candidates.extend(self.rruff_source.load_candidates(SourceQuery(text=text, kind=self.active_spectrum.kind, formula=formula)))
        if use_openspecy:
            candidates.extend(candidate for candidate in self.openspecy_source.load_candidates(SourceQuery(text=text, kind=self.active_spectrum.kind, formula=formula)) if candidate.reference is not None)
        candidates = [candidate for candidate in candidates if self._record_passes_element_gate(candidate)]
        self.results = rank_candidates(self.active_spectrum, candidates, self._matching_options())
        self.browse_records = []
        self.candidate_table.set_results(self.results)
        self._update_profile_view_context()
        self._preview_result(self.results[0] if self.results else None)
        if self.results:
            self.statusBar().showMessage(f"Found {len(self.results)} candidates. Top match: {self.results[0].candidate.name}", 7000)
        else:
            self.statusBar().showMessage(
                "No candidates matched. Load a reference folder/CSV or relax element/source filters.",
                9000,
            )

    def _browse_reference_sources(self) -> None:
        text = self.action_bar.search_input.text().strip()
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
        if self.browse_records:
            self._preview_browse_record(0)
            self.statusBar().showMessage(f"Found {len(self.browse_records)} reference records. Import an experiment to calculate match scores.", 8000)
        else:
            self._redraw_plot()
            self.statusBar().showMessage("No reference records found. Update RRUFF, load a library, or relax filters.", 9000)

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
        use_openspecy = self.source_checks.get("OpenSpecy").isChecked() if hasattr(self, "source_checks") and "OpenSpecy" in self.source_checks else False
        records: list[CandidateRecord] = []
        if use_user_library:
            for source in self.user_libraries:
                records.extend(source.search(query))
        if use_rruff:
            records.extend(self.rruff_source.search(query))
        if use_openspecy:
            records.extend(self.openspecy_source.search(query))
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

    def _selected_laser_wavelength_nm(self) -> float:
        if not hasattr(self, "action_bar"):
            return 0.0
        return float(self.action_bar.laser_wavelength_spin.value())

    def _record_laser_wavelength_nm(self, record: CandidateRecord) -> float | None:
        raw_value = str(record.metadata.get("laser_nm", "") or "")
        match = re.search(r"(\d+(?:[.,]\d+)?)", raw_value)
        if not match:
            return None
        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def _record_passes_laser_gate(self, record: CandidateRecord) -> bool:
        selected_laser = self._selected_laser_wavelength_nm()
        if selected_laser <= 0.0 or record.kind != SignalKind.RAMAN:
            return True
        record_laser = self._record_laser_wavelength_nm(record)
        if record_laser is None:
            return False
        return abs(record_laser - selected_laser) <= 2.0

    def _refresh_project_tree(self) -> None:
        self.project_tree.clear()
        root = QTreeWidgetItem(["IR/Raman Phase Finder Project"])
        self.project_tree.addTopLevelItem(root)

        raman_root = QTreeWidgetItem(["Raman spectra"])
        ftir_root = QTreeWidgetItem(["FTIR spectra"])
        library_root = QTreeWidgetItem(["User reference libraries"])
        root.addChild(raman_root)
        root.addChild(ftir_root)
        root.addChild(library_root)

        for index, spectrum in enumerate(self.raman_spectra):
            item = QTreeWidgetItem([f"{index + 1:02d}  {spectrum.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("raman", index))
            raman_root.addChild(item)
        for index, spectrum in enumerate(self.ftir_spectra):
            item = QTreeWidgetItem([f"{index + 1:02d}  {spectrum.name}"])
            item.setData(0, Qt.ItemDataRole.UserRole, ("ftir", index))
            ftir_root.addChild(item)

        by_library: dict[str, tuple[QTreeWidgetItem, QTreeWidgetItem, QTreeWidgetItem]] = {}
        for index, record in enumerate(self.reference_records):
            library_name = Path(record.metadata.get("path", "")).parent.name or "User library"
            if library_name not in by_library:
                library_item = QTreeWidgetItem([library_name])
                raman_refs = QTreeWidgetItem(["Raman references"])
                ftir_refs = QTreeWidgetItem(["FTIR references"])
                library_item.addChild(raman_refs)
                library_item.addChild(ftir_refs)
                library_root.addChild(library_item)
                by_library[library_name] = (library_item, raman_refs, ftir_refs)
            _library_item, raman_refs, ftir_refs = by_library[library_name]
            item = QTreeWidgetItem([self._reference_label(record)])
            item.setData(0, Qt.ItemDataRole.UserRole, ("reference", index))
            if record.kind == SignalKind.RAMAN:
                raman_refs.addChild(item)
            elif record.kind == SignalKind.FTIR:
                ftir_refs.addChild(item)

        root.setExpanded(True)
        raman_root.setExpanded(True)
        ftir_root.setExpanded(True)
        library_root.setExpanded(True)

    def _reference_label(self, record: CandidateRecord) -> str:
        name = record.name or record.entry_id
        formula = f" ({record.formula})" if record.formula else ""
        return f"{name}{formula}"

    def _on_project_tree_selection_changed(self) -> None:
        item = self.project_tree.currentItem()
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, index = data
        if kind == "raman" and 0 <= index < len(self.raman_spectra):
            self.active_spectrum = self.raman_spectra[index]
            self.results = []
            self.browse_records = []
            self.candidate_table.set_results([])
            self._redraw_plot()
        elif kind == "ftir" and 0 <= index < len(self.ftir_spectra):
            self.active_spectrum = self.ftir_spectra[index]
            self.results = []
            self.browse_records = []
            self.candidate_table.set_results([])
            self._redraw_plot()
        elif kind == "reference" and 0 <= index < len(self.reference_spectra):
            self._preview_reference(self.reference_spectra[index])

    def _redraw_plot(self) -> None:
        self.match_plot.clear()
        self._ensure_cursor_position_items()
        if self.legend_item is not None:
            self.legend_item = None
            self._set_legend_visible(bool(getattr(self.plot_view_settings, "legend_visible", True)))
        if self.active_spectrum is not None and getattr(self.plot_view_settings, "layer_observed_visible", True):
            x, y = self._display_trace_xy(self.active_spectrum)
            self.match_plot.plot(
                x,
                y,
                pen=pg.mkPen(self._plot_observed_color(), width=float(getattr(self.plot_view_settings, "observed_width", 1.35))),
                name="Observed",
            )

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
            params["width"] = max(3200.0, current_width * 2.0)
            exporter.export(path)
        except Exception as exc:
            if not self.match_plot.grab().save(path):
                QMessageBox.warning(self, "Export image", f"Could not save current plot image:\n{exc}")
                return
        self.statusBar().showMessage(f"Exported image: {path}", 6000)

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
        self._redraw_plot()
        self._set_card(result)
        if result is None or result.aligned_reference is None:
            self._current_preview_reference = None
            return
        ref = result.aligned_reference
        self._current_preview_reference = ref
        if getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            x, y = self._display_trace_xy(ref)
            self.match_plot.plot(
                x,
                y,
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=result.candidate.name,
            )

    def _preview_reference(self, reference: ReferenceSpectrum) -> None:
        self._redraw_plot()
        self._current_preview_reference = reference
        if getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            x, y = self._display_trace_xy(reference)
            self.match_plot.plot(
                x,
                y,
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=reference.name,
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
        )
        result = VibrationalMatchResult(
            candidate=candidate,
            score=MatchScore(),
            aligned_reference=reference,
        )
        self._redraw_plot()
        self._current_preview_reference = reference
        if getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            x, y = self._display_trace_xy(reference)
            self.match_plot.plot(
                x,
                y,
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=reference.name,
            )
        self._set_reference_card(result)

    def _set_reference_card(self, result: VibrationalMatchResult) -> None:
        self._set_card(result)
        for key in ("Match", "Position score", "Intensity score", "Correlation", "Coverage", "X shift"):
            if key in self.card_labels:
                self.card_labels[key].setText("-")

    def _load_reference_record(self, record: CandidateRecord) -> ReferenceSpectrum:
        if record.source == self.rruff_source.name:
            return self.rruff_source.load_spectrum(record)
        if record.source == self.openspecy_source.name:
            return self.openspecy_source.load_spectrum(record)
        for source in self.user_libraries:
            if any(candidate.key == record.key for candidate in source.search(SourceQuery())):
                return source.load_spectrum(record)
        raise FileNotFoundError(record.key)

    def _add_selected_candidate(self) -> None:
        row = self.candidate_table.currentRow()
        if row < 0 or row >= len(self.results):
            return
        result = self.results[row]
        if result not in self.selected_results:
            self.selected_results.append(result)
        self.selected_table.set_selected(self.selected_results)

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
        self.band_table.setRowCount(len(result.observed_bands))
        reference_positions = [band.position for band in result.reference_bands]
        for row, band in enumerate(result.observed_bands):
            nearest = min(reference_positions, key=lambda value: abs(value - band.position)) if reference_positions else None
            delta = band.position - nearest if nearest is not None else None
            values = [
                f"{band.position:.2f}",
                f"{nearest:.2f}" if nearest is not None else "-",
                f"{delta:.2f}" if delta is not None else "-",
                f"{band.intensity:.3f}",
            ]
            for column, value in enumerate(values):
                self.band_table.setItem(row, column, QTableWidgetItem(value))

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
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        for column in range(table.columnCount()):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        return table

    def _management_row(self, label_text: str, actions: list[tuple[str, object]]) -> QWidget:
        row = QWidget()
        layout = QGridLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel(label_text)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title, 0, 0, 1, 2)
        for index, (button_text, callback) in enumerate(actions):
            button = QPushButton(button_text)
            button.setMinimumHeight(28)
            button.setStyleSheet(_glass_button_style("#2367a5", "#5a9bd8"))
            button.clicked.connect(callback)
            layout.addWidget(button, 1 + index // 2, index % 2)
        return row

    def _update_database_table(self) -> None:
        if not hasattr(self, "database_table"):
            return
        raman_count = sum(1 for record in self.reference_records if record.kind == SignalKind.RAMAN)
        ftir_count = sum(1 for record in self.reference_records if record.kind == SignalKind.FTIR)
        rruff_row = self.rruff_source.status_row()
        openspecy_row = self.openspecy_source.status_row()
        external_rows = [
            [info.name, info.status, info.details]
            for info in external_source_catalog().values()
            if info.key != "OpenSpecy"
        ]
        rows = [
            ["User Library", "Loaded" if self.user_libraries else "Empty", f"{len(self.user_libraries)} libraries, {raman_count} Raman, {ftir_count} FTIR"],
            [rruff_row[0], rruff_row[1], rruff_row[2]],
            [openspecy_row[0], openspecy_row[1], openspecy_row[2]],
        ] + external_rows
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
            text=self.action_bar.search_input.text().strip() if hasattr(self, "action_bar") else "",
            formula=self._element_formula_query(),
        )
        url = source.search_url(query)
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "External source", f"Could not open:\n{url}")

    def _planned_source(self) -> None:
        QMessageBox.information(self, "Planned source", "This database connector will be added after the local user library workflow is stable.")

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

    def _save_ui_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("splitters/main", self.main_splitter.saveState())
        self.settings.setValue("splitters/center", self.center_splitter.saveState())
        if hasattr(self, "elements_splitter"):
            self.settings.setValue("splitters/elements", self.elements_splitter.saveState())
        self.settings.setValue("tabs/right_index", self.right_tabs.currentIndex())
        self.settings.setValue("controls/display_mode", self.action_bar.display_mode.currentText())
        self.settings.setValue("controls/normalize", self.action_bar.normalize_checkbox.isChecked())
        self.settings.setValue("controls/laser_nm", self.action_bar.laser_wavelength_spin.value())
        self.settings.setValue("controls/include_raman", self.include_raman_checkbox.isChecked())
        self.settings.setValue("controls/include_ftir", self.include_ftir_checkbox.isChecked())
        self.settings.setValue("theme/preference", self.theme_preference)
        for label, checkbox in getattr(self, "source_checks", {}).items():
            self.settings.setValue(f"sources/{label}", checkbox.isChecked())
        self._save_header_state("headers/candidates", self.candidate_table)
        self._save_header_state("headers/selected", self.selected_table)
        self._save_header_state("headers/databases", self.database_table)
        self._save_header_state("headers/bands", self.band_table)
        self.settings.sync()

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
        right_index = int(self.settings.value("tabs/right_index", self.right_tabs.currentIndex()) or 0)
        if 0 <= right_index < self.right_tabs.count():
            self.right_tabs.setCurrentIndex(right_index)
        theme = str(self.settings.value("theme/preference", self.theme_preference, type=str) or self.theme_preference)
        if theme != self.theme_preference:
            self._apply_theme(theme)
        display_mode = str(self.settings.value("controls/display_mode", self.action_bar.display_mode.currentText(), type=str) or "")
        if display_mode:
            self.action_bar.display_mode.setCurrentText(display_mode)
        blocked = self.action_bar.laser_wavelength_spin.blockSignals(True)
        self.action_bar.laser_wavelength_spin.setValue(float(self.settings.value("controls/laser_nm", 532.0) or 532.0))
        self.action_bar.laser_wavelength_spin.blockSignals(blocked)
        self.action_bar.normalize_checkbox.setChecked(self._settings_bool("controls/normalize", True))
        self.include_raman_checkbox.setChecked(self._settings_bool("controls/include_raman", True))
        self.include_ftir_checkbox.setChecked(self._settings_bool("controls/include_ftir", True))
        for label, checkbox in getattr(self, "source_checks", {}).items():
            checkbox.setChecked(self._settings_bool(f"sources/{label}", checkbox.isChecked()))
        self._restore_header_state("headers/candidates", self.candidate_table)
        self._restore_header_state("headers/selected", self.selected_table)
        self._restore_header_state("headers/databases", self.database_table)
        self._restore_header_state("headers/bands", self.band_table)
        self._redraw_plot()

    def _normalization_mode(self) -> str:
        if hasattr(self, "action_bar") and self.action_bar.normalize_checkbox.isChecked():
            return "max"
        return "none"

    def _matching_options(self) -> MatchingOptions:
        return MatchingOptions(preprocessing=PreprocessingOptions(normalize=self._normalization_mode()))

    def _display_trace_xy(self, trace) -> tuple[list[float], list[float]]:
        if self._normalization_mode() == "none":
            return list(trace.x), list(trace.y)
        processed = preprocess_spectrum(trace, PreprocessingOptions(normalize=self._normalization_mode()))
        return list(processed.x), list(processed.y)

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
            return
        self._redraw_plot()
        if self._current_preview_reference is not None and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            x, y = self._display_trace_xy(self._current_preview_reference)
            self.match_plot.plot(
                x,
                y,
                pen=pg.mkPen(self._plot_reference_color(), width=float(getattr(self.plot_view_settings, "calculated_width", 1.7))),
                name=self._current_preview_reference.name,
            )

    def _reset_plot_view(self) -> None:
        self._set_plot_range_for_traces(self._experimental_range_traces())

    def _show_full_plot_range(self) -> None:
        traces = self._experimental_range_traces()
        if self._current_preview_reference is not None and getattr(self.plot_view_settings, "layer_preview_peak_positions_visible", True):
            traces.append(self._current_preview_reference)
        self._set_plot_range_for_traces(traces)

    def _experimental_range_traces(self) -> list[ObservedSpectrum]:
        traces = [*self.raman_spectra, *self.ftir_spectra]
        if traces:
            return traces
        return [self.active_spectrum] if self.active_spectrum is not None else []

    def _set_plot_range_for_traces(self, traces: list) -> None:
        valid_x: list[float] = []
        valid_y: list[float] = []
        for trace in traces:
            x_values, y_values = self._display_trace_xy(trace)
            x_array = np.asarray(x_values, dtype=float)
            y_array = np.asarray(y_values, dtype=float)
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
            self.cursor_label.setText(f"cm-1: {point.x():.2f}    I: {point.y():.2f}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("IR/Raman Phase Finder")
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
