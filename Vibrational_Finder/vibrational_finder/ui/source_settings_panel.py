from __future__ import annotations

from dataclasses import asdict
from html import escape
import json

from PySide6.QtCore import QSettings, QSize, Signal, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from vibrational_finder.services.source_management import SpectroscopySourceManager
from vibrational_finder.services.editable_reference import USER_LIBRARY_NAME, user_reference_root
from vibrational_finder.services.rest_library_source import RestConnection
from vibrational_finder.services.spectroscopy_source_catalog import ProjectReferenceSource, SpectroscopySourceCatalog
from vibrational_finder.services.user_reference_store import UserReferenceStore
from vibrational_finder.ui.rest_connection_dialog import RestConnectionDialog
from vibrational_finder.ui.user_reference_library import UserReferenceLibraryDialog


_REMOTE_LIBRARIES_SETTING = "sources/remote_catalogs_v1"
_REST_LIBRARIES_SETTING = "sources/rest_catalogs_v1"

_SOURCE_DESCRIPTIONS = {
    USER_LIBRARY_NAME: "Your measured and literature references, stored in one local JSON library.",
    "RRUFF": "Measured mineral Raman and FTIR reference spectra.",
    "ROD": "Measured mineral Raman reference spectra.",
    "OpenSpecy": "Raman and FTIR references for polymers and related materials.",
    "JARVIS-DFT": "Calculated FTIR bands work offline. Cached XML files provide intensities.",
    "Oulu CRD": "Calculated Raman spectra of crystalline materials.",
    "MLROD": "Measured mineral Raman spectra for identification and comparison.",
    "RamanBench": "Raman reference collections from multiple measurement domains.",
    ProjectReferenceSource.name: "References stored in the current project.",
}


class SourceOverviewTable(QTableWidget):
    def sizeHintForColumn(self, column: int) -> int:  # noqa: N802 - Qt API
        hint = super().sizeHintForColumn(column)
        if column not in (0, 1):
            return hint
        metrics = self.fontMetrics()
        texts = (self.item(row, column) for row in range(self.rowCount()))
        cells = max((metrics.horizontalAdvance(item.text()) for item in texts if item), default=0) + 18
        heading = self.horizontalHeaderItem(column)
        header = self.horizontalHeader().fontMetrics().horizontalAdvance(heading.text()) + 20 if heading else 0
        return min(230, max(hint, cells, header))


class SourceActionCard(QFrame):
    def __init__(self, name: str, description: str) -> None:
        super().__init__()
        self.name = name
        self.setProperty("databaseGroup", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 7, 8, 8)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)
        title = QLabel(name)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setProperty("uiRole", "sectionTitle")
        title.setWordWrap(True)
        heading = QHBoxLayout()
        heading.addWidget(title, 1)
        info = QToolButton()
        info.setText("?")
        info.setProperty("databaseHelp", True)
        info.setFixedSize(24, 20)
        info.setAccessibleName(f"About {name}")
        info.setToolTip(description)
        info.clicked.connect(lambda: QToolTip.showText(info.mapToGlobal(info.rect().bottomLeft()), description, info))
        heading.addWidget(info)
        self.grid.addLayout(heading, 0, 0, 1, 2)
        detail = QLabel(description)
        detail.setTextFormat(Qt.TextFormat.PlainText)
        detail.setProperty("uiRole", "muted")
        detail.setWordWrap(True)
        self.grid.addWidget(detail, 1, 0, 1, 2)
        self.actions: dict[str, QPushButton] = {}
        self.packages = QComboBox(self)
        self.packages.setAccessibleName(f"{name} package")
        self.packages.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.packages.hide()
        self.grid.addWidget(self.packages, 2, 0, 1, 2)

    def add_action(self, key: str, label: str, callback, *, available: bool = True) -> QPushButton:
        offset, column = divmod(len(self.actions), 2)
        button = QPushButton(label)
        button.setAccessibleName(f"{self.name}: {label}")
        button.setProperty("available", available)
        if key in {"update", "add_reference"}:
            button.setProperty("databaseAction", "emphasis")
        elif key in {"clear", "clear_index"}:
            button.setProperty("databaseAction", "clear")
        button.clicked.connect(lambda _checked=False: callback())
        self.grid.addWidget(button, offset + 3, column)
        self.actions[key] = button
        return button

    def set_busy(self, busy: bool) -> None:
        for key, button in self.actions.items():
            button.setEnabled(bool(button.property("available")) and (not busy or key in {"website", "manage"}))
        self.packages.setEnabled(not busy)


class SourceSettingsPanel(QWidget):
    sourcesChanged = Signal()
    updateRequested = Signal(str, str)
    clearCacheRequested = Signal(str)
    buildIndexRequested = Signal(str)
    clearIndexRequested = Signal(str)

    def __init__(
        self, catalog: SpectroscopySourceCatalog, parent: QWidget | None = None, *,
        settings: QSettings | None = None, defer_refresh: bool = False,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.manager = SpectroscopySourceManager(catalog)
        self.settings = settings
        self._populated = False
        self._operation_running = False
        self._user_library_dialog: UserReferenceLibraryDialog | None = None
        self.source_action_cards: dict[str, SourceActionCard] = {}
        self.source_checkboxes: dict[str, QCheckBox] = {}
        self._card_column_count = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        filters = QHBoxLayout()
        self.source_filter = QComboBox()
        self.source_filter.setObjectName("sourceGroupFilter")
        self.source_filter.addItem("All sources", "all")
        self.source_filter.addItem("Built-in", "builtin")
        self.source_filter.addItem("My sources", "user")
        filters.addWidget(QLabel("Show:"))
        filters.addWidget(self.source_filter)
        filters.addStretch(1)
        self.refresh_sources_button = QPushButton("Refresh")
        self.refresh_sources_button.setObjectName("refreshSourcesButton")
        filters.addWidget(self.refresh_sources_button)
        layout.addLayout(filters)

        self._connections_card = SourceActionCard(
            "Additional databases", "Connect local folders, CSV lists, JSON catalogs or REST APIs.",
        )
        self.add_user_library_button = self._connections_card.add_action("csv", "CSV library…", self._choose_user_library)
        self.add_user_library_button.setObjectName("addUserLibraryButton")
        self.add_folder_library_button = self._connections_card.add_action("folder", "Folder…", self._choose_folder_library)
        self.add_folder_library_button.setObjectName("addFolderLibraryButton")
        self.add_url_button = self._connections_card.add_action("url", "JSON URL…", self._choose_url_library)
        self.add_url_button.setObjectName("addUrlLibraryButton")
        self.add_rest_button = self._connections_card.add_action("rest", "REST API…", self._choose_rest_library)
        self.add_rest_button.setObjectName("addRestLibraryButton")

        self.source_table = SourceOverviewTable(0, 3)
        self.source_table.setObjectName("sourceSettingsTable")
        self.source_table.setHorizontalHeaderLabels(["Database", "Status", "Details"])
        self.source_table.setAlternatingRowColors(True)
        self.source_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.source_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.source_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.source_table.verticalHeader().hide()
        header = self.source_table.horizontalHeader()
        for column in (0, 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        overview = QHBoxLayout()
        overview.addWidget(self.source_table, 2)
        search_group = QGroupBox("Databases used for search")
        search_group.setProperty("databaseGroup", True)
        search_layout = QVBoxLayout(search_group)
        search_scroll = QScrollArea()
        search_scroll.setProperty("databaseScroll", True)
        search_scroll.setWidgetResizable(True)
        search_body = QWidget()
        search_body.setObjectName("databaseScrollBody")
        self._search_options = QGridLayout(search_body)
        self._search_options.setContentsMargins(0, 0, 0, 0)
        self._search_options.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._search_options.setColumnStretch(0, 1)
        self._search_options.setColumnStretch(1, 1)
        search_scroll.setWidget(search_body)
        search_layout.addWidget(search_scroll)
        overview.addWidget(search_group, 1)
        layout.addLayout(overview, 2)

        title = QLabel("Database management")
        title.setProperty("uiRole", "sectionTitle")
        layout.addWidget(title)
        management = QScrollArea()
        management.setProperty("databaseScroll", True)
        management.setWidgetResizable(True)
        cards = QWidget()
        cards.setObjectName("databaseScrollBody")
        self._card_columns = QHBoxLayout(cards)
        self._card_columns.setContentsMargins(2, 0, 8, 4)
        management.setWidget(cards)
        layout.addWidget(management, 3)
        self.operation_status = QLabel("Downloads and index updates are started from each database card.")
        self.operation_status.setObjectName("sourceOperationStatus")
        self.operation_status.setTextFormat(Qt.TextFormat.PlainText)
        self.operation_status.setWordWrap(True)
        layout.addWidget(self.operation_status)

        self.source_filter.currentIndexChanged.connect(lambda _index: self.refresh())
        self.refresh_sources_button.clicked.connect(self.refresh)
        self._restore_remote_libraries()
        if not defer_refresh:
            self.refresh()

    def ensure_populated(self) -> None:
        if not self._populated:
            self.refresh()

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        hint = super().minimumSizeHint()
        return QSize(min(hint.width(), 220), hint.height())

    @staticmethod
    def _kind_label(kinds) -> str:
        labels = {"raman": "Raman", "ftir": "FTIR", "unknown": "Unknown"}
        return ", ".join(labels.get(kind.value, kind.value) for kind in kinds)

    def refresh(self) -> None:
        selected_name = self.selected_source_name()
        selected_packages = {name: card.packages.currentData() for name, card in self.source_action_cards.items()}
        mode = self.source_filter.currentData()
        names = [
            name for name in self.catalog.names()
            if mode == "all" or (mode == "user") == (
                self.catalog.descriptor(name).user_managed or name == ProjectReferenceSource.name
            )
        ]
        for name in names:
            self.catalog.refresh(name)
        rows = self.catalog.status_rows(names)
        while self._search_options.count():
            widget = self._search_options.takeAt(0).widget()
            widget.hide()
            widget.deleteLater()
        for card in self.source_action_cards.values():
            card.hide()
            card.deleteLater()
        self.source_checkboxes.clear()
        self.source_action_cards.clear()
        self.source_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            name = row.name
            count = f"{row.count} reference{'s' if row.count != 1 else ''}"
            details = " · ".join(part for part in (row.detail, self._kind_label(row.kinds), count) if part)
            values = (name, row.state.capitalize(), details)
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                tooltip = "<br>".join(escape(part) for part in (value, row.path or row.website) if part)
                item.setToolTip(f"<qt>{tooltip}</qt>")
                self.source_table.setItem(row_index, column, item)
            toggle = QCheckBox(name)
            toggle.setChecked(row.enabled)
            toggle.setToolTip("Use in search. This does not download data.")
            toggle.toggled.connect(lambda checked, name=name: self._set_search_source(name, checked))
            self.source_checkboxes[name] = toggle
            self._search_options.addWidget(toggle, *divmod(row_index, 2))
            card = self._build_source_card(name, selected_packages.get(name))
            self.source_action_cards[name] = card
        self._place_source_cards(force=True)
        target_row = 0 if rows else -1
        if selected_name:
            for row_index, row in enumerate(rows):
                if row.name == selected_name:
                    target_row = row_index
                    break
        if target_row >= 0:
            self.source_table.selectRow(target_row)
        self._apply_operation_state()
        self._populated = True

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._place_source_cards()

    def _place_source_cards(self, *, force: bool = False) -> None:
        cards = [self._connections_card, *self.source_action_cards.values()]
        count = min(len(cards), max(1, min(5, (self.width() - 20) // 255)))
        if not force and self._card_column_count == count:
            return
        self._card_column_count = count
        while self._card_columns.count():
            column = self._card_columns.takeAt(0).layout()
            while column.count():
                column.takeAt(0)
            column.deleteLater()
        columns = [QVBoxLayout() for _ in range(count)]
        heights = [0] * count
        for column in columns:
            self._card_columns.addLayout(column, 1)
        for card in cards:
            index = min(range(count), key=heights.__getitem__)
            columns[index].addWidget(card)
            heights[index] += card.sizeHint().height() + 6
        for column in columns:
            column.addStretch(1)

    def set_catalog(self, catalog: SpectroscopySourceCatalog) -> None:
        self.catalog = catalog
        self.manager = SpectroscopySourceManager(catalog)
        if self._populated:
            self.refresh()

    def _user_library(self) -> UserReferenceLibraryDialog:
        if self._user_library_dialog is None:
            self._user_library_dialog = UserReferenceLibraryDialog(UserReferenceStore(user_reference_root()), self)
            self._user_library_dialog.libraryChanged.connect(self._user_library_changed)
        return self._user_library_dialog

    def add_reference(self) -> None:
        self._user_library().add_reference()

    def manage_user_library(self) -> UserReferenceLibraryDialog:
        dialog = self._user_library()
        dialog.refresh()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return dialog

    def _user_library_changed(self) -> None:
        self.sourcesChanged.emit()
        self.refresh()

    def selected_source_name(self) -> str | None:
        row = self.source_table.currentRow()
        item = self.source_table.item(row, 0) if row >= 0 else None
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text())

    def _build_source_card(self, name: str, selected_package: str | None) -> SourceActionCard:
        descriptor = self.catalog.descriptor(name)
        description = _SOURCE_DESCRIPTIONS.get(name) or (
            "Remote spectroscopy library with a local cache." if descriptor.remote_url
            else "Local reference data connected to this Finder."
        )
        card = SourceActionCard(name, description)
        if name == USER_LIBRARY_NAME:
            card.add_action("add_reference", "Add reference…", self.add_reference)
            card.add_action("manage", "Manage…", self.manage_user_library)
            return card

        try:
            capabilities = self.manager.capabilities(name)
        except Exception:
            # The source error is reported in its overview row.
            capabilities = None
        if capabilities is not None:
            for package in capabilities.packages:
                suffix = " (cached)" if package.cached else ""
                card.packages.addItem(f"{package.label}{suffix}", package.key)
            if capabilities.packages:
                card.packages.setCurrentIndex(max(0, card.packages.findData(selected_package)))
                card.packages.show()
            if capabilities.can_update:
                label = "Update…" if any(package.cached for package in capabilities.packages) else "Download…"
                card.add_action("update", label, lambda: self.updateRequested.emit(
                    name, str(card.packages.currentData() or ""),
                ))
            if capabilities.can_build_index:
                available = not descriptor.remote_url or any(package.cached for package in capabilities.packages)
                card.add_action("build_index", "Build index", lambda: self.buildIndexRequested.emit(name),
                                available=available)
                if not available:
                    card.actions["build_index"].setToolTip("Download this catalog first.")
            if capabilities.can_clear:
                card.add_action("clear", "Clear cache…", lambda: self._request_clear_cache(name))
            if capabilities.can_clear_index:
                card.add_action("clear_index", "Clear index…", lambda: self._request_clear_index(name))
        if descriptor.website:
            card.add_action("website", "Source page", lambda: QDesktopServices.openUrl(QUrl(descriptor.website)))
        if descriptor.rest_connection is not None:
            card.add_action("edit", "Edit API…", lambda: self._configure_rest_library(descriptor.rest_connection))
        if descriptor.remote_url:
            card.add_action("disconnect", "Disconnect…", lambda: self._disconnect_url_library(name))
        if not card.actions:
            hint = QLabel("No local management actions.")
            hint.setWordWrap(True)
            card.grid.addWidget(hint, 3, 0, 1, 2)
        return card

    def _apply_operation_state(self) -> None:
        for button in (
            self.refresh_sources_button, self.source_filter, self.add_url_button, self.add_rest_button,
            self.add_user_library_button, self.add_folder_library_button,
        ):
            button.setEnabled(not self._operation_running)
        for card in self.source_action_cards.values():
            card.set_busy(self._operation_running)

    def _confirm(self, title: str, message: str) -> bool:
        return QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def _request_clear_cache(self, name: str) -> None:
        if self._confirm("Clear source cache", f"Delete downloaded cache files for {name}?"):
            self.clearCacheRequested.emit(name)

    def _request_clear_index(self, name: str) -> None:
        if self._confirm("Clear line index", f"Delete the derived line index for {name}?"):
            self.clearIndexRequested.emit(name)

    def set_operation_pending(self, name: str, operation: str) -> None:
        labels = {
            "update": "Updating",
            "clear": "Clearing cache",
            "build_index": "Building line index",
            "clear_index": "Clearing line index",
        }
        self._operation_running = True
        self.operation_status.setText(f"{labels.get(operation, operation)} {name}…")
        self._apply_operation_state()

    def set_operation_succeeded(self, name: str, operation: str, message: str = "") -> None:
        self._operation_running = False
        self.refresh()
        self.operation_status.setText(message or f"{name}: {operation} complete")

    def set_operation_failed(self, name: str, operation: str, message: str) -> None:
        self._operation_running = False
        self.operation_status.setText(f"{name}: {message}")
        self._apply_operation_state()

    def set_operation_cancelled(self, name: str, operation: str) -> None:
        self._operation_running = False
        self.operation_status.setText(f"{name}: {operation} cancelled")
        self._apply_operation_state()

    def _set_search_source(self, name: str, enabled: bool) -> None:
        self.catalog.set_enabled(name, enabled)
        self.sourcesChanged.emit()

    def _choose_user_library(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Add spectroscopy library", "", "CSV libraries (*.csv);;All files (*)")
        if path:
            self.catalog.add_user_library(path)
            self.refresh()
            self.sourcesChanged.emit()

    def _choose_folder_library(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add spectroscopy folder")
        if path:
            self.catalog.add_folder_library(path)
            self.refresh()
            self.sourcesChanged.emit()

    def _saved_connections(self, key: str) -> list:
        if self.settings is None:
            return []
        try:
            values = json.loads(self.settings.value(key, "[]", type=str))
        except (ValueError, TypeError):
            return []
        return values if isinstance(values, list) else []

    def _restore_remote_libraries(self) -> None:
        for url in self._saved_connections(_REMOTE_LIBRARIES_SETTING):
            if isinstance(url, str):
                try:
                    self.catalog.add_remote_library(url)
                except ValueError:
                    continue
        for config in self._saved_connections(_REST_LIBRARIES_SETTING):
            if isinstance(config, dict):
                try:
                    self.catalog.add_rest_library(RestConnection(**config))
                except (TypeError, ValueError):
                    continue

    def _save_remote_libraries(self) -> None:
        if self.settings is not None:
            self.settings.setValue(_REMOTE_LIBRARIES_SETTING, json.dumps(self.catalog.remote_library_urls()))
            self.settings.setValue(
                _REST_LIBRARIES_SETTING, json.dumps([asdict(config) for config in self.catalog.rest_connections()]),
            )

    def _choose_url_library(self) -> None:
        url, accepted = QInputDialog.getText(
            self, "Add spectroscopy catalog", "Direct HTTPS URL of an IR/Raman JSON catalog:",
        )
        if not accepted:
            return
        try:
            name = self.catalog.add_remote_library(url)
        except ValueError as exc:
            self.operation_status.setText(str(exc))
            return
        self._show_connected_library(
            name, "Catalog connected. Download it, build the index, then tick to use it in search.",
        )

    def _choose_rest_library(self) -> None:
        self._configure_rest_library()

    def _configure_rest_library(self, config: RestConnection | None = None) -> None:
        dialog = RestConnectionDialog(self, config)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        connection = dialog.connection
        dialog.deleteLater()
        if not accepted or connection is None:
            return
        name = self.catalog.add_rest_library(connection)
        self._show_connected_library(
            name,
            "REST mapping saved. Download / update to fetch it, then build the local index.",
        )

    def _show_connected_library(self, name: str, message: str) -> None:
        self._save_remote_libraries()
        group = self.source_filter.findData("user")
        if self.source_filter.currentIndex() != group:
            self.source_filter.setCurrentIndex(group)
        else:
            self.refresh()
        for row in range(self.source_table.rowCount()):
            if self.source_table.item(row, 0).text() == name:
                self.source_table.selectRow(row)
                break
        self.operation_status.setText(message)
        self.sourcesChanged.emit()

    def _disconnect_url_library(self, name: str) -> None:
        if self.catalog.descriptor(name).remote_url and self._confirm(
            "Disconnect library", "Remove this source from Finder? Downloaded cache files will be kept.",
        ):
            self.catalog.remove_remote_library(name)
            self._save_remote_libraries()
            self.refresh()
            self.operation_status.setText("Library disconnected. Downloaded files were kept.")
            self.sourcesChanged.emit()

