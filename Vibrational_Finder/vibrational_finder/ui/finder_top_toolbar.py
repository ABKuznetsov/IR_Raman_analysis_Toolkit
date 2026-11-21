from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Signal, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLayout, QMenu, QSizePolicy, QToolButton, QWidget

from vibrational_finder.ui.theme import (
    BRAND_ACCENT,
    BRAND_ACCENT_BORDER,
    BRAND_BANDS,
    IR_RAMAN_BRAND_CRIMSON,
    colored_hover_background,
    is_dark_theme,
    theme_colors,
)
from vibrational_finder.ui.toolbar_icons import toolbar_icon


class FinderTopToolbar(QWidget):
    newProjectRequested = Signal()
    openProjectRequested = Signal()
    saveProjectRequested = Signal()
    importRequested = Signal()
    detectBandsRequested = Signal()
    matchRequested = Signal()
    residualSearchRequested = Signal()
    exportRequested = Signal()
    plotSettingsRequested = Signal()
    databaseRequested = Signal()
    resetProcessingRequested = Signal()
    fitPlotRequested = Signal()
    spectralSettingsRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("finderTopToolBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(56)
        self._applying_style = False
        self._theme_override: bool | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._buttons: list[QToolButton] = []
        layout = QHBoxLayout(self)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self.new_button = self._button("new", "New project", "Create a project", self.newProjectRequested)
        self.open_button = self._button("open", "Open project", "Open an IRFF project", self.openProjectRequested)
        self.save_button = self._button("save", "Save", "Save the current project", self.saveProjectRequested)
        self.import_button = self._button("import", "Import data", "Import Raman or FTIR spectra", self.importRequested)
        self.bands_button = self._button("bands", "Band search", "Detect and edit bands in the active spectrum", self.detectBandsRequested)
        self.match_button = self._button("match", "Identify compounds", "Find matching reference spectra", self.matchRequested)
        self.match_button.setCheckable(True)
        self.match_button.setProperty("searchMode", "auto")
        self.bands_button.setCheckable(True)
        self.bands_button.setProperty("searchMode", "bands")
        self.residual_button = self._button("residual", "Next component", "Search unexplained bands", self.residualSearchRequested)
        self.export_button = self._button("export", "Export", "Export PNG, JPEG, layered SVG or vector PDF", self.exportRequested)
        self.reset_button = self._button("reset", "Reset processing", "Restore the active spectrum", self.resetProcessingRequested)
        self.fit_button = self._button("fit", "Fit plot", "Fit the full spectrum in the plot", self.fitPlotRequested)
        self.database_button = self._button("database", "Manage databases", "Manage spectroscopy sources", self.databaseRequested)
        self.plot_button = self._button("plot", "Plot settings", "Configure plot appearance", self.plotSettingsRequested)
        self.instrument_button = self._button("instrument", "Spectral settings", "Configure spectrum settings", self.spectralSettingsRequested)
        self.residual_button.hide()
        self.export_button.hide()

        self._groups = [
            self._group(layout, [self.new_button, self.open_button, self.save_button, self.import_button]),
            self._group(layout, [self.match_button, self.bands_button, self.reset_button, self.fit_button]),
        ]
        layout.addStretch(1)
        self._groups.append(
            self._group(
                layout,
                [self.database_button, self.plot_button, self.instrument_button],
            )
        )

        self.more_button = self._button("more", "More", "More commands")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.more_button.setMenu(QMenu(self.more_button))
        self._overflow_actions: dict[QToolButton, QAction] = {}
        for button in self._buttons:
            if button is self.more_button:
                continue
            action = self.more_button.menu().addAction(button.text())
            action.triggered.connect(lambda _checked=False, source=button: source.click())
            self._overflow_actions[button] = action
        self.more_button.menu().aboutToShow.connect(self._sync_overflow_actions)
        layout.addWidget(self.more_button)
        self.more_button.hide()
        self._secondary = [
            self.new_button, self.open_button, self.save_button,
            self.reset_button, self.fit_button, self.plot_button,
        ]
        self._compact = [
            self.new_button, self.open_button, self.save_button,
            self.reset_button, self.fit_button,
        ]
        self._fallback = [
            self.import_button, self.bands_button, self.database_button,
            self.instrument_button,
        ]
        self._responsive_buttons = [
            button for button in self._buttons
            if button not in (self.residual_button, self.export_button, self.more_button)
        ]
        self._apply_style()

    def attach_layout_controls(self, edit_button: QToolButton, help_button: QToolButton) -> None:
        """Attach the exact XRD layout pin and help controls to the final group."""
        self.layout_button = edit_button
        self.help_button = help_button
        help_button.setText("Help")
        row = self._groups[-1].layout()
        for button, icon in ((edit_button, "layout"), (help_button, "help")):
            button.setProperty("toolbarIcon", icon)
            button.setIconSize(QSize(20, 20))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setFixedHeight(34)
            button.setAutoRaise(True)
            row.addWidget(button)
            self._buttons.append(button)
            self._responsive_buttons.append(button)
            self._fallback.append(button)
            action = self.more_button.menu().addAction(button.text())
            action.triggered.connect(lambda _checked=False, source=button: source.click())
            self._overflow_actions[button] = action
        self._apply_style()
        self._adapt_width()

    def _button(self, key: str, text: str, tooltip: str, signal=None) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(f"command_{key}")
        button.setText(text)
        button.setAccessibleName(text)
        button.setToolTip(f"{text}\n{tooltip}")
        button.setProperty("toolbarIcon", key)
        button.setIconSize(QSize(20, 20))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setAutoRaise(True)
        button.setFixedHeight(34)
        button.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        if signal is not None:
            button.clicked.connect(signal)
        self._buttons.append(button)
        return button

    def _group(self, layout: QHBoxLayout, buttons: list[QToolButton]) -> QFrame:
        group = QFrame(self)
        group.setObjectName("toolbarGroup")
        row = QHBoxLayout(group)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        for button in buttons:
            row.addWidget(button)
        layout.addWidget(group)
        return group

    def _required_width(self) -> int:
        groups = [group for group in self._groups if not group.isHidden()]
        width = sum(group.layout().sizeHint().width() for group in groups)
        if not self.more_button.isHidden():
            width += self.more_button.sizeHint().width()
        return width + 16 + 8 * len(groups)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 56)

    def _refresh_groups(self) -> None:
        for group in self._groups:
            row = group.layout()
            group.setVisible(any(not row.itemAt(index).widget().isHidden() for index in range(row.count())))
            row.invalidate()

    def _adapt_width(self) -> None:
        if not hasattr(self, "_secondary"):
            return
        for button in self._responsive_buttons:
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.show()
        self.more_button.hide()
        self._refresh_groups()
        if self._required_width() > self.width():
            for button in self._compact:
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            for group in self._groups:
                group.layout().invalidate()
        if self._required_width() > self.width():
            for button in self._secondary:
                button.hide()
            self.more_button.show()
            self._refresh_groups()
            self.import_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            for button in self._fallback:
                if self._required_width() <= self.width():
                    break
                button.hide()
                self._refresh_groups()
        self._sync_overflow_actions()
        self.layout().invalidate()
        self.layout().activate()

    def _sync_overflow_actions(self) -> None:
        for button, action in self._overflow_actions.items():
            action.setIcon(button.icon())
            action.setEnabled(button.isEnabled())
            action.setVisible(button.isHidden())
            action.setToolTip(button.toolTip())
            action.setCheckable(button.isCheckable())
            action.setChecked(button.isChecked())

    def set_search_mode(self, mode: str) -> None:
        if mode not in {"search", "auto", "bands"}:
            raise ValueError(f"Unknown search mode: {mode}")
        self.match_button.setChecked(mode == "auto")
        self.bands_button.setChecked(mode == "bands")
        self._sync_overflow_actions()

    def _apply_style(self, dark: bool | None = None) -> None:
        if self._applying_style:
            return
        self._applying_style = True
        if dark is not None:
            self._theme_override = bool(dark)
        elif self._theme_override is not None:
            dark = self._theme_override
        colors = theme_colors(dark) if dark is not None else theme_colors(widget=self)
        try:
            self.setStyleSheet(
                f"QWidget#finderTopToolBar {{ background: {colors['bg']}; border: 1px solid {IR_RAMAN_BRAND_CRIMSON}; border-radius: 10px; }}"
                f"QFrame#toolbarGroup {{ background: {colors['panel']}; border: 1px solid {IR_RAMAN_BRAND_CRIMSON}; border-radius: 8px; }}"
                f"QWidget#finderTopToolBar QToolButton {{ background: {colors['button']}; color: {colors['text']}; border: 1px solid {colors['button_border']}; border-radius: 6px; padding: 4px 9px; font-weight: 500; }}"
                f"QWidget#finderTopToolBar QToolButton:hover:enabled {{ background: {colors['button_hover']}; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton:pressed {{ background: {colors['button_pressed']}; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton:focus {{ border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton[searchMode=\"auto\"]:checked {{ background: {BRAND_ACCENT}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton[searchMode=\"auto\"]:checked:hover:enabled {{ background: {colored_hover_background(BRAND_ACCENT)}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton[searchMode=\"bands\"]:checked {{ background: {BRAND_BANDS}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton[searchMode=\"bands\"]:checked:hover:enabled {{ background: {colored_hover_background(BRAND_BANDS)}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton#editLayoutButton:checked {{ background: {BRAND_BANDS}; color: #ffffff; border-color: {BRAND_ACCENT_BORDER}; }}"
                f"QWidget#finderTopToolBar QToolButton#editLayoutButton:checked:hover:enabled {{ background: {colored_hover_background(BRAND_BANDS)}; }}"
                "QWidget#finderTopToolBar QToolButton#contextHelpButton:checked { background: #8f2f66; color: #ffffff; border-color: #d060a0; }"
                f"QWidget#finderTopToolBar QToolButton#contextHelpButton:checked:hover:enabled {{ background: {colored_hover_background('#8f2f66')}; }}"
                f"QWidget#finderTopToolBar QToolButton:disabled {{ background: transparent; color: {colors['muted']}; border-color: transparent; }}"
                "QWidget#finderTopToolBar QToolButton::menu-indicator { image: none; width: 0px; }"
            )
            self.more_button.menu().setStyleSheet(
                f"QMenu {{ background: {colors['panel']}; color: {colors['text']}; border: 1px solid {colors['border']}; padding: 5px; }}"
                f"QMenu::item {{ color: {colors['text']}; padding: 7px 22px 7px 30px; border-radius: 4px; }}"
                f"QMenu::item:selected {{ background: {colors['hover']}; }}"
                f"QMenu::item:disabled {{ color: {colors['muted']}; }}"
            )
            for button in self._buttons:
                button.setIcon(toolbar_icon(str(button.property("toolbarIcon")), colors["text"], colors["muted"]))
        finally:
            self._applying_style = False

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._adapt_width()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange):
            self._apply_style(self._theme_override)
            self._adapt_width()
