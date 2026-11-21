from __future__ import annotations

from collections.abc import Callable, Sequence
import math

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QHBoxLayout, QSplitter, QTabWidget, QToolButton, QWidget


def normalize_splitter_ratios(values: Sequence[int | float], expected_count: int) -> tuple[float, ...]:
    if len(values) != expected_count:
        raise ValueError(f"Expected {expected_count} values, got {len(values)}.")
    numbers = tuple(float(value) for value in values)
    if not numbers or any(not math.isfinite(value) or value <= 0.0 for value in numbers):
        raise ValueError("Splitter values must be finite and positive.")
    total = sum(numbers)
    if total <= 0.0:
        raise ValueError("Splitter values must have a positive sum.")
    return tuple(value / total for value in numbers)


def splitter_sizes(total: int, ratios: Sequence[float], minimums: Sequence[int]) -> list[int]:
    if len(ratios) != len(minimums) or not ratios:
        raise ValueError("Ratios and minimums must have the same non-zero length.")
    if total < sum(minimums):
        raise ValueError("Total extent is smaller than the required minimum sizes.")
    normalized = normalize_splitter_ratios(ratios, len(ratios))
    sizes = [max(int(minimum), round(total * ratio)) for ratio, minimum in zip(normalized, minimums)]
    excess = sum(sizes) - total
    while excess > 0:
        index = max(range(len(sizes)), key=lambda item: sizes[item] - int(minimums[item]))
        available = sizes[index] - int(minimums[index])
        if available <= 0:
            raise ValueError("Minimum sizes cannot be satisfied within the total extent.")
        reduction = min(excess, available)
        sizes[index] -= reduction
        excess -= reduction
    if sum(sizes) < total:
        index = max(range(len(sizes)), key=lambda item: normalized[item])
        sizes[index] += total - sum(sizes)
    return sizes


class SplitterLayoutState:
    """Direct spectroscopy adaptation of XRD 1.6.7's layout controller."""

    def __init__(
        self,
        settings: QSettings,
        names: tuple[str, ...] = ("main_splitter", "center_splitter", "composition_splitter"),
    ) -> None:
        from vibrational_finder.ui.workspace_preferences import WorkspacePreferences

        self._settings = settings
        self._preferences = WorkspacePreferences(settings)
        self._names = names
        self._splitters: dict[str, QSplitter] = {}
        self._tables: dict[str, object] = {}
        self._splitter_proportions: dict[str, tuple[float, ...]] = {}
        has_saved_layout = self._preferences.has_saved_state() or any(
            key.startswith("layout/") for key in settings.allKeys()
        )
        self._pinned = bool(settings.value("layout/pinned", has_saved_layout, type=bool))
        self.pin_button: QToolButton | None = None
        self.help_button: QToolButton | None = None

    @property
    def pinned(self) -> bool:
        return self._pinned

    def register(self, name: str, splitter: QSplitter) -> QSplitter:
        splitter.setChildrenCollapsible(False)
        self._splitters[name] = splitter
        self._apply_lock(splitter)
        return splitter

    def register_table(self, name: str, table):
        self._tables[name] = table
        table.set_column_layout_editable(not self._pinned)
        return table

    def add_pin_corner(self, tabs: QTabWidget, help_callback: Callable[[], None] | None) -> QToolButton:
        corner = QWidget()
        row = QHBoxLayout(corner)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        pin_button = QToolButton()
        pin_button.setText("Edit layout")
        pin_button.setObjectName("editLayoutButton")
        pin_button.setAccessibleName("Edit layout")
        pin_button.setCheckable(True)
        pin_button.setChecked(not self._pinned)
        pin_button.setToolTip("On: move and resize panels and table columns. Off: save and lock the layout.")
        pin_button.toggled.connect(lambda editing: self.set_pinned(not editing))

        help_button = QToolButton()
        help_button.setText("?")
        help_button.setObjectName("contextHelpButton")
        help_button.setAccessibleName("Context help")
        help_button.setToolTip("Click a control to explain it without running its command")
        help_button.setCheckable(True)
        if help_callback is not None:
            help_button.clicked.connect(help_callback)

        row.addWidget(pin_button)
        row.addWidget(help_button)
        tabs.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.pin_button = pin_button
        self.help_button = help_button
        self.apply_lock()
        return pin_button

    def set_pinned(self, pinned: bool) -> None:
        self._pinned = bool(pinned)
        self._settings.setValue("layout/pinned", self._pinned)
        if self._pinned:
            self.save()
        else:
            self._settings.sync()
        self.apply_lock()
        if self.pin_button is not None:
            self.pin_button.blockSignals(True)
            self.pin_button.setChecked(not self._pinned)
            self.pin_button.blockSignals(False)

    def apply_lock(self) -> None:
        for splitter in self._splitters.values():
            self._apply_lock(splitter)
        for table in self._tables.values():
            table.set_column_layout_editable(not self._pinned)

    def remember_splitter_proportions(self, name: str, splitter: QSplitter | None = None) -> None:
        splitter = splitter or self._splitters.get(name)
        if splitter is None:
            return
        try:
            values = normalize_splitter_ratios(splitter.sizes(), splitter.count())
        except ValueError:
            return
        self._splitter_proportions[name] = values

    def apply_proportions(self) -> None:
        for name, splitter in self._splitters.items():
            values = self._splitter_proportions.get(name)
            if values is None:
                continue
            extent = splitter.width() if splitter.orientation() == Qt.Orientation.Horizontal else splitter.height()
            available = max(1, extent - splitter.handleWidth() * (splitter.count() - 1))
            splitter.setSizes([max(1, round(value * available)) for value in values])

    def save(self) -> None:
        state = self._preferences.load()
        panels: dict[str, tuple[float, ...]] = {}
        for name in self._names:
            splitter = self._splitters.get(name)
            if splitter is None:
                continue
            if name not in self._splitter_proportions:
                self.remember_splitter_proportions(name, splitter)
            values = self._splitter_proportions.get(name)
            if values is not None:
                panels[name] = values
        state.splitter_ratios = panels
        self._preferences.save(state)
        self._settings.sync()

    def restore(self) -> None:
        from vibrational_finder.ui.workspace_preferences import DEFAULT_SPLITTER_PROPORTIONS

        state = self._preferences.load()
        legacy_names = {
            "main_splitter": "main",
            "center_splitter": "center",
            "composition_splitter": "composition",
        }
        for name in self._names:
            splitter = self._splitters.get(name)
            if splitter is None:
                continue
            raw = state.splitter_ratios.get(name)
            if raw is None:
                raw = state.splitter_ratios.get(legacy_names[name])
            if raw is None:
                raw = DEFAULT_SPLITTER_PROPORTIONS.get(name)
            try:
                values = normalize_splitter_ratios(raw, splitter.count()) if raw is not None else None
            except (TypeError, ValueError):
                values = None
            if values is not None:
                self._splitter_proportions[name] = values
        self.apply_proportions()

    def _apply_lock(self, splitter: QSplitter) -> None:
        for index in range(1, splitter.count()):
            splitter.handle(index).setEnabled(not self._pinned)
        density = getattr(splitter.window(), "ui_density_factor", 1.0)
        splitter.setHandleWidth(max(1, round((1 if self._pinned else 7) * density)))
