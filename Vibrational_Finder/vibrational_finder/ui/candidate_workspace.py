from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finder_core.models import CandidateRecord

from vibrational_finder.models import VibrationalMatchResult
from vibrational_finder.ui.managed_table import ManagedColumnTable


_NUMERIC_ROLE = Qt.ItemDataRole.UserRole + 1


class NumericTableItem(QTableWidgetItem):
    def __lt__(self, other: QTableWidgetItem) -> bool:
        left = self.data(_NUMERIC_ROLE)
        right = other.data(_NUMERIC_ROLE)
        if left is not None and right is not None:
            return float(left) < float(right)
        return super().__lt__(other)


class CandidateStatusLabel(QLabel):
    messagePublished = Signal(str)

    def setText(self, text: str) -> None:
        super().setText(text)
        self.messagePublished.emit(text)

    def set_routine_text(self, text: str) -> None:
        super().setText(text)
        self.messagePublished.emit("")


class CandidateWorkspace(QWidget):
    matchRequested = Signal(str)
    cancelRequested = Signal()
    previewRequested = Signal(str)
    acceptRequested = Signal(str)

    HEADERS = ("Source", "Compound", "Formula", "Match", "Pos.", "Corr.", "Cov.", "Bands", "Shift")
    HEADER_TOOLTIPS = (
        "Reference library or source",
        "Compound name or database entry",
        "Chemical formula",
        "Combined match score",
        "Position score",
        "Correlation score",
        "Coverage score",
        "Matched bands",
        "Axis shift",
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("candidatePanel")
        self._results: dict[str, VibrationalMatchResult] = {}
        self._records: dict[str, CandidateRecord] = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.search_controls = QWidget()
        self.search_controls.setObjectName("candidateSearchControls")
        query_row = QHBoxLayout(self.search_controls)
        query_row.setContentsMargins(0, 0, 0, 0)
        self.query_edit = QLineEdit()
        self.query_edit.setObjectName("candidateQueryEdit")
        self.query_edit.setPlaceholderText("Name, mineral or formula")
        self.match_button = QPushButton("Match")
        self.match_button.setObjectName("candidateMatchButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("candidateCancelButton")
        self.cancel_button.setEnabled(False)
        query_row.addWidget(self.query_edit, 1)
        query_row.addWidget(self.match_button)
        query_row.addWidget(self.cancel_button)
        layout.addWidget(self.search_controls)
        self.status_label = CandidateStatusLabel("Ready")
        self.status_label.setObjectName("candidateStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        self.table = ManagedColumnTable(
            0, len(self.HEADERS), default_proportions=(0.11, 0.16, 0.12, 0.10, 0.11, 0.12, 0.10, 0.09, 0.09)
        )
        self.table.setObjectName("candidateTable")
        self.table.setHorizontalHeaderLabels(list(self.HEADERS))
        for column, tooltip in enumerate(self.HEADER_TOOLTIPS):
            self.table.horizontalHeaderItem(column).setToolTip(tooltip)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.set_column_layout_editable(False)
        layout.addWidget(self.table, 1)
        self.match_button.clicked.connect(lambda: self.matchRequested.emit(self.query_edit.text().strip()))
        self.query_edit.returnPressed.connect(lambda: self.matchRequested.emit(self.query_edit.text().strip()))
        self.cancel_button.clicked.connect(self.cancelRequested)
        self.table.cellClicked.connect(lambda row, _column: self._emit_key(self.previewRequested, row))
        self.table.cellDoubleClicked.connect(lambda row, _column: self._emit_key(self.acceptRequested, row))

    def candidate_key_at(self, row: int) -> str:
        item = self.table.item(row, 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item is not None else ""

    def result_for_key(self, key: str) -> VibrationalMatchResult | None:
        return self._results.get(key)

    def record_for_key(self, key: str) -> CandidateRecord | None:
        return self._records.get(key)

    def _emit_key(self, signal: Signal, row: int) -> None:
        key = self.candidate_key_at(row)
        if key:
            signal.emit(key)

    @staticmethod
    def _number(value: float, digits: int = 1) -> NumericTableItem:
        item = NumericTableItem(f"{float(value):.{digits}f}")
        item.setData(_NUMERIC_ROLE, float(value))
        return item

    def set_results(self, results: list[VibrationalMatchResult]) -> None:
        self._set_results(results, prefix="")

    def set_records(self, records: list[CandidateRecord]) -> None:
        self._results.clear()
        self._records = {record.key: record for record in records}
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            values = (record.source, record.name or record.entry_id, record.formula)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, record.key)
                self.table.setItem(row, column, item)
            for column in range(3, len(self.HEADERS)):
                item = QTableWidgetItem("—")
                item.setData(Qt.ItemDataRole.UserRole, record.key)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(sorting)
        self.status_label.set_routine_text(f"{len(records)} reference{'s' if len(records) != 1 else ''}")
        self.match_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def set_residual_results(self, results: list[VibrationalMatchResult]) -> None:
        self._set_results(results, prefix="Next component — ")

    def _set_results(self, results: list[VibrationalMatchResult], *, prefix: str) -> None:
        self._records.clear()
        self._results = {result.candidate.key: result for result in results}
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(results))
        for row, result in enumerate(results):
            candidate = result.candidate
            text_values = (candidate.source, candidate.name, candidate.formula)
            for column, value in enumerate(text_values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, candidate.key)
                self.table.setItem(row, column, item)
            score = result.score
            numeric = (
                score.combined,
                score.position,
                score.correlation,
                score.coverage,
                score.matched_features,
                score.x_shift,
            )
            for column, value in enumerate(numeric, start=3):
                item = self._number(value, 0 if column == 7 else 1)
                item.setData(Qt.ItemDataRole.UserRole, candidate.key)
                self.table.setItem(row, column, item)
        self.table.setSortingEnabled(sorting)
        if sorting and results:
            self.table.sortItems(3, Qt.SortOrder.DescendingOrder)
        self.status_label.set_routine_text(f"{prefix}{len(results)} candidate{'s' if len(results) != 1 else ''}")
        self.match_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def set_pending(self) -> None:
        self.status_label.setText("Searching spectroscopy references…")
        self.match_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def set_failed(self, message: str) -> None:
        self.status_label.setText(f"Match failed: {message}")
        self.match_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def set_unavailable(self, message: str) -> None:
        self._results.clear()
        self._records.clear()
        self.table.setRowCount(0)
        self.status_label.setText(message)
        self.match_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

    def set_cancelled(self) -> None:
        self.status_label.setText("Match cancelled")
        self.match_button.setEnabled(True)
        self.cancel_button.setEnabled(False)

