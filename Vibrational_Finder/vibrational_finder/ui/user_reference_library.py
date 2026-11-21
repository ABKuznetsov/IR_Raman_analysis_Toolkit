from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from vibrational_finder.services.user_reference_store import UserReferenceStore, read_reference_card, write_json_atomic
from vibrational_finder.ui.reference_editor import ReferenceEditorDialog


_CARD_FILTER = "Reference cards (*.json *.vsref);;JSON (*.json);;All files (*)"


class UserReferenceLibraryDialog(QDialog):
    libraryChanged = Signal()

    def __init__(self, store: UserReferenceStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self.cards: dict[str, dict] = {}
        self.setWindowTitle("User Library — Raman / FTIR")
        self.resize(720, 440)
        layout = QVBoxLayout(self)
        self.summary = QLabel()
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)

        controls = QHBoxLayout()
        self.add_button = QPushButton("Add reference…")
        self.edit_button = QPushButton("Edit…")
        self.import_button = QPushButton("Import JSON…")
        self.export_button = QPushButton("Export card…")
        for button, handler in (
            (self.add_button, self.add_reference), (self.edit_button, self._edit_selected),
            (self.import_button, self._import_card), (self.export_button, self._export_selected),
        ):
            controls.addWidget(button)
            button.clicked.connect(handler)
        controls.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        controls.addWidget(close)
        layout.addLayout(controls)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Reference", "Formula", "Technique", "Bands"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.itemDoubleClicked.connect(lambda _item: self._edit_selected())
        layout.addWidget(self.table)
        self.refresh()

    def refresh(self, select_id: str | None = None) -> None:
        select_id = select_id or self._selected_id()
        try:
            self.cards = self.store.cards()
            self.summary.setText(f"{len(self.cards)} references · {self.store.path}")
        except (OSError, ValueError) as exc:
            self.cards = {}
            self.summary.setText(f"Could not open {self.store.path}: {exc}")
        self.table.clearContents()
        self.table.setRowCount(len(self.cards))
        for row, (card_id, payload) in enumerate(self.cards.items()):
            metadata = payload.get("metadata") or {}
            band_count = sum(item.get("position_cm1") not in (None, "") for item in payload.get("bands") or [])
            for column, value in enumerate((
                metadata.get("name") or "Untitled reference", metadata.get("formula") or "",
                str(payload.get("kind") or metadata.get("method") or "").upper(), band_count,
            )):
                item = QTableWidgetItem(str(value))
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, card_id)
                self.table.setItem(row, column, item)
            if card_id == select_id:
                self.table.selectRow(row)
        self._update_actions()

    def _selected_id(self) -> str | None:
        selected = self.table.selectedItems()
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_actions(self) -> None:
        selected = self._selected_id() in self.cards
        self.edit_button.setEnabled(selected)
        self.export_button.setEnabled(selected)

    def add_reference(self) -> None:
        self._open_editor(None)

    def _edit_selected(self) -> None:
        card_id = self._selected_id()
        if card_id in self.cards:
            self._open_editor(card_id)

    def _open_editor(self, card_id: str | None) -> None:
        editor = ReferenceEditorDialog(self)
        try:
            original = self.cards.get(card_id) if card_id is not None else None
            if original is not None:
                editor.setWindowTitle("Edit reference")
                editor.load_payload(original)
            if editor.exec() != QDialog.DialogCode.Accepted:
                return
            payload = editor.payload()
            if original is not None:
                # Preserve IDs and metadata not exposed by this editor.
                other_metadata = {
                    key: value for key, value in (original.get("metadata") or {}).items()
                    if key not in editor.fields and key not in {"notes", "origin"}
                }
                payload["metadata"] = {**other_metadata, **payload["metadata"]}
                payload = {**original, **payload}
            self._save(payload, card_id=card_id)
        finally:
            editor.deleteLater()

    def _import_card(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Import reference card", "", _CARD_FILTER)
        if not name:
            return
        try:
            payload = read_reference_card(Path(name))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Reference import failed", str(exc))
            return
        self._save(payload)

    def _save(self, payload: dict, *, card_id: str | None = None) -> None:
        try:
            saved_id = self.store.save(payload, card_id=card_id)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Reference save failed", str(exc))
            return
        self.refresh(saved_id)
        self.libraryChanged.emit()

    def _export_selected(self) -> None:
        card = self.cards.get(self._selected_id())
        if card is None:
            return
        name, _ = QFileDialog.getSaveFileName(self, "Export reference card", "vibrational_reference.json", _CARD_FILTER)
        if not name:
            return
        try:
            target = Path(name)
            if target.resolve() == self.store.path.resolve():
                raise ValueError("Choose a different file from the user library.")
            write_json_atomic(target, card)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Reference export failed", str(exc))
