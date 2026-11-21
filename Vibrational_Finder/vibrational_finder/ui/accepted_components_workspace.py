from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from vibrational_finder.models import VibrationalMatchResult
from vibrational_finder.ui.managed_table import ManagedColumnTable


class AcceptedComponentsWorkspace(QWidget):
    visibilityChanged = Signal(str, bool)
    removeRequested = Signal(str)
    clearRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("acceptedComponentsPanel")
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.header = QWidget()
        self.header.setObjectName("acceptedResultsHeader")
        self.header_layout = QHBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setSpacing(5)
        self.title_label = QLabel("Accepted results")
        self.title_label.setProperty("uiRole", "sectionTitle")
        self.remove_button = QPushButton("Remove")
        self.remove_button.setObjectName("removeComponentButton")
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("clearComponentsButton")
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch(1)
        self.header_layout.addWidget(self.remove_button)
        self.header_layout.addWidget(self.clear_button)
        layout.addWidget(self.header)
        self.table = ManagedColumnTable(0, 5, default_proportions=(0.08, 0.08, 0.20, 0.44, 0.20))
        self.table.setObjectName("acceptedComponentsTable")
        self.table.setHorizontalHeaderLabels(["✓", "●", "Source", "Compound", "Match"])
        header_tooltips = (
            "Show this accepted component on the plot",
            "Plot color",
            "Reference library or source",
            "Accepted compound name",
            "Combined match score",
        )
        for column, tooltip in enumerate(header_tooltips):
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.set_column_layout_editable(False)
        self.table.itemChanged.connect(self._item_changed)
        layout.addWidget(self.table, 1)
        self.remove_button.clicked.connect(self._remove_selected)
        self.clear_button.clicked.connect(self.clearRequested)

    def set_components(
        self,
        results: list[VibrationalMatchResult],
        visible_keys: set[str],
        colors: dict[str, str],
    ) -> None:
        self._updating = True
        try:
            self.table.setRowCount(len(results))
            for row, result in enumerate(results):
                key = result.candidate.key
                visible = QTableWidgetItem("")
                visible.setFlags(visible.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                visible.setCheckState(Qt.CheckState.Checked if key in visible_keys else Qt.CheckState.Unchecked)
                visible.setData(Qt.ItemDataRole.UserRole, key)
                self.table.setItem(row, 0, visible)
                color = QTableWidgetItem(colors.get(key, ""))
                color.setData(Qt.ItemDataRole.UserRole, key)
                if colors.get(key):
                    color.setBackground(QColor(colors[key]))
                self.table.setItem(row, 1, color)
                values = (result.candidate.source, result.candidate.name or result.candidate.entry_id, f"{result.score.combined:.1f}")
                for column, value in enumerate(values, start=2):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, key)
                    self.table.setItem(row, column, item)
            enabled = bool(results)
            self.remove_button.setEnabled(enabled)
            self.clear_button.setEnabled(enabled)
        finally:
            self._updating = False

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 0:
            return
        key = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if key:
            self.visibilityChanged.emit(key, item.checkState() == Qt.CheckState.Checked)

    def _remove_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        item = self.table.item(row, 0)
        key = str(item.data(Qt.ItemDataRole.UserRole) or "") if item is not None else ""
        if key:
            self.removeRequested.emit(key)

