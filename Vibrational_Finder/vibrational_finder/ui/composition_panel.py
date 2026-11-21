from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter, QVBoxLayout, QWidget

from vibrational_finder.ui.element_filter import PeriodicTableWidget


class SpectroscopyCompositionPanel(QWidget):
    """XRD-shaped chemistry/search panel with spectroscopy result content."""

    requiredElementToggled = Signal(str)
    excludedElementToggled = Signal(str)
    elementsPainted = Signal(list, str)
    exclusionModeToggleRequested = Signal()
    searchRequested = Signal(str)
    resetRequested = Signal()

    def __init__(self, accepted_results: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("spectroscopyCompositionPanel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setObjectName("compositionSplitter")
        outer.addWidget(self.splitter)

        element_panel = QWidget()
        element_panel.setObjectName("compositionElements")
        element_layout = QVBoxLayout(element_panel)
        element_layout.setContentsMargins(5, 4, 5, 4)
        element_layout.setSpacing(3)
        title = QLabel("Element filters")
        title.setProperty("uiRole", "sectionTitle")
        element_layout.addWidget(title)
        self.element_table = PeriodicTableWidget()
        self.element_table.setObjectName("periodicTable")
        self.element_table.leftClicked.connect(self.requiredElementToggled)
        self.element_table.rightClicked.connect(self.excludedElementToggled)
        self.element_table.elementsPainted.connect(self.elementsPainted)
        self.element_table.modeToggleRequested.connect(self.exclusionModeToggleRequested)
        element_layout.addWidget(self.element_table, 1)
        self.splitter.addWidget(element_panel)

        controls_panel = QWidget()
        controls_panel.setObjectName("compositionControls")
        controls_layout = QVBoxLayout(controls_panel)
        controls_layout.setContentsMargins(6, 4, 6, 4)
        controls_layout.setSpacing(5)
        self.filter_summary = QLabel("Chemical filter: none")
        self.filter_summary.setObjectName("compositionFilterSummary")
        self.filter_summary.setWordWrap(True)
        controls_layout.addWidget(self.filter_summary)
        self.query_edit = QLineEdit()
        self.query_edit.setObjectName("compositionQueryEdit")
        self.query_edit.setPlaceholderText("Name, mineral or formula")
        controls_layout.addWidget(self.query_edit)
        actions = QHBoxLayout()
        self.search_button = QPushButton("Search database")
        self.search_button.setObjectName("compositionSearchButton")
        self.reset_button = QPushButton("Clear search")
        self.reset_button.setObjectName("compositionResetButton")
        actions.addWidget(self.search_button)
        actions.addWidget(self.reset_button)
        controls_layout.addLayout(actions)
        controls_layout.addWidget(accepted_results, 1)
        self.splitter.addWidget(controls_panel)

        self.search_button.clicked.connect(lambda: self.searchRequested.emit(self.query_edit.text().strip()))
        self.query_edit.returnPressed.connect(lambda: self.searchRequested.emit(self.query_edit.text().strip()))
        self.reset_button.clicked.connect(self.resetRequested)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([260, 390])

    def set_search_mode(self, mode: str) -> None:
        labels = {
            "search": "Search database",
            "auto": "Identify compounds",
            "bands": "Band search",
        }
        if mode not in labels:
            raise ValueError(f"Unknown search mode: {mode}")
        self.search_button.setText(labels[mode])
        self.search_button.setProperty("searchMode", mode)
        self.search_button.style().unpolish(self.search_button)
        self.search_button.style().polish(self.search_button)
        self.search_button.update()
