"""Resolve live spectroscopy controls to concise, non-executing explanations."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class HelpArticle:
    title: str
    what: str
    why: str
    how: str
    topic: str


def _article(topic: str, title: str, what: str, why: str, how: str) -> HelpArticle:
    return HelpArticle(title, what, why, how, topic)


def resolve_help(window, widget: QWidget, global_pos=None) -> tuple[QWidget, HelpArticle]:
    toolbar = window.top_toolbar
    direct = {
        toolbar.new_button: _article("projects.new", "New project", "Start an empty Raman/FTIR project.", "Separate unrelated measurements and interpretations.", "Save the current project first if it contains changes."),
        toolbar.open_button: _article("projects.open", "Open project", "Open a portable IRFF project.", "Restore measurements, processing, accepted results and display state together.", "Choose an .irff file or open it from Finder."),
        toolbar.save_button: _article("projects.save", "Save project", "Save the current Raman/FTIR analysis as IRFF.", "Keep scientific data and reconstruction instructions portable.", "Use Save after changing data, processing or accepted results."),
        toolbar.import_button: _article("projects.import", "Import Raman or FTIR", "Add measured vibrational spectra to the project.", "Imported spectra are the observations used for processing and search.", "Choose supported Raman/FTIR text or instrument files."),
        toolbar.match_button: _article("search.identify", "Identify compounds", "Compare the active spectrum with enabled spectroscopy references.", "Candidate scores help rank possible compounds; they are not probabilities.", "Set element restrictions if needed, then run identification."),
        toolbar.bands_button: _article("bands.search", "Band search", "Detect and edit Raman/FTIR bands before matching.", "Band positions provide a compact representation for reference search.", "Open the band editor, review detected bands, then run the search."),
        toolbar.reset_button: _article("processing.reset", "Reset processing", "Restore the active spectrum to its imported signal.", "Processing experiments remain reversible.", "Use this after an unsuitable smoothing, baseline or crop operation."),
        toolbar.fit_button: _article("plot.fit", "Fit plot", "Show the complete active spectral range.", "Return quickly after zooming or panning.", "Click once to reset the visible plot range."),
        toolbar.export_button: _article("export.figure", "Export figure", "Export the assembled scientific figure as PNG, JPEG, SVG or PDF.", "Vector formats retain editable text and layers for publication work.", "Arrange the canvas first, then choose the output format and size."),
        window.project_tree: _article("projects.tree", "Project tree", "Organise Raman and FTIR spectra into project series.", "The active spectrum and checked visible spectra are separate states.", "Select to activate; use checks to control multi-spectrum display."),
        window.action_bar: _article("processing", "Spectrum processing", "Apply reversible smoothing, baseline, crop, despike, normalization and calibration.", "Prepare the measured signal without altering the imported source data.", "Open one section, preview the result, then apply or undo it."),
        window.candidate_workspace.table: _article("results.candidates", "Candidate results", "Reference spectra ranked against the active Raman/FTIR measurement.", "Candidates remain hypotheses until accepted.", "Select to preview and double-click to accept a result."),
        window.accepted_components_workspace.table: _article("results.accepted", "Accepted results", "Compounds accepted for the active spectrum.", "Accepted components are retained separately from the candidate list.", "Toggle visibility, inspect color and remove results when needed."),
        window._layout_state.pin_button: _article("appearance.layout", "Edit layout", "Unlock or save the relative panel and table arrangement.", "The same proportions can be restored across HD, QHD and Retina screens.", "Enable editing, resize panels and columns, then switch it off to save."),
        window.ui_scale_combo: _article("appearance.scale", "Interface scale", "Scale controls from 75% to 150% without changing spectral coordinates.", "Match control size to the monitor and viewing distance.", "Choose a percentage; the setting is stored with workspace preferences."),
    }
    help_button = window._layout_state.help_button
    direct[help_button] = _article(
        "help.context", "Context help", "Click-to-explain mode for Raman/FTIR controls.",
        "Learn a control without running its command.",
        "Turn Help on, click a control, then press Escape or Help again to return.",
    )
    element_buttons = window.composition_panel.element_table._buttons
    symbol = next((name for name, button in element_buttons.items() if button is widget), None)
    if symbol is not None:
        mode = window.element_states.get(symbol, "neutral")
        if mode == "required":
            meaning = "Candidate formulas must contain this element."
        elif mode == "excluded":
            meaning = "Candidate formulas containing this element are excluded."
        else:
            meaning = "This element may be present and does not currently restrict the search."
        return widget, _article(
            "elements.filter", f"{symbol} element filter", meaning,
            "Chemical restrictions narrow reference search; they are not measured composition values.",
            "Left-click to require it, right-click to exclude it, or drag across several cells.",
        )
    current: QWidget | None = widget
    while current is not None:
        if current in direct:
            return current, direct[current]
        current = current.parentWidget()
    return widget, _article(
        "control", widget.accessibleName() or "Raman/FTIR control",
        widget.toolTip() or "A control in the current spectroscopy workspace.",
        "It configures the current Raman/FTIR operation.",
        "Turn off Help to operate this control.",
    )
