from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.project_series import ProjectSeries


class ProjectTree(QTreeWidget):
    object_open_requested = Signal(str, str)
    object_rename_requested = Signal(str, str)
    object_delete_requested = Signal(str, str)
    series_create_requested = Signal()
    object_move_to_series_requested = Signal(str, str, str)
    spectrum_selection_changed = Signal(list)
    active_spectrum_requested = Signal(str)
    object_reorder_requested = Signal(str, str, int)

    def __init__(self) -> None:
        super().__init__()
        self.setHeaderLabel("Data")
        self.setToolTip(
            "Project tree\nSelect a spectrum to make it active.\n"
            "Checkboxes show or hide spectra or a complete series.\n"
            "Double click a spectrum to show only it."
        )
        self._updating = False
        self._checked_ids: set[str] = set()
        self._known_ids: set[str] = set()
        self._spectrum_order: list[str] = []
        self._spectrum_items: dict[str, QTreeWidgetItem] = {}
        self._series_items: dict[str, QTreeWidgetItem] = {}
        self._series_names: list[tuple[str, str]] = []
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.itemChanged.connect(self._on_item_changed)
        self.currentItemChanged.connect(self._on_current_item_changed)

    def set_project(
        self,
        *,
        project_id: str,
        project_name: str,
        spectra: list[ObservedSpectrum],
        series: list[ProjectSeries],
        spectrum_order_ids: list[str],
    ) -> None:
        expansion = self._capture_expansion_state()
        self._updating = True
        self.clear()
        self._spectrum_items = {}
        self._series_items = {}
        self._series_names = [(item.id, item.name) for item in series]
        by_id = {item.id: item for item in spectra}
        self._spectrum_order = [item for item in spectrum_order_ids if item in by_id]
        self._spectrum_order.extend(item.id for item in spectra if item.id not in self._spectrum_order)
        available = set(by_id)
        new_ids = available - self._known_ids
        self._checked_ids &= available
        self._checked_ids |= new_ids
        self._known_ids = available

        root = QTreeWidgetItem([project_name])
        root.setData(0, Qt.ItemDataRole.UserRole, ("project", project_id))
        self.addTopLevelItem(root)
        claimed: set[str] = set()
        for group in series:
            series_item = QTreeWidgetItem([group.name])
            series_item.setData(0, Qt.ItemDataRole.UserRole, ("series", group.id))
            series_item.setFlags(series_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            series_item.setToolTip(0, "Project series\nCheckbox: show or hide every spectrum in this series.")
            self._series_items[group.id] = series_item
            root.addChild(series_item)
            member_ids = set(group.spectrum_ids)
            for spectrum_id in self._spectrum_order:
                if spectrum_id not in member_ids:
                    continue
                spectrum = by_id.get(spectrum_id)
                if spectrum is not None and spectrum_id not in claimed:
                    self._add_spectrum_item(series_item, spectrum)
                    claimed.add(spectrum_id)
        unassigned = [by_id[item] for item in self._spectrum_order if item not in claimed]
        if unassigned:
            no_series = QTreeWidgetItem(["No series"])
            no_series.setData(0, Qt.ItemDataRole.UserRole, ("group", "unassigned"))
            root.addChild(no_series)
            for spectrum in unassigned:
                self._add_spectrum_item(no_series, spectrum)

        self._restore_expansion_state(root, expansion)
        self._refresh_series_check_states()
        self._updating = False
        self.spectrum_selection_changed.emit(self.checked_spectrum_ids())

    def _add_spectrum_item(self, parent: QTreeWidgetItem, spectrum: ObservedSpectrum) -> None:
        number = self._spectrum_order.index(spectrum.id) + 1
        child = QTreeWidgetItem([f"{number:02d}  {spectrum.name}"])
        child.setData(0, Qt.ItemDataRole.UserRole, ("spectrum", spectrum.id))
        child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        child.setCheckState(0, Qt.CheckState.Checked if spectrum.id in self._checked_ids else Qt.CheckState.Unchecked)
        kind = "Raman" if spectrum.kind.value == "raman" else "FTIR"
        child.setToolTip(0, f"{kind} spectrum\nSelect: make active. Checkbox: plot visibility. Double click: show only.")
        self._spectrum_items[spectrum.id] = child
        parent.addChild(child)

    def checked_spectrum_ids(self) -> list[str]:
        return [item for item in self._spectrum_order if item in self._checked_ids]

    def set_checked_spectrum_ids(self, spectrum_ids: list[str]) -> None:
        checked = set(spectrum_ids) & self._known_ids
        if checked == self._checked_ids:
            return
        self._checked_ids = checked
        self._updating = True
        for spectrum_id, item in self._spectrum_items.items():
            item.setCheckState(0, Qt.CheckState.Checked if spectrum_id in checked else Qt.CheckState.Unchecked)
        self._refresh_series_check_states()
        self._updating = False
        self.spectrum_selection_changed.emit(self.checked_spectrum_ids())

    def current_object(self) -> tuple[str, str] | None:
        item = self.currentItem()
        data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if data and data[0] in {"series", "spectrum"}:
            return str(data[0]), str(data[1])
        return None

    def current_series_id(self) -> str | None:
        item = self.currentItem()
        while item is not None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "series":
                return str(data[1])
            item = item.parent()
        return None

    def select_object(self, object_type: str, object_id: str) -> None:
        item = self._series_items.get(object_id) if object_type == "series" else self._spectrum_items.get(object_id)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)

    def _capture_expansion_state(self) -> dict[tuple[str, str], bool]:
        result: dict[tuple[str, str], bool] = {}

        def visit(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and len(data) == 2:
                result[(str(data[0]), str(data[1]))] = item.isExpanded()
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.topLevelItemCount()):
            visit(self.topLevelItem(index))
        return result

    def expansion_state(self) -> dict[str, bool]:
        return {
            f"{kind}:{object_id}": expanded
            for (kind, object_id), expanded in self._capture_expansion_state().items()
            if kind in {"project", "series", "group"}
        }

    def restore_expansion_state(self, state: dict[str, bool] | None) -> None:
        parsed: dict[tuple[str, str], bool] = {}
        for key, expanded in (state or {}).items():
            kind, separator, object_id = str(key).partition(":")
            if separator and kind in {"project", "series", "group"} and object_id:
                parsed[(kind, object_id)] = bool(expanded)
        root = self.topLevelItem(0)
        if root is not None:
            self._restore_expansion_state(root, parsed)

    def _restore_expansion_state(self, root: QTreeWidgetItem, state: dict[tuple[str, str], bool]) -> None:
        def visit(item: QTreeWidgetItem) -> None:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data:
                key = (str(data[0]), str(data[1]))
                item.setExpanded(state.get(key, str(data[0]) in {"project", "group"}))
            for index in range(item.childCount()):
                visit(item.child(index))

        visit(root)

    def _refresh_series_check_states(self) -> None:
        for item in self._series_items.values():
            states = [item.child(index).checkState(0) for index in range(item.childCount())]
            if not states or all(state == Qt.CheckState.Unchecked for state in states):
                state = Qt.CheckState.Unchecked
            elif all(state == Qt.CheckState.Checked for state in states):
                state = Qt.CheckState.Checked
            else:
                state = Qt.CheckState.PartiallyChecked
            item.setCheckState(0, state)

    def _on_item_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._updating:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, object_id = data
        if kind == "series":
            checked = item.checkState(0) == Qt.CheckState.Checked
            self._updating = True
            for index in range(item.childCount()):
                child = item.child(index)
                child_data = child.data(0, Qt.ItemDataRole.UserRole)
                if not child_data or child_data[0] != "spectrum":
                    continue
                child.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                if checked:
                    self._checked_ids.add(str(child_data[1]))
                else:
                    self._checked_ids.discard(str(child_data[1]))
            self._updating = False
            self.spectrum_selection_changed.emit(self.checked_spectrum_ids())
        elif kind == "spectrum":
            if item.checkState(0) == Qt.CheckState.Checked:
                self._checked_ids.add(str(object_id))
            else:
                self._checked_ids.discard(str(object_id))
            self._updating = True
            self._refresh_series_check_states()
            self._updating = False
            self.spectrum_selection_changed.emit(self.checked_spectrum_ids())

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and data[0] == "spectrum":
            self.object_open_requested.emit("spectrum", str(data[1]))

    def _on_current_item_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        data = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        if data and data[0] == "spectrum":
            self.active_spectrum_requested.emit(str(data[1]))

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        current = self.currentItem()
        data = current.data(0, Qt.ItemDataRole.UserRole) if current is not None else None
        if data:
            kind, object_id = str(data[0]), str(data[1])
            if event.key() == Qt.Key.Key_F2 and kind in {"project", "series", "spectrum"}:
                self.object_rename_requested.emit(kind, object_id)
                return
            if event.key() == Qt.Key.Key_Delete and kind in {"series", "spectrum"}:
                self.object_delete_requested.emit(kind, object_id)
                return
        super().keyPressEvent(event)

    def _show_context_menu(self, position: QPoint) -> None:
        item = self.itemAt(position)
        data = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not data or data[0] not in {"project", "series", "spectrum"}:
            return
        kind, object_id = str(data[0]), str(data[1])
        menu = QMenu(self)
        add_action = menu.addAction("Add series") if kind == "project" else None
        open_action = menu.addAction("Open") if kind == "spectrum" else None
        rename_action = menu.addAction("Rename")
        up_action = menu.addAction("Move up") if kind in {"series", "spectrum"} else None
        down_action = menu.addAction("Move down") if kind in {"series", "spectrum"} else None
        moves: list[tuple[object, str]] = []
        if kind == "spectrum":
            move_menu = menu.addMenu("Move to series")
            moves.append((move_menu.addAction("No series"), ""))
            if self._series_names:
                move_menu.addSeparator()
                moves.extend((move_menu.addAction(name), series_id) for series_id, name in self._series_names)
        delete_action = menu.addAction("Delete series" if kind == "series" else "Delete") if kind != "project" else None
        action = menu.exec(self.viewport().mapToGlobal(position))
        if action is None:
            return
        if action == add_action:
            self.series_create_requested.emit()
        elif action == open_action:
            self.object_open_requested.emit(kind, object_id)
        elif action == rename_action:
            self.object_rename_requested.emit(kind, object_id)
        elif action == up_action:
            self.object_reorder_requested.emit(kind, object_id, -1)
        elif action == down_action:
            self.object_reorder_requested.emit(kind, object_id, 1)
        elif action == delete_action:
            self.object_delete_requested.emit(kind, object_id)
        else:
            for move_action, target in moves:
                if action == move_action:
                    self.object_move_to_series_requested.emit(kind, object_id, target)
                    break
