"""Build the spectroscopy Finder menu bar from one shared command map."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QMenuBar, QWidgetAction

from vibrational_finder.ui.fullscreen import FullscreenController
from vibrational_finder.ui.interface_scaling import INTERFACE_SCALE_PERCENTAGES


def build_finder_menu_bar(owner) -> QMenuBar:
    menu_bar = owner.menuBar()
    menu_bar.clear()
    menus = {
        name: menu_bar.addMenu(name)
        for name in (
            "File", "Edit", "View", "Instrument", "Spectrum", "Bands", "Search",
            "Entries", "Database", "Tools", "Experimental", "Help",
        )
    }

    def command(menu: str, text: str, callback) -> QAction:
        action = QAction(text, owner)
        action.triggered.connect(callback)
        menus[menu].addAction(action)
        return action

    command("File", "New project", owner.top_toolbar.new_button.click)
    command("File", "Open project…", owner.top_toolbar.open_button.click)
    command("File", "Save project", owner.top_toolbar.save_button.click)
    command("File", "Import data…", owner.top_toolbar.import_button.click)
    command("File", "Import folder…", owner.request_import_folder)
    command("File", "Export publication figure…", owner.top_toolbar.export_button.click)
    command("Edit", "Undo processing", owner.undo_active_processing)
    command("Edit", "Reset processing", owner.reset_active_processing)
    command("View", "Fit plot", owner.top_toolbar.fit_button.click)
    command("View", "Plot settings…", owner.top_toolbar.plot_button.click)
    command("View", "Edit layout", owner.begin_workspace_layout_edit)
    scale_menu = menus["View"].addMenu("Interface scale")
    owner.ui_scale_combo = QComboBox()
    owner.ui_scale_combo.setAccessibleName("Interface scale")
    owner.ui_scale_combo.setToolTip("Adjust control size without changing spectroscopy data")
    owner.ui_scale_combo.addItems([f"UI {value}%" for value in INTERFACE_SCALE_PERCENTAGES])
    owner.ui_scale_combo.setCurrentText(f"UI {owner._ui_scale_percent}%")
    owner.ui_scale_combo.currentTextChanged.connect(owner._set_interface_scale)
    scale_action = QWidgetAction(scale_menu)
    scale_action.setDefaultWidget(owner.ui_scale_combo)
    scale_menu.addAction(scale_action)
    menus["View"].addSeparator()
    owner._fullscreen_controller = FullscreenController(owner, menus["View"])
    command("Instrument", "Spectral settings", owner.top_toolbar.instrument_button.click)
    command("Spectrum", "Processing", lambda: owner.right_tabs.setCurrentWidget(owner.action_bar))
    command("Bands", "Band search", owner.top_toolbar.bands_button.click)
    command("Search", "Identify compounds", owner.top_toolbar.match_button.click)
    command("Search", "Next component", owner.top_toolbar.residual_button.click)
    command("Entries", "Accepted results", lambda: owner.right_tabs.setCurrentWidget(owner.composition_panel))
    command("Database", "Manage databases…", owner.top_toolbar.database_button.click)
    command("Database", "Add reference…", owner.source_settings_panel.add_reference)
    command("Tools", "Export figure…", owner.top_toolbar.export_button.click)
    command("Experimental", "Residual component search", owner.top_toolbar.residual_button.click)
    command("Help", "IR/Raman Finder help", owner._show_help)

    def check_updates() -> None:
        from vibrational_finder.ui.deferred_updates import update_controller

        update_controller(owner).check(manual=True)

    owner.check_updates_action = command("Help", "Check for updates…", check_updates)

    menu_bar._owned_menus = list(menus.values()) + [scale_menu]
    owner._owned_menus = menu_bar._owned_menus
    return menu_bar
