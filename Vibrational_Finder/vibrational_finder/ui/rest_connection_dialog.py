from __future__ import annotations

from dataclasses import asdict, fields
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vibrational_finder.services.rest_library_source import RestConnection, RestFieldMapping
from vibrational_finder.services.rest_mapping_preview import MappingRow, check_rest_mapping, check_rest_profile


class RestConnectionDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, config: RestConnection | None = None) -> None:
        super().__init__(parent)
        self.connection: RestConnection | None = None
        self.setWindowTitle("Edit REST source" if config else "Add REST source")
        self.resize(710, 615)
        self.inputs: dict[str, QLineEdit] = {}
        values = asdict(config) if config else {
            "records_path": "results", "id_path": "id", "name_path": "name", "formula_path": "formula",
            "x_path": "x", "y_path": "y",
        }
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        connection_page = QWidget()
        self.tabs.addTab(connection_page, "Connection")
        connection_layout = QVBoxLayout(connection_page)
        hint = QLabel(
            "Map fields from a public HTTPS JSON API using dotted paths, for example data.results. "
            "Adding this source does not contact the server."
        )
        hint.setWordWrap(True)
        connection_layout.addWidget(hint)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        connection_layout.addLayout(form)
        for key, label, placeholder in (
            ("url", "HTTPS endpoint", "https://example.org/api/spectra?limit=100"),
            ("title", "Library name", "Optional"),
            ("license", "Data license", "Optional"),
            ("records_path", "Records array", "Blank if the whole JSON response is an array"),
            ("next_path", "Next-page URL", "Optional, e.g. links.next"),
            ("id_path", "ID", "id"),
            ("name_path", "Name", "material.name"),
            ("formula_path", "Formula", "Optional"),
            ("kind_path", "Spectrum type field", "Optional; otherwise use the fixed type below"),
            ("profile_path", "Profile URL field", "Optional; otherwise use x/y from the record"),
            ("x_path", "X, in cm⁻¹", "spectrum.wavenumbers"),
            ("y_path", "Intensity", "spectrum.intensities"),
        ):
            field = QLineEdit(values.get(key, ""))
            field.setPlaceholderText(placeholder)
            field.setMaxLength(2048 if key == "url" else 200)
            field.setReadOnly(key == "url" and config is not None)
            self.inputs[key] = field
            form.addRow(label, field)
        self.default_kind = QComboBox()
        self.default_kind.addItem("Raman", "raman")
        self.default_kind.addItem("FTIR", "ftir")
        self.default_kind.setCurrentIndex(self.default_kind.findData(values.get("default_kind", "raman")))
        form.addRow("Fixed type", self.default_kind)
        connection_layout.addStretch(1)
        self._add_preview_tab()
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _values(self) -> dict[str, str]:
        return {**{key: field.text() for key, field in self.inputs.items()}, "default_kind": self.default_kind.currentData()}

    def _add_preview_tab(self) -> None:
        page = QWidget()
        self.tabs.addTab(page, "Check mapping")
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Paste a sample JSON response and check it against the fields on the Connection tab. "
            "The sample is not saved, and links are never opened."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        controls = QHBoxLayout()
        self.preview_input_kind = QComboBox()
        self.preview_input_kind.addItem("Records response", "records")
        self.preview_input_kind.addItem("Separate profile response", "profile")
        controls.addWidget(QLabel("Sample type:"))
        controls.addWidget(self.preview_input_kind)
        controls.addStretch(1)
        self.check_mapping_button = QPushButton("Check pasted JSON")
        self.check_mapping_button.setAutoDefault(False)
        controls.addWidget(self.check_mapping_button)
        layout.addLayout(controls)
        self.preview_summary = QLabel("Paste a response below to check the mapping.")
        self.preview_summary.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_summary.setWordWrap(True)
        layout.addWidget(self.preview_summary)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.preview_editors = QStackedWidget()
        self.pasted_json = QPlainTextEdit()
        self.pasted_json.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.pasted_json.setPlaceholderText(
            '{"results": [{"id": 1, "name": "Quartz", "x": [100, 200, 300], "y": [0, 1, 0]}]}'
        )
        self.pasted_profile_json = QPlainTextEdit()
        self.pasted_profile_json.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.pasted_profile_json.setPlaceholderText('{"x": [100, 200, 300], "y": [0, 1, 0]}')
        self.preview_editors.addWidget(self.pasted_json)
        self.preview_editors.addWidget(self.pasted_profile_json)
        self.preview_table = QTableWidget(0, 5)
        self.preview_table.setHorizontalHeaderLabels(["Record", "Field", "JSON path", "Status", "Result"])
        self.preview_table.verticalHeader().hide()
        self.preview_table.setAlternatingRowColors(True)
        for section, width in enumerate((66, 98, 140, 100)):
            self.preview_table.setColumnWidth(section, width)
        self.preview_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.preview_editors)
        splitter.addWidget(self.preview_table)
        splitter.setSizes([130, 250])
        layout.addWidget(splitter, 1)

        self.check_mapping_button.clicked.connect(self._check_mapping)
        self.preview_input_kind.currentIndexChanged.connect(self._switch_preview_input)
        self.pasted_json.textChanged.connect(self._invalidate_preview)
        self.pasted_profile_json.textChanged.connect(self._invalidate_preview)
        self.default_kind.currentIndexChanged.connect(self._invalidate_preview)
        for field in self.inputs.values():
            field.textChanged.connect(self._invalidate_preview)

    def _switch_preview_input(self, index: int) -> None:
        self.preview_editors.setCurrentIndex(index)
        self.preview_table.setRowCount(0)
        self.preview_summary.setText(
            "Paste a profile response to check the X and Y paths."
            if self.preview_input_kind.currentData() == "profile"
            else "Paste a response below to check the mapping."
        )

    def _invalidate_preview(self) -> None:
        if self.preview_table.rowCount():
            self.preview_table.setRowCount(0)
            self.preview_summary.setText("Input changed. Check the mapping again.")

    def _check_mapping(self) -> None:
        values = self._values()
        if self.preview_input_kind.currentData() == "profile":
            rows = check_rest_profile(
                self.pasted_profile_json.toPlainText(), x_path=values["x_path"], y_path=values["y_path"],
            )
            self._show_preview(rows)
            errors = sum(row.level == "error" for row in rows)
            self.preview_summary.setText(
                f"Profile check: {errors} errors. See the details below."
                if errors else "Profile checked: X and Y are usable."
            )
            return
        try:
            mapping = RestFieldMapping(**{field.name: values[field.name] for field in fields(RestFieldMapping)})
        except ValueError as exc:
            self._show_preview([MappingRow(None, "Mapping", "", "error", str(exc))])
            self.preview_summary.setText("Fix the mapping on the Connection tab and check again.")
            return
        report = check_rest_mapping(self.pasted_json.toPlainText(), mapping, endpoint=values["url"])
        self._show_preview(report.rows)
        response_errors = sum(row.record is None and row.level == "error" for row in report.rows)
        summary = (
            f"Checked {report.checked_records:,} of {report.total_records:,} records · "
            f"{report.invalid_records:,} with errors"
        )
        if response_errors:
            summary += f" · {response_errors} response-level errors"
        if report.unchecked_profiles:
            summary += f" · {report.unchecked_profiles} linked profiles not checked"
        self.preview_summary.setText(summary)

    def _show_preview(self, rows: list[MappingRow]) -> None:
        labels = {"ok": "Found", "error": "Error", "unchecked": "Not checked", "optional": "Optional"}
        table = self.preview_table
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (str(row.record) if row.record is not None else "Response", row.field, row.path,
                     labels[row.level], row.detail)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setToolTip(f"<qt>{escape(text)}</qt>" if text else "")
                if row.level == "error" and column == 3:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                table.setItem(index, column, item)

    def accept(self) -> None:
        try:
            self.connection = RestConnection(**self._values())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.tabs.setCurrentIndex(0)
            return
        super().accept()
