from __future__ import annotations

import math

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QHeaderView, QTableWidget


def _normalized(values, count: int) -> list[float] | None:
    try:
        numbers = [float(value) for value in values]
    except (TypeError, ValueError):
        return None
    if len(numbers) != count or any(not math.isfinite(value) or value <= 0 for value in numbers):
        return None
    total = sum(numbers)
    return [value / total for value in numbers] if total > 0 else None


class ManagedColumnTable(QTableWidget):
    """Fit saved column fractions exactly to the visible table viewport."""

    def __init__(self, rows: int, columns: int, parent=None, *, default_proportions=None) -> None:
        super().__init__(rows, columns, parent)
        self._default_column_proportions = _normalized(default_proportions or [1] * columns, columns)
        self._column_layout_weights: list[float] = []
        self._column_layout_editable = False
        self._column_layout_managed = False
        self._fitting_columns = False
        self._column_fit_timer = QTimer(self)
        self._column_fit_timer.setSingleShot(True)
        self._column_fit_timer.timeout.connect(self._fit_columns_to_viewport)
        self.viewport().installEventFilter(self)
        self.horizontalHeader().sectionResized.connect(self._column_section_resized)

    def set_column_layout_editable(self, editable: bool) -> None:
        self._column_layout_managed = True
        self._column_layout_editable = bool(editable)
        self._apply_column_layout_lock()

    def column_layout_state(self) -> dict[str, list[int] | list[float]]:
        if not self._column_layout_weights:
            self._capture_column_proportions()
        header = self.horizontalHeader()
        return {
            "order": [header.logicalIndex(visual) for visual in range(self.columnCount())],
            "proportions": list(self._column_layout_weights),
        }

    def restore_column_layout(self, state) -> bool:
        if not isinstance(state, dict):
            return False
        count = self.columnCount()
        order = state.get("order")
        weights = _normalized(state.get("proportions"), count)
        if weights is None or not isinstance(order, (list, tuple)) or sorted(order) != list(range(count)):
            return False
        self._fitting_columns = True
        try:
            header = self.horizontalHeader()
            for visual, logical in enumerate(order):
                header.moveSection(header.visualIndex(int(logical)), visual)
            self._column_layout_weights = weights
        finally:
            self._fitting_columns = False
        self._apply_column_layout_lock()
        return True

    def _capture_column_proportions(self) -> None:
        widths = [max(1, self.columnWidth(column)) for column in range(self.columnCount())]
        total = sum(widths)
        self._column_layout_weights = [width / total for width in widths] if total else []

    def _apply_column_layout_lock(self) -> None:
        if not self._column_layout_managed:
            return
        if not self._column_layout_weights:
            self._column_layout_weights = list(self._default_column_proportions or [])
            if not self._column_layout_weights:
                self._capture_column_proportions()
        header = self.horizontalHeader()
        self._fitting_columns = True
        try:
            header.setStretchLastSection(False)
            header.setMinimumSectionSize(1)
            header.setSectionsMovable(self._column_layout_editable)
            header.setFirstSectionMovable(self._column_layout_editable)
            mode = QHeaderView.ResizeMode.Interactive if self._column_layout_editable else QHeaderView.ResizeMode.Fixed
            header.setSectionResizeMode(mode)
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        finally:
            self._fitting_columns = False
        self._fit_columns_to_viewport()

    def _minimum_column_width(self, total: int) -> int:
        density = getattr(self.window(), "ui_density_factor", 1.0)
        return max(1, min(round(20 * density), total // max(1, self.columnCount())))

    def _fit_columns_to_viewport(self) -> None:
        if not self._column_layout_managed or self._fitting_columns:
            return
        count = self.columnCount()
        total = self.viewport().width()
        weights = self._column_layout_weights
        if len(weights) != count or total < count or not weights:
            return
        minimum = self._minimum_column_width(total)
        widths = [0] * count
        active = list(range(count))
        remaining = total
        while active:
            scale = remaining / sum(weights[index] for index in active)
            narrow = [index for index in active if weights[index] * scale < minimum]
            if not narrow:
                desired = {index: weights[index] * scale for index in active}
                for index in active:
                    widths[index] = int(desired[index])
                extra = remaining - sum(widths[index] for index in active)
                for index in sorted(active, key=lambda item: desired[item] - widths[item], reverse=True)[:extra]:
                    widths[index] += 1
                break
            for index in narrow:
                widths[index] = minimum
                remaining -= minimum
                active.remove(index)
        self._set_fitted_column_widths(widths)

    def _set_fitted_column_widths(self, widths: list[int]) -> None:
        self._fitting_columns = True
        try:
            for column, width in enumerate(widths):
                if self.columnWidth(column) != width:
                    self.setColumnWidth(column, width)
            self.updateGeometries()
            self.horizontalScrollBar().setValue(0)
        finally:
            self._fitting_columns = False

    def _column_section_resized(self, column: int, _old_size: int, new_size: int) -> None:
        if self._fitting_columns or not self._column_layout_managed or not self._column_layout_editable:
            return
        count = self.columnCount()
        total = self.viewport().width()
        if count < 2 or total < count:
            return
        minimum = self._minimum_column_width(total)
        widths = [self.columnWidth(index) for index in range(count)]
        widths[column] = max(minimum, min(new_size, total - minimum * (count - 1)))
        header = self.horizontalHeader()
        visual = header.visualIndex(column)
        neighbours = [header.logicalIndex(index) for index in range(visual + 1, count)]
        neighbours += [header.logicalIndex(index) for index in range(visual - 1, -1, -1)]
        excess = sum(widths) - total
        if excess > 0:
            for index in neighbours:
                take = min(excess, max(0, widths[index] - minimum))
                widths[index] -= take
                excess -= take
                if excess == 0:
                    break
        elif excess < 0 and neighbours:
            widths[neighbours[0]] -= excess
        self._set_fitted_column_widths(widths)
        self._capture_column_proportions()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._fit_columns_to_viewport()

    def eventFilter(self, watched, event):  # type: ignore[override]
        if watched is self.viewport() and event.type() == QEvent.Type.Resize:
            self._column_fit_timer.start(0)
        return super().eventFilter(watched, event)
