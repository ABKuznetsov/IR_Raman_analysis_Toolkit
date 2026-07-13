from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from finder_core.models import SignalKind
from finder_core.data_sources import SourceQuery
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.io import guess_spectrum_metadata, load_xy_spectrum, supported_spectrum_extensions
from vibrational_finder.models import ReferenceSpectrum, SpectralBand
from vibrational_finder.services.cif_structure_source import CifStructureSource
from vibrational_finder.services.preprocessing_service import (
    auto_smoothing_window,
    estimate_background,
    remove_narrow_spikes,
    smooth_spectrum_curve,
)
from vibrational_finder.ui.preprocessing_panels import (
    BackgroundRemovalPanel,
    DespikePanel,
    SmoothPanel,
    background_method_label,
    preprocessing_panel_style,
)
from vibrational_finder.ui.vibrational_plot import create_vibrational_plot_widget


def _dialog_button_style(background: str, border: str) -> str:
    return (
        "QPushButton {"
        f"background: {background}; border: 1px solid {border}; color: #ffffff;"
        "border-radius: 7px; padding: 8px 12px; font-weight: 700;"
        "}"
        f"QPushButton:hover {{ background: {border}; }}"
    )


def blank_reference_template(kind: SignalKind | str = SignalKind.UNKNOWN) -> dict:
    method = kind.value if isinstance(kind, SignalKind) else str(kind or "raman").lower()
    if method in {"ir", "infrared"}:
        method = "ftir"
    if method not in {"raman", "ftir"}:
        method = ""
    return {
        "format": "vibrational-reference",
        "version": 1,
        "kind": method,
        "metadata": {
            "name": "",
            "formula": "",
            "alternative_name": "",
            "origin": "experimental",
            "laser_nm": "" if method == "raman" else "",
            "temperature_K": "",
            "pressure": "",
            "sample_form": "",
            "orientation": "",
            "polarization": "",
            "instrument": "",
            "resolution": "",
            "operator": "",
            "laboratory": "",
            "measurement_date": "",
            "doi": "",
            "citation": "",
            "notes": "",
        },
        "profile": None,
        "bands": [
            {
                "position_cm1": None,
                "intensity": None,
                "fwhm_cm1": None,
                "mode": "",
                "symmetry": "",
                "assignment": "",
                "polarization": "",
                "orientation": "",
                "confidence": "reported / estimated / inferred / unknown",
                "comment": "Article page, table, figure, or note",
            }
        ],
    }


def _spectrum_file_filter() -> str:
    globs = " ".join(f"*{extension}" for extension in supported_spectrum_extensions())
    return (
        f"Spectra ({globs});;"
        "Text spectra (*.txt *.xy *.csv *.tsv *.dat *.asc *.ascii);;"
        "Spreadsheets (*.xlsx);;"
        "JCAMP-DX (*.jdx *.dx);;"
        "Vendor spectra (*.spc *.sp *.spa *.0 *.1 *.2 *.wdf *.ngs *.spe *.cha);;"
        "All files (*)"
    )


def _guess_label(kind: SignalKind) -> str:
    if kind == SignalKind.RAMAN:
        return "Raman"
    if kind == SignalKind.FTIR:
        return "FTIR"
    return "Unknown"


def _guess_summary(path: str | Path, guess) -> str:
    details = [
        f"method: {_guess_label(guess.kind)}",
        f"x: {guess.x_unit}",
        f"y: {guess.y_unit}",
        f"peaks: {guess.peak_direction}",
        f"confidence: {guess.confidence:.0%}",
    ]
    if guess.x_reversed:
        details.append("x reversed")
    if guess.warnings:
        details.append("warnings: " + "; ".join(guess.warnings))
    return f"{Path(path).name} -> " + ", ".join(details)


class ImportMethodDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import experimental spectra")
        self.setModal(True)
        self.resize(560, 220)
        self.selected_kind = SignalKind.UNKNOWN
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        methods = QHBoxLayout()
        methods.setSpacing(12)
        methods.addWidget(self._spectrum_panel(SignalKind.RAMAN), 1)
        methods.addWidget(self._spectrum_panel(SignalKind.FTIR), 1)
        layout.addLayout(methods, 1)
        close = QPushButton("Cancel")
        close.setStyleSheet(_dialog_button_style("#5f6368", "#8a8d91"))
        close.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)

    def _spectrum_panel(self, kind: SignalKind) -> QWidget:
        panel = QWidget()
        panel.setObjectName("loadMethodPanel")
        panel.setStyleSheet(
            "#loadMethodPanel { border: 1px solid #526273; border-radius: 8px; padding: 8px; }"
        )
        layout = QVBoxLayout(panel)
        title = "Raman" if kind == SignalKind.RAMAN else "FTIR"
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet("font-weight: 800; font-size: 16px;")
        button = QPushButton("Load spectrum file")
        button.setMinimumHeight(58)
        button.setStyleSheet(
            _dialog_button_style("#2367a5", "#5a9bd8")
            if kind == SignalKind.RAMAN
            else _dialog_button_style("#0b8043", "#35a96c")
        )
        button.clicked.connect(lambda: self._choose(kind))
        layout.addWidget(caption)
        layout.addWidget(button)
        return panel

    def _choose(self, kind: SignalKind) -> None:
        self.selected_kind = kind
        self.accept()


class ReferenceLoadDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, *, include_manage: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Load references")
        self.setModal(True)
        self.resize(760, 420)
        self.selected_kind = SignalKind.UNKNOWN
        self.selected_action = ""
        self.include_manage = include_manage
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        methods = QHBoxLayout()
        methods.setSpacing(12)
        methods.addWidget(self._method_panel(SignalKind.RAMAN), 1)
        methods.addWidget(self._method_panel(SignalKind.FTIR), 1)
        layout.addLayout(methods, 1)

        template_row = QHBoxLayout()
        save_template = QPushButton("Download blank template")
        copy_template = QPushButton("Copy template JSON")
        manage = QPushButton("Open reference list")
        close = QPushButton("Cancel")
        save_template.setStyleSheet(_dialog_button_style("#e9328f", "#ff65b3"))
        copy_template.setStyleSheet(_dialog_button_style("#7b4fb3", "#a782d8"))
        manage.setStyleSheet(_dialog_button_style("#2367a5", "#5a9bd8"))
        close.setStyleSheet(_dialog_button_style("#5f6368", "#8a8d91"))
        save_template.clicked.connect(self._save_blank_template)
        copy_template.clicked.connect(self._copy_blank_template)
        manage.clicked.connect(lambda: self._choose(SignalKind.UNKNOWN, "manage"))
        close.clicked.connect(self.reject)
        template_row.addWidget(save_template)
        template_row.addWidget(copy_template)
        if self.include_manage:
            template_row.addWidget(manage)
        template_row.addStretch(1)
        template_row.addWidget(close)
        layout.addLayout(template_row)

        hint = QLabel(
            "Instruction: download or copy the template, find an article, ask an AI assistant to fill the JSON, "
            "then check the values, modes and metadata before loading it."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

    def _method_panel(self, kind: SignalKind) -> QWidget:
        panel = QWidget()
        panel.setObjectName("loadMethodPanel")
        panel.setStyleSheet(
            "#loadMethodPanel { border: 1px solid #526273; border-radius: 8px; padding: 8px; }"
        )
        layout = QGridLayout(panel)
        layout.setColumnStretch(0, 1)
        title = "Raman" if kind == SignalKind.RAMAN else "FTIR"
        caption = QLabel(title)
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption.setStyleSheet("font-weight: 800; font-size: 16px;")
        layout.addWidget(caption, 0, 0, 1, 2)

        spectrum = QPushButton("Load reference spectrum")
        template = QPushButton("Load filled template")
        spectrum.setMinimumHeight(54)
        template.setMinimumHeight(54)
        if kind == SignalKind.RAMAN:
            spectrum.setStyleSheet(_dialog_button_style("#2367a5", "#5a9bd8"))
        else:
            spectrum.setStyleSheet(_dialog_button_style("#0b8043", "#35a96c"))
        template.setStyleSheet(_dialog_button_style("#e9328f", "#ff65b3"))
        spectrum.clicked.connect(lambda: self._choose(kind, "spectrum"))
        template.clicked.connect(lambda: self._choose(kind, "template"))
        layout.addWidget(spectrum, 1, 0, 1, 2)
        layout.addWidget(template, 2, 0, 1, 2)

        if kind == SignalKind.FTIR:
            cif = QPushButton("Calculate IR hints from CIF")
            cif.setMinimumHeight(46)
            cif.setStyleSheet(_dialog_button_style("#7b4fb3", "#a782d8"))
            cif.clicked.connect(lambda: self._choose(kind, "cif"))
            layout.addWidget(cif, 3, 0, 1, 2)
            note = QLabel("CIF mode is a fallback structural hint, not DFT-quality IR calculation.")
            note.setWordWrap(True)
            layout.addWidget(note, 4, 0, 1, 2)
        else:
            note = QLabel("Use a spectrum file for measured data or a filled template for literature peak tables.")
            note.setWordWrap(True)
            layout.addWidget(note, 3, 0, 1, 2)
        return panel

    def _choose(self, kind: SignalKind, action: str) -> None:
        self.selected_kind = kind
        self.selected_action = action
        self.accept()

    def _save_blank_template(self) -> None:
        default_name = "vibrational_reference_template.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save blank reference template", default_name, "JSON templates (*.json)")
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(blank_reference_template(), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Template save failed", str(exc))

    def _copy_blank_template(self) -> None:
        text = json.dumps(blank_reference_template(), ensure_ascii=False, indent=2)
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)
        QMessageBox.information(self, "Template copied", "Blank reference template JSON was copied to the clipboard.")


class ReferenceEditorDialog(QDialog):
    BAND_HEADERS = [
        "Position, cm-1",
        "Intensity",
        "FWHM, cm-1",
        "Mode",
        "Symmetry",
        "Assignment",
        "Polarization",
        "Orientation",
        "Confidence",
        "Source / comment",
    ]

    def __init__(self, parent: QWidget | None = None, *, default_kind: SignalKind = SignalKind.RAMAN, laser_nm: float = 0.0) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create reference")
        self.resize(1250, 820)
        self.profile: ReferenceSpectrum | None = None
        self._original_profile: ReferenceSpectrum | None = None
        self._plot_has_content = False
        self._preprocessing_panel: QWidget | None = None
        self._preprocessing_panel_key = ""
        self._preprocessing_cancel_callback = None
        self.profile_path = ""
        self.fields: dict[str, QLineEdit] = {}
        self._build_ui(default_kind, laser_nm)

    def _build_ui(self, default_kind: SignalKind, laser_nm: float) -> None:
        root = QVBoxLayout(self)
        load_data = QPushButton("Load")
        import_peaks = QPushButton("Load peak table")
        auto_detect = QPushButton("Auto detect")
        smooth = QPushButton("Smooth")
        remove_background = QPushButton("Remove background")
        despike = QPushButton("Despike")
        reset_profile = QPushButton("Reset profile")
        detect = QPushButton("Detect peaks from spectrum")
        add_row = QPushButton("Add manual peak")
        remove_rows = QPushButton("Remove selected peaks")
        load_data.setMinimumWidth(170)
        load_data.setMinimumHeight(46)
        load_data.setStyleSheet(_dialog_button_style("#2367a5", "#5a9bd8"))
        auto_detect.setStyleSheet(_dialog_button_style("#0b8043", "#35a96c"))
        smooth.setStyleSheet(_dialog_button_style("#2367a5", "#5a9bd8"))
        remove_background.setStyleSheet(_dialog_button_style("#8a5a16", "#c68a2e"))
        despike.setStyleSheet(_dialog_button_style("#5f6368", "#8a8d91"))
        reset_profile.setStyleSheet(_dialog_button_style("#7b4fb3", "#a782d8"))
        detect.setStyleSheet(_dialog_button_style("#8a5a16", "#c68a2e"))
        add_row.setStyleSheet(_dialog_button_style("#0b8043", "#35a96c"))
        remove_rows.setStyleSheet(_dialog_button_style("#5f6368", "#8a8d91"))
        import_peaks.setStyleSheet(_dialog_button_style("#2367a5", "#5a9bd8"))
        load_data.clicked.connect(self._show_load_dialog)
        import_peaks.clicked.connect(self._import_peak_table)
        auto_detect.clicked.connect(self._auto_detect_profile)
        smooth.clicked.connect(self._smooth_profile)
        remove_background.clicked.connect(self._remove_profile_background)
        despike.clicked.connect(self._despike_profile)
        reset_profile.clicked.connect(self._reset_profile)
        detect.clicked.connect(self._detect_peaks)
        add_row.clicked.connect(self._add_band_row)
        remove_rows.clicked.connect(self._remove_selected_rows)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(12)
        action_row.addWidget(load_data)
        action_row.addStretch(1)
        root.addLayout(action_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        metadata = QWidget()
        metadata.setMinimumWidth(420)
        form = QFormLayout(metadata)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for key, label in (
            ("name", "Compound / reference name"),
            ("formula", "Formula"),
            ("alternative_name", "Alternative name"),
        ):
            self.fields[key] = QLineEdit()
            form.addRow(label, self.fields[key])
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Raman", SignalKind.RAMAN)
        self.kind_combo.addItem("FTIR", SignalKind.FTIR)
        self.kind_combo.setCurrentIndex(0 if default_kind != SignalKind.FTIR else 1)
        form.addRow("Method", self.kind_combo)
        self.origin_combo = QComboBox()
        self.origin_combo.addItem("Experimental", "experimental")
        self.origin_combo.addItem("Calculated", "calculated")
        form.addRow("Reference type", self.origin_combo)
        for key, label, initial in (
            ("laser_nm", "Laser wavelength, nm", f"{laser_nm:g}" if laser_nm > 0 else ""),
            ("temperature_K", "Temperature, K", ""),
            ("pressure", "Pressure", ""),
            ("sample_form", "Sample form", ""),
            ("orientation", "Orientation", ""),
            ("polarization", "Polarization", ""),
            ("instrument", "Instrument", ""),
            ("resolution", "Resolution", ""),
            ("operator", "Operator / author", ""),
            ("laboratory", "Laboratory", ""),
            ("measurement_date", "Measurement date", ""),
            ("doi", "DOI", ""),
            ("citation", "Citation", ""),
        ):
            self.fields[key] = QLineEdit(initial)
            form.addRow(label, self.fields[key])
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(100)
        form.addRow("Notes", self.notes)
        splitter.addWidget(metadata)

        work = QWidget()
        work_layout = QVBoxLayout(work)
        preprocessing_row = QHBoxLayout()
        preprocessing_row.setContentsMargins(0, 0, 0, 0)
        preprocessing_row.setSpacing(8)
        for button in (auto_detect, smooth, remove_background, despike, reset_profile):
            preprocessing_row.addWidget(button)
        preprocessing_row.addStretch(1)
        work_layout.addLayout(preprocessing_row)
        peak_tools_row = QHBoxLayout()
        peak_tools_row.setContentsMargins(0, 0, 0, 0)
        peak_tools_row.setSpacing(8)
        for button in (detect, add_row, remove_rows):
            peak_tools_row.addWidget(button)
        peak_tools_row.addStretch(1)
        work_layout.addLayout(peak_tools_row)
        self.profile_label = QLabel("No spectrum profile. A line-only reference can still be saved.")
        self.profile_label.setWordWrap(True)
        work_layout.addWidget(self.profile_label)
        self.plot = create_vibrational_plot_widget()
        self.plot.setMinimumHeight(280)
        work_layout.addWidget(self.plot, 1)
        peak_caption = QLabel("Manual / literature peak table. Type peak positions directly; a spectrum profile is optional.")
        peak_caption.setWordWrap(True)
        work_layout.addWidget(peak_caption)
        table_actions = QHBoxLayout()
        table_actions.addWidget(import_peaks)
        table_actions.addStretch(1)
        work_layout.addLayout(table_actions)
        self.band_table = QTableWidget(0, len(self.BAND_HEADERS))
        self.band_table.setHorizontalHeaderLabels(self.BAND_HEADERS)
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.setAlternatingRowColors(True)
        self.band_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.band_table.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.band_table.setMinimumHeight(260)
        for column, width in enumerate((115, 85, 105, 80, 90, 190, 110, 110, 95, 200)):
            self.band_table.setColumnWidth(column, width)
        self.band_table.itemChanged.connect(lambda _item: self._redraw_profile())
        self.band_table.setRowCount(6)
        work_layout.addWidget(self.band_table, 1)
        splitter.addWidget(work)
        splitter.setSizes([430, 820])

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _current_kind(self) -> SignalKind:
        value = self.kind_combo.currentData() or SignalKind.RAMAN
        return value if isinstance(value, SignalKind) else SignalKind(str(value))

    def _set_kind(self, kind: SignalKind) -> None:
        if kind == SignalKind.FTIR:
            self.kind_combo.setCurrentIndex(1)
        elif kind == SignalKind.RAMAN:
            self.kind_combo.setCurrentIndex(0)

    def _show_load_dialog(self) -> None:
        dialog = ReferenceLoadDialog(self, include_manage=False)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if dialog.selected_action == "spectrum" and dialog.selected_kind in {SignalKind.RAMAN, SignalKind.FTIR}:
            self._add_spectrum(dialog.selected_kind)
        elif dialog.selected_action == "template" and dialog.selected_kind in {SignalKind.RAMAN, SignalKind.FTIR}:
            self._load_template(dialog.selected_kind)
        elif dialog.selected_action == "cif":
            self._load_cif_ir_hints()

    def _add_spectrum(self, kind: SignalKind | None = None) -> None:
        active_kind = kind or self._current_kind()
        self._set_kind(active_kind)
        globs = " ".join(f"*{extension}" for extension in supported_spectrum_extensions())
        file_filter = (
            f"Reference spectra/templates ({globs} *.vsref *.json);;"
            f"{_spectrum_file_filter()}"
        )
        path, _ = QFileDialog.getOpenFileName(self, "Add reference spectrum or template", "", file_filter)
        if not path:
            return
        if Path(path).suffix.lower() in {".json", ".vsref"}:
            self._load_template(active_kind, path=path)
            return
        if Path(path).suffix.lower() == ".cif":
            QMessageBox.information(
                self,
                "Use CIF mode",
                "CIF is a structure file, not an experimental spectrum. Use FTIR -> Calculate IR hints from CIF.",
            )
            return
        try:
            loaded = load_xy_spectrum(path, kind=active_kind, name=Path(path).stem, reference=True)
            self.profile = loaded if isinstance(loaded, ReferenceSpectrum) else ReferenceSpectrum(**loaded.__dict__)
            self._remember_original_profile()
        except Exception as exc:
            QMessageBox.warning(self, "Spectrum import failed", str(exc))
            return
        self.profile_path = path
        if not self.fields["name"].text().strip():
            self.fields["name"].setText(Path(path).stem)
        self.profile_label.setText(f"Spectrum: {path}")
        self._redraw_profile(preserve_view=False)
        self._detect_peaks()

    def _auto_detect_profile(self) -> None:
        if self.profile is None or not self.profile.x or not self.profile.y:
            QMessageBox.information(self, "Auto detect", "Load a reference spectrum before auto-detection.")
            return
        source = self.profile_path or self.profile.source_path or self.profile.name or "reference-spectrum"
        guess = guess_spectrum_metadata(source, x=self.profile.x, y=self.profile.y)
        if guess.kind in {SignalKind.RAMAN, SignalKind.FTIR}:
            self._set_kind(guess.kind)
            self.profile.kind = guess.kind
        if not self.fields["name"].text().strip() and self.profile_path:
            self.fields["name"].setText(Path(self.profile_path).stem)
        if guess.kind == SignalKind.RAMAN and not self.fields["laser_nm"].text().strip():
            laser_match = None
            if self.profile_path:
                import re

                laser_match = re.search(r"(?<!\d)(488|514|515|532|633|638|785|830|1064)(?!\d)", str(self.profile_path))
            if laser_match is not None:
                self.fields["laser_nm"].setText(laser_match.group(1))
        self.profile_label.setText(_guess_summary(source, guess))
        if guess.warnings:
            QMessageBox.information(self, "Auto detect", _guess_summary(source, guess))
        self._redraw_profile()

    def _redraw_profile(self, *, preserve_view: bool = True) -> None:
        old_range = self.plot.viewRange() if preserve_view and self._plot_has_content else None
        self.plot.clear()
        table_bands = self._table_bands()
        y_min = 0.0
        y_max = 1.0
        has_content = False
        if self.profile is not None and self.profile.x and self.profile.y:
            x_profile = np.asarray(self.profile.x, dtype=float)
            y_profile = np.asarray(self.profile.y, dtype=float)
            mask = np.isfinite(x_profile) & np.isfinite(y_profile)
            if np.any(mask):
                self.plot.plot(x_profile[mask], y_profile[mask], pen=pg.mkPen("#202124", width=1.2), name="Reference profile")
                y_min = float(np.nanmin(y_profile[mask]))
                y_max = float(np.nanmax(y_profile[mask]))
                has_content = True
        self._draw_table_band_preview(table_bands, y_min, y_max)
        has_content = has_content or bool(table_bands)
        self.plot.setLabel("bottom", "Wavenumber", units="cm-1")
        self.plot.setLabel("left", "Intensity", units="a.u.")
        self._plot_has_content = has_content
        if old_range is not None:
            self.plot.setXRange(float(old_range[0][0]), float(old_range[0][1]), padding=0.0)
            self.plot.setYRange(float(old_range[1][0]), float(old_range[1][1]), padding=0.0)
        elif has_content:
            self.plot.autoRange()

    def _remember_original_profile(self) -> None:
        if self.profile is None:
            self._original_profile = None
            return
        self._original_profile = replace(
            self.profile,
            x=list(self.profile.x),
            y=list(self.profile.y),
        )

    def _profile_xy(self) -> tuple[np.ndarray, np.ndarray] | None:
        if self.profile is None or not self.profile.x or not self.profile.y:
            QMessageBox.information(self, "No spectrum", "Load a reference spectrum before preprocessing.")
            return None
        x = np.asarray(self.profile.x, dtype=float)
        y = np.asarray(self.profile.y, dtype=float)
        mask = np.isfinite(x) & np.isfinite(y)
        if not np.any(mask):
            QMessageBox.information(self, "No spectrum", "The reference spectrum has no finite x/y values.")
            return None
        return x, y

    def _replace_profile_y(self, y: np.ndarray, label: str) -> None:
        if self.profile is None:
            return
        self.profile.y = [float(value) for value in np.asarray(y, dtype=float)]
        self.profile_label.setText(f"{label}: {self.profile_path or self.profile.name}")
        self._redraw_profile()

    def _close_preprocessing_panel(self, *, restore: bool = False) -> None:
        panel = self._preprocessing_panel
        cancel_callback = self._preprocessing_cancel_callback
        self._preprocessing_panel = None
        self._preprocessing_panel_key = ""
        self._preprocessing_cancel_callback = None
        if restore and cancel_callback is not None:
            cancel_callback()
        if panel is not None:
            panel.hide()
            panel.deleteLater()

    def _begin_preprocessing_panel(self, key: str) -> bool:
        if self._preprocessing_panel is None:
            return True
        same_panel = self._preprocessing_panel_key == key
        self._close_preprocessing_panel(restore=True)
        return not same_panel

    def _show_preprocessing_panel(
        self,
        key: str,
        button: QWidget,
        panel: QWidget,
        preview_callback,
        cancel_callback,
    ) -> None:
        if self._preprocessing_panel is not None:
            same_panel = self._preprocessing_panel_key == key
            self._close_preprocessing_panel(restore=True)
            if same_panel:
                return
        panel.setParent(self)
        panel.setWindowFlags(Qt.WindowType.Widget)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setAutoFillBackground(True)
        panel.setStyleSheet(preprocessing_panel_style(True))
        panel.adjustSize()
        position = button.mapTo(self, button.rect().bottomLeft())
        max_x = max(0, self.width() - panel.width() - 8)
        max_y = max(0, self.height() - panel.height() - 8)
        panel.move(min(max(position.x(), 8), max_x), min(max(position.y() + 4, 8), max_y))
        panel.raise_()

        def accept_panel() -> None:
            preview_callback()
            self._close_preprocessing_panel()

        def cancel_panel() -> None:
            self._close_preprocessing_panel(restore=True)

        panel.previewRequested.connect(preview_callback)
        panel.applyRequested.connect(accept_panel)
        panel.cancelRequested.connect(cancel_panel)
        self._preprocessing_panel = panel
        self._preprocessing_panel_key = key
        self._preprocessing_cancel_callback = cancel_callback
        panel.show()

    def _smooth_profile(self) -> None:
        if not self._begin_preprocessing_panel("smooth"):
            return
        xy = self._profile_xy()
        if xy is None:
            return
        x, y = xy
        base = replace(self.profile, x=list(self.profile.x), y=list(self.profile.y)) if self.profile is not None else None
        panel = SmoothPanel(auto_smoothing_window(x, y), self)

        def preview() -> None:
            smoothed_y = np.asarray(y, dtype=float)
            for _ in range(panel.passes()):
                smoothed_y = smooth_spectrum_curve(
                    smoothed_y,
                    method=panel.method(),
                    window=panel.window_size(),
                    polyorder=panel.polyorder(),
                    gaussian_sigma=panel.gaussian_sigma(),
                )
            self._replace_profile_y(
                smoothed_y,
                f"Smoothing preview ({panel.method()}, window {panel.window_size()}, {panel.passes()} pass(es))",
            )

        def cancel() -> None:
            if base is not None:
                self.profile = replace(base, x=list(base.x), y=list(base.y))
                self.profile_label.setText(f"Smoothing preview cancelled: {self.profile_path or self.profile.name}")
                self._redraw_profile()

        self._show_preprocessing_panel("smooth", self.sender() if isinstance(self.sender(), QWidget) else self, panel, preview, cancel)

    def _remove_profile_background(self) -> None:
        if not self._begin_preprocessing_panel("background"):
            return
        xy = self._profile_xy()
        if xy is None:
            return
        x, y = xy
        base = replace(self.profile, x=list(self.profile.x), y=list(self.profile.y)) if self.profile is not None else None
        panel = BackgroundRemovalPanel(parent=self)

        def preview() -> None:
            method = panel.method()
            if method == "constant":
                background = np.full_like(y, float(np.nanpercentile(y, panel.floor_percentile())))
            else:
                background = estimate_background(
                    x,
                    y,
                    degree=panel.degree(),
                    method=method,
                    lam=panel.lambda_value(),
                    asymmetry=panel.asymmetry(),
                    half_window=panel.half_window(),
                )
            self._replace_profile_y(
                y - background,
                f"Background preview ({background_method_label(method, panel.degree())})",
            )

        def cancel() -> None:
            if base is not None:
                self.profile = replace(base, x=list(base.x), y=list(base.y))
                self.profile_label.setText(f"Background preview cancelled: {self.profile_path or self.profile.name}")
                self._redraw_profile()

        self._show_preprocessing_panel("background", self.sender() if isinstance(self.sender(), QWidget) else self, panel, preview, cancel)

    def _despike_profile(self) -> None:
        if not self._begin_preprocessing_panel("despike"):
            return
        xy = self._profile_xy()
        if xy is None:
            return
        _x, y = xy
        base = replace(self.profile, x=list(self.profile.x), y=list(self.profile.y)) if self.profile is not None else None
        panel = DespikePanel(self)

        def preview() -> None:
            corrected_y = np.asarray(y, dtype=float)
            for _ in range(panel.passes()):
                corrected_y = remove_narrow_spikes(
                    corrected_y,
                    threshold=panel.threshold(),
                    max_width=panel.max_width(),
                    median_window=panel.median_window(),
                )
            changed = int(np.count_nonzero(corrected_y != y))
            self._replace_profile_y(corrected_y, f"Despike preview ({changed} point(s) replaced)")

        def cancel() -> None:
            if base is not None:
                self.profile = replace(base, x=list(base.x), y=list(base.y))
                self.profile_label.setText(f"Despike preview cancelled: {self.profile_path or self.profile.name}")
                self._redraw_profile()

        self._show_preprocessing_panel("despike", self.sender() if isinstance(self.sender(), QWidget) else self, panel, preview, cancel)

    def _reset_profile(self) -> None:
        if self._original_profile is None:
            QMessageBox.information(self, "No original profile", "Load a reference spectrum before resetting.")
            return
        self.profile = replace(
            self._original_profile,
            x=list(self._original_profile.x),
            y=list(self._original_profile.y),
        )
        self.profile_label.setText(f"Spectrum: {self.profile_path or self.profile.name}")
        self._redraw_profile()

    def _detect_peaks(self) -> None:
        if self.profile is None:
            QMessageBox.information(self, "No spectrum", "Add a spectrum before detecting peaks.")
            return
        bands = detect_bands(self.profile, BandDetectionOptions(backend="auto", fit_peaks=False))
        self._set_bands(bands)

    def _set_bands(self, bands: list[SpectralBand]) -> None:
        blocked = self.band_table.blockSignals(True)
        self.band_table.setRowCount(len(bands))
        for row, band in enumerate(bands):
            values = [
                f"{band.position:.4f}",
                f"{band.intensity:.6g}",
                f"{band.width:.4f}" if band.width else "",
                "",
                band.symmetry,
                band.assignment,
                "",
                "",
                "detected",
                "",
            ]
            for column, value in enumerate(values):
                self.band_table.setItem(row, column, QTableWidgetItem(value))
        self.band_table.blockSignals(blocked)
        self._redraw_profile()

    def _add_band_row(self) -> None:
        self.band_table.insertRow(self.band_table.rowCount())
        self._redraw_profile()

    def _remove_selected_rows(self) -> None:
        rows = sorted({index.row() for index in self.band_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.band_table.removeRow(row)
        self._redraw_profile()

    def _import_peak_table(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import peak table", "", "Tables (*.csv *.tsv *.txt);;All files (*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
            rows = list(csv.reader(text.splitlines(), dialect))
        except Exception as exc:
            QMessageBox.warning(self, "Peak table import failed", str(exc))
            return
        if not rows:
            return
        header = [cell.strip().lower() for cell in rows[0]]
        has_header = any("position" in cell or "wavenumber" in cell or "intensity" in cell for cell in header)
        data_rows = rows[1:] if has_header else rows
        blocked = self.band_table.blockSignals(True)
        self.band_table.setRowCount(0)
        for values in data_rows:
            if not values or not values[0].strip():
                continue
            row = self.band_table.rowCount()
            self.band_table.insertRow(row)
            for column, value in enumerate(values[: self.band_table.columnCount()]):
                self.band_table.setItem(row, column, QTableWidgetItem(value.strip()))
        self.band_table.blockSignals(blocked)
        self._redraw_profile()

    def _load_template(self, kind: SignalKind | None = None, *, path: str | None = None) -> None:
        if kind is not None:
            self._set_kind(kind)
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Load reference template", "", "Reference templates (*.vsref *.json);;All files (*)")
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.warning(self, "Template import failed", str(exc))
            return
        metadata = payload.get("metadata") or {}
        for key, field in self.fields.items():
            value = metadata.get(key)
            if value is not None:
                field.setText(str(value))
        self.notes.setPlainText(str(metadata.get("notes") or ""))
        kind = str(payload.get("kind") or metadata.get("method") or "raman").lower()
        self.kind_combo.setCurrentIndex(1 if kind in {"ftir", "ir", "infrared"} else 0)
        origin_index = self.origin_combo.findData(metadata.get("origin", "experimental"))
        self.origin_combo.setCurrentIndex(max(0, origin_index))
        profile = payload.get("profile") or {}
        if profile.get("x") and profile.get("y"):
            self.profile = ReferenceSpectrum(
                x=[float(value) for value in profile["x"]],
                y=[float(value) for value in profile["y"]],
                kind=self._current_kind(),
                name=self.fields["name"].text(),
            )
            self.profile_path = str(profile.get("source_path") or path)
            self._remember_original_profile()
            self.profile_label.setText(f"Spectrum from template: {self.profile_path}")
            self._redraw_profile(preserve_view=False)
        self._set_band_rows(payload.get("bands") or [], preserve_view=False)

    def _load_cif_ir_hints(self) -> None:
        self._set_kind(SignalKind.FTIR)
        path, _ = QFileDialog.getOpenFileName(self, "Open CIF structure for IR hints", "", "CIF files (*.cif);;All files (*)")
        if not path:
            return
        try:
            source = CifStructureSource(path)
            records = source.search(SourceQuery(kind=SignalKind.FTIR))
            if not records:
                raise ValueError("No CIF structure record could be created from this file.")
            record = records[0]
            self.profile = source.load_spectrum(record)
            self._remember_original_profile()
            self.profile_path = str(path)
            if not self.fields["name"].text().strip():
                self.fields["name"].setText(record.name or Path(path).stem)
            if not self.fields["formula"].text().strip():
                self.fields["formula"].setText(record.formula)
            origin_index = self.origin_combo.findData("calculated")
            self.origin_combo.setCurrentIndex(max(0, origin_index))
            hints = source._band_hints(record.formula)
            self._set_band_rows(
                [
                    {
                        "position_cm1": f"{hint.position:.4f}",
                        "intensity": f"{hint.intensity:.6g}",
                        "fwhm_cm1": f"{hint.width:.4f}",
                        "assignment": hint.assignment,
                        "confidence": "structural hint",
                        "comment": "Estimated from CIF formula; not a DFT IR calculation",
                    }
                    for hint in hints
                ],
                preserve_view=False,
            )
        except Exception as exc:
            QMessageBox.warning(self, "CIF import failed", str(exc))
            return
        self.profile_label.setText(f"CIF IR hints: {path}")
        self._redraw_profile(preserve_view=False)

    def _save_blank_template(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save reference template",
            "reference_template.json",
            "JSON templates (*.json)",
        )
        if not path:
            return
        payload = blank_reference_template(self._current_kind())
        try:
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, "Template save failed", str(exc))

    def _set_band_rows(self, bands: list[dict], *, preserve_view: bool = True) -> None:
        keys = [
            "position_cm1", "intensity", "fwhm_cm1", "mode", "symmetry", "assignment",
            "polarization", "orientation", "confidence", "comment",
        ]
        blocked = self.band_table.blockSignals(True)
        self.band_table.setRowCount(max(len(bands), 6))
        self.band_table.clearContents()
        for row, band in enumerate(bands):
            for column, key in enumerate(keys):
                value = band.get(key, "")
                self.band_table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))
        self.band_table.blockSignals(blocked)
        self._redraw_profile(preserve_view=preserve_view)

    def _table_bands(self) -> list[dict[str, object]]:
        bands: list[dict[str, object]] = []
        for row in range(self.band_table.rowCount()):
            position = self._number_or_none(self._cell(row, 0))
            if position is None:
                continue
            bands.append(
                {
                    "position": position,
                    "intensity": self._number_or_none(self._cell(row, 1)),
                    "fwhm": self._number_or_none(self._cell(row, 2)),
                    "mode": self._cell(row, 3),
                    "symmetry": self._cell(row, 4),
                    "assignment": self._cell(row, 5),
                }
            )
        return bands

    def _draw_table_band_preview(self, bands: list[dict[str, object]], y_min: float, y_max: float) -> None:
        if not bands:
            return
        positions = np.asarray([float(band["position"]) for band in bands], dtype=float)
        if not np.any(np.isfinite(positions)):
            return
        profile_x = np.asarray(self.profile.x, dtype=float) if self.profile is not None and self.profile.x else np.asarray([])
        profile_y = np.asarray(self.profile.y, dtype=float) if self.profile is not None and self.profile.y else np.asarray([])
        if not np.isfinite(y_min) or not np.isfinite(y_max) or y_max <= y_min:
            y_min, y_max = 0.0, 1.0
        span = max(y_max - y_min, 1.0e-9)
        zero_line = 0.0
        intensities = np.asarray(
            [float(band["intensity"]) for band in bands if band["intensity"] is not None],
            dtype=float,
        )
        has_reported_intensity = bool(intensities.size)
        intensity_scale = float(np.nanmax(np.abs(intensities))) if intensities.size else 0.0
        if intensity_scale <= 0.0:
            intensity_scale = 1.0

        line_x: list[float] = []
        line_y: list[float] = []
        tick_x: list[float] = []
        tick_y: list[float] = []
        labels: list[tuple[float, float, str]] = []
        lower = min(y_min, zero_line) - span * 0.16
        tick_height = span * 0.055
        tick_base = lower + span * 0.02

        for band in bands:
            position = float(band["position"])
            if not np.isfinite(position):
                continue
            intensity = float(band["intensity"]) if band["intensity"] is not None else None
            fwhm = float(band["fwhm"]) if band["fwhm"] is not None else 0.0
            if has_reported_intensity:
                top = zero_line + span * max(abs(intensity or 0.0) / intensity_scale, 0.08)
            else:
                top = zero_line + span * 0.72
            if profile_x.size and profile_y.size == profile_x.size:
                half_window = max(fwhm * 1.5, 8.0)
                mask = (np.abs(profile_x - position) <= half_window) & np.isfinite(profile_y)
                if np.any(mask):
                    top = max(float(np.nanmax(profile_y[mask])), zero_line + span * 0.04)
            top = min(top, y_max + span * 0.08)
            line_x.extend((position, position, np.nan))
            line_y.extend((zero_line, top, np.nan))
            tick_x.extend((position, position, np.nan))
            tick_y.extend((tick_base, tick_base + tick_height, np.nan))
            label = self._band_preview_label(band)
            if label:
                labels.append((position, top, label))

        pen = pg.mkPen("#1a73e8", width=1.4)
        if line_x:
            self.plot.plot(line_x, line_y, pen=pen, connect="finite", name="Reference lines")
        if tick_x:
            self.plot.plot(tick_x, tick_y, pen=pg.mkPen("#1a73e8", width=1.2), connect="finite", name="Reference ticks")
        for index, (position, top, label_text) in enumerate(labels):
            label = pg.TextItem(
                label_text,
                color="#1a73e8",
                anchor=(0.5, 1.0),
                border=pg.mkPen("#1a73e8", width=0.7),
                fill=pg.mkBrush(255, 255, 255, 225),
            )
            label.setPos(position, top + span * (0.035 + 0.018 * (index % 2)))
            self.plot.addItem(label)

    def _band_preview_label(self, band: dict[str, object]) -> str:
        mode = str(band.get("mode") or "").strip()
        symmetry = str(band.get("symmetry") or "").strip()
        if symmetry:
            return symmetry
        return mode if len(mode) <= 18 else ""

    def _validate_and_accept(self) -> None:
        has_profile = self.profile is not None and bool(self.profile.x and self.profile.y)
        has_bands = any(self._cell(row, 0) for row in range(self.band_table.rowCount()))
        if not has_profile and not has_bands:
            QMessageBox.warning(self, "Empty reference", "Add a spectrum or at least one peak position.")
            return
        self.accept()

    def _cell(self, row: int, column: int) -> str:
        item = self.band_table.item(row, column)
        return item.text().strip() if item is not None else ""

    @staticmethod
    def _number(text: str):
        text = text.strip().replace(",", ".")
        return float(text) if text else None

    def _number_or_none(self, text: str):
        try:
            return self._number(text)
        except ValueError:
            return None

    def _intensity_number_or_label(self, text: str):
        value = self._number_or_none(text)
        if value is not None:
            return value
        normalized = text.strip().lower().replace("_", " ").replace("-", " ")
        if not normalized:
            return None
        qualitative = {
            "very weak": 0.1,
            "weak": 0.25,
            "medium": 0.5,
            "moderate": 0.5,
            "strong": 0.75,
            "very strong": 1.0,
            "vs": 1.0,
            "s": 0.75,
            "m": 0.5,
            "w": 0.25,
            "vw": 0.1,
        }
        if normalized in qualitative:
            return qualitative[normalized]
        for label, mapped in qualitative.items():
            if label in normalized:
                return mapped
        return None

    def payload(self) -> dict:
        metadata = {key: field.text().strip() for key, field in self.fields.items() if field.text().strip()}
        metadata["origin"] = str(self.origin_combo.currentData() or "experimental")
        if self.notes.toPlainText().strip():
            metadata["notes"] = self.notes.toPlainText().strip()
        bands = []
        keys = [
            "position_cm1", "intensity", "fwhm_cm1", "mode", "symmetry", "assignment",
            "polarization", "orientation", "confidence", "comment",
        ]
        for row in range(self.band_table.rowCount()):
            if not self._cell(row, 0):
                continue
            item = {key: self._cell(row, column) for column, key in enumerate(keys)}
            position = self._number_or_none(str(item["position_cm1"]))
            if position is None:
                continue
            item["position_cm1"] = position
            item["intensity"] = self._intensity_number_or_label(str(item["intensity"]))
            item["fwhm_cm1"] = self._number_or_none(str(item["fwhm_cm1"]))
            bands.append(item)
        profile = None
        if self.profile is not None and self.profile.x and self.profile.y:
            profile = {
                "x": [float(value) for value in self.profile.x],
                "y": [float(value) for value in self.profile.y],
                "source_path": self.profile_path,
            }
        return {
            "format": "vibrational-reference",
            "version": 1,
            "kind": self._current_kind().value,
            "source": "User References",
            "metadata": metadata,
            "profile": profile,
            "bands": bands,
        }
