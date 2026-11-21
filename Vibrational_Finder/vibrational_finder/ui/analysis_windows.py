from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from finder_core.models import SignalKind
from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.plot_export.metadata import CanvasLayer, canvas_item_tag
from vibrational_finder.project_document import ProjectDocument
from vibrational_finder.project_model import observed_spectra
from vibrational_finder.project_state import VibrationalProjectState
from vibrational_finder.ui.finder_action_bar import FinderActionBar
from vibrational_finder.ui.finder_plot_control_bar import FinderPlotControlBar
from vibrational_finder.ui.finder_top_toolbar import FinderTopToolbar
from vibrational_finder.ui.observed_spectrum_actions import ObservedSpectrumActionsMixin
from vibrational_finder.ui.plot_display_actions import PlotDisplayActionsMixin
from vibrational_finder.ui.project_tree import ProjectTree
from vibrational_finder.ui.project_controls import ProjectControlsWidget
from vibrational_finder.ui.composition_panel import SpectroscopyCompositionPanel
from vibrational_finder.ui.project_document_actions import ProjectDocumentActionsMixin
from vibrational_finder.ui.project_tree_controller import ProjectTreeController
from vibrational_finder.ui.sample_metadata_panel import SampleMetadataPanel
from vibrational_finder.ui.band_information_card import BandInformationCard
from vibrational_finder.ui.spectrum_processing_actions import SpectrumProcessingActionsMixin
from vibrational_finder.ui.system_theme import SystemThemeObserver
from vibrational_finder.ui.theme import is_dark_theme, window_style
from vibrational_finder.ui.vibrational_plot import (
    SpectrumPlotCanvas, create_vibrational_plot_widget, layout_band_annotations, show_observed_spectrum,
    show_reference_layers,
)
from vibrational_finder.ui.spectrum_legends import PhaseLegendEntry, REFERENCE_COLOR, show_spectrum_legends
from vibrational_finder.ui.workspace_preferences import WorkspacePreferences, WorkspaceState
from vibrational_finder.ui.layout_state import SplitterLayoutState, normalize_splitter_ratios
from vibrational_finder.services.spectroscopy_source_catalog import SpectroscopySourceCatalog
from vibrational_finder.ui.source_settings_panel import SourceSettingsPanel
from vibrational_finder.ui.candidate_workspace import CandidateWorkspace
from vibrational_finder.ui.analysis_actions import SpectroscopyAnalysisActionsMixin
from vibrational_finder.ui.accepted_components_workspace import AcceptedComponentsWorkspace
from vibrational_finder.ui.publication_export_actions import PublicationExportActionsMixin
from vibrational_finder.ui.interface_scaling import INTERFACE_SCALE_PERCENTAGES, interface_density_factor
from vibrational_finder.ui.ui_density import UiDensity


class SpectroscopyFinderWindow(
    PublicationExportActionsMixin,
    SpectroscopyAnalysisActionsMixin,
    SpectrumProcessingActionsMixin,
    ProjectDocumentActionsMixin,
    ObservedSpectrumActionsMixin,
    PlotDisplayActionsMixin,
    QMainWindow,
):
    """Development shell that ports the Finder workspace to Raman and FTIR."""

    def __init__(
        self,
        project: VibrationalProjectState | None = None,
        *,
        defer_initial_plot: bool = False,
        defer_source_settings: bool = False,
        workspace_preferences: WorkspacePreferences | None = None,
        source_catalog: SpectroscopySourceCatalog | None = None,
    ) -> None:
        super().__init__()
        self._application_ref = QApplication.instance()
        self.document = ProjectDocument(project or VibrationalProjectState())
        self.project = self.document.state
        self.source_catalog = source_catalog or SpectroscopySourceCatalog(self.project.ui, project=self.project)
        self.last_import_failures: list[str] = []
        self.workspace_preferences = workspace_preferences or WorkspacePreferences()
        restored_workspace = self.workspace_preferences.load()
        self._layout_state = SplitterLayoutState(self.workspace_preferences.settings)
        self.ui_density_factor = 1.0
        self._ui_scale_percent = restored_workspace.ui_scale_percent
        self._density = UiDensity()
        self._interface_scaling = False
        self._applied_density: float | None = None
        self._interface_scale_timer = QTimer(self)
        self._interface_scale_timer.setSingleShot(True)
        self._interface_scale_timer.timeout.connect(self._update_interface_scaling)
        self._dark_theme = is_dark_theme(self)
        self.setObjectName("spectroscopyFinderWindow")
        self.setWindowTitle("IR/Raman Phase Finder")
        self.resize(1440, 900)
        self.setStyleSheet(window_style(self._dark_theme))

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 6, 8, 4)
        root.setSpacing(6)
        self.top_toolbar = FinderTopToolbar()
        root.addWidget(self.top_toolbar)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("projectSidebar")
        self.sidebar.setMinimumWidth(170)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(6)
        self.project_controls = ProjectControlsWidget()
        sidebar_layout.addWidget(self.project_controls)
        self.project_tree = ProjectTree()
        self.project_tree.setObjectName("projectTree")
        sidebar_layout.addWidget(self.project_tree, 1)
        self.add_series_button = self.project_controls.add_series_button
        self.move_up_button = self.project_controls.move_up_button
        self.move_down_button = self.project_controls.move_down_button

        self.center = QWidget()
        center_layout = QVBoxLayout(self.center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(6)
        self.plot_host = QWidget()
        plot_layout = QVBoxLayout(self.plot_host)
        plot_layout.setContentsMargins(0, 0, 0, 0)
        plot_layout.setSpacing(6)
        self.plot_control_bar = FinderPlotControlBar()
        self.spectrum_plot = create_vibrational_plot_widget()
        self.spectrum_plot.setObjectName("spectrumPlot")
        self.plot_canvas = SpectrumPlotCanvas(self.spectrum_plot)
        plot_layout.addWidget(self.plot_canvas, 1)
        plot_layout.addWidget(self.plot_control_bar)
        self.band_information_card = BandInformationCard(self.plot_host)
        self._selected_band_index: int | None = None
        self.center_splitter = QSplitter(Qt.Orientation.Vertical)
        self.center_splitter.setObjectName("centerSplitter")
        self._layout_state.register("center_splitter", self.center_splitter)
        self.center_splitter.addWidget(self.plot_host)
        self.candidate_workspace = CandidateWorkspace()
        self.candidate_workspace.status_label.messagePublished.connect(self.statusBar().showMessage)
        self.candidate_workspace.table.horizontalHeader().setSectionsMovable(True)
        self._layout_state.register_table("candidates", self.candidate_workspace.table)
        self.candidate_workspace.search_controls.hide()
        self.candidate_panel = self.candidate_workspace
        self.center_splitter.addWidget(self.candidate_panel)
        self.center_splitter.setStretchFactor(0, 3)
        self.center_splitter.setStretchFactor(1, 2)
        self.center_splitter.setSizes([520, 260])
        center_layout.addWidget(self.center_splitter, 1)

        self.accepted_components_workspace = AcceptedComponentsWorkspace()
        self.accepted_components_workspace.table.horizontalHeader().setSectionsMovable(True)
        self._layout_state.register_table("accepted", self.accepted_components_workspace.table)
        self.accepted_components_panel = self.accepted_components_workspace
        self.composition_panel = SpectroscopyCompositionPanel(self.accepted_components_workspace)
        self._layout_state.register("composition_splitter", self.composition_panel.splitter)
        self.element_states: dict[str, str] = {}
        self.selected_element_order: list[str] = []
        self.exclude_all_other_elements = False
        self._search_mode = "search"
        self._restore_composition_filter_from_project()
        self.action_bar = FinderActionBar()
        self.sample_metadata_panel = SampleMetadataPanel()
        self.compound_details_panel = QWidget()
        details_layout = QVBoxLayout(self.compound_details_panel)
        details_layout.setContentsMargins(6, 6, 6, 6)
        details_layout.addWidget(self.sample_metadata_panel)

        self.right_tabs = QTabWidget()
        self.right_tabs.setObjectName("analysisSidebar")
        self.right_tabs.setMinimumWidth(280)
        self.right_tabs.addTab(self.composition_panel, "Elements")
        self.right_tabs.addTab(self.action_bar, "Processing")
        self.right_tabs.addTab(self.compound_details_panel, "Compound details")
        self.analysis_tabs = self.right_tabs

        self.source_settings_panel = SourceSettingsPanel(
            self.source_catalog, settings=self.workspace_preferences.settings, defer_refresh=defer_source_settings,
        )
        self.source_settings_dialog = QDialog(self)
        self.source_settings_dialog.setObjectName("sourceSettingsDialog")
        self.source_settings_dialog.setWindowTitle("Spectroscopy databases")
        self.source_settings_dialog.setModal(False)
        source_dialog_layout = QVBoxLayout(self.source_settings_dialog)
        source_dialog_layout.setContentsMargins(8, 8, 8, 8)
        source_dialog_layout.addWidget(self.source_settings_panel)
        self.source_settings_dialog.resize(920, 650)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("workspaceSplitter")
        self._layout_state.register("main_splitter", self.main_splitter)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.center)
        self.main_splitter.addWidget(self.right_tabs)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setStretchFactor(2, 1)
        self.main_splitter.setHandleWidth(8)
        self.main_splitter.setSizes([190, 920, 390])
        self.workspace_splitter = self.main_splitter
        root.addWidget(self.main_splitter, 1)
        self.setCentralWidget(central)
        self._layout_state.add_pin_corner(self.right_tabs, None)
        self.top_toolbar.attach_layout_controls(
            self._layout_state.pin_button,
            self._layout_state.help_button,
        )
        self._layout_state.restore()
        for name, splitter in self._layout_state._splitters.items():
            splitter.splitterMoved.connect(
                lambda _position, _index, key=name, target=splitter: self._remember_splitter_ratio(key, target)
            )

        self.project_tree_controller = ProjectTreeController(self)
        self.project_tree.active_spectrum_requested.connect(self.set_active_spectrum)
        self.project_tree.series_create_requested.connect(self._prompt_create_series)
        self.project_tree.object_rename_requested.connect(self._prompt_rename_object)
        self.project_tree.object_delete_requested.connect(self._prompt_delete_object)
        self.project_tree.object_move_to_series_requested.connect(
            lambda object_type, object_id, series_id: self.project_tree_controller.move_spectrum_to_series(
                object_id, series_id or None
            )
            if object_type == "spectrum"
            else None
        )
        self.project_tree.object_reorder_requested.connect(self.project_tree_controller.reorder_object)
        self.project_controls.addSeriesRequested.connect(self._prompt_create_series)
        self.project_controls.moveRequested.connect(self._reorder_current_object)
        self.sample_metadata_panel.metadataEdited.connect(self._sample_metadata_edited)
        self.composition_panel.requiredElementToggled.connect(self._toggle_required_element)
        self.composition_panel.excludedElementToggled.connect(self._toggle_excluded_element)
        self.composition_panel.elementsPainted.connect(self._paint_elements)
        self.composition_panel.exclusionModeToggleRequested.connect(self._toggle_excluded_mode)
        self.composition_panel.searchRequested.connect(self._search_candidates_in_current_mode)
        self.composition_panel.resetRequested.connect(self._clear_composition_search)
        self.composition_panel.query_edit.textChanged.connect(self.candidate_workspace.query_edit.setText)
        self.top_toolbar.newProjectRequested.connect(lambda: self.request_new_project())
        self.top_toolbar.openProjectRequested.connect(lambda: self.request_open_project())
        self.top_toolbar.saveProjectRequested.connect(lambda: self.request_save_project())
        self._init_spectrum_import_actions()
        self._init_spectrum_processing_actions()
        self._init_plot_display_actions()
        self._init_analysis_actions()
        self._init_publication_export_actions()
        self.top_toolbar.resetProcessingRequested.connect(self.reset_active_processing)
        self.top_toolbar.fitPlotRequested.connect(self.fit_active_plot)
        self.spectrum_plot.getViewBox().full_range_callback = self.fit_active_plot
        self.top_toolbar.spectralSettingsRequested.connect(
            lambda: self.right_tabs.setCurrentWidget(self.action_bar)
        )
        self._build_menu_bar()
        from vibrational_finder.ui.context_help import ContextHelpController

        self._context_help = ContextHelpController(self)
        self._layout_state.help_button.toggled.connect(self._context_help.set_enabled)
        self.restore_workspace_state(restored_workspace)
        self._update_interface_scaling()
        self._set_search_mode("search")
        self._refresh_project_tree()
        initial = self.project.active_spectrum_key
        if initial is None:
            ordered = self._ordered_spectra()
            initial = ordered[0].id if ordered else None
        if not defer_initial_plot:
            self.set_active_spectrum(initial)
        self.apply_native_theme(self._dark_theme)
        self._theme_observer = SystemThemeObserver(self)
        self._theme_observer.changed.connect(lambda dark, _previous: self.apply_native_theme(dark))

    @staticmethod
    def _placeholder(text: str, object_name: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setEnabled(False)
        return label

    def _ordered_spectra(self) -> list[ObservedSpectrum]:
        return observed_spectra(self.project)

    def _build_menu_bar(self) -> None:
        from vibrational_finder.ui.finder_menu import build_finder_menu_bar

        build_finder_menu_bar(self)

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "IR/Raman Phase Finder",
            "Import Raman or FTIR spectra, process the signal, select chemical filters, "
            "identify compounds, and export a publication-ready figure.",
        )

    def _refresh_project_tree(self) -> None:
        self.project_tree.set_project(
            project_id=self.project.project_id,
            project_name=self.project.project_name,
            spectra=self._ordered_spectra(),
            series=self.project.series,
            spectrum_order_ids=self.project.spectrum_order_ids,
        )

    def active_spectrum(self) -> ObservedSpectrum | None:
        active_id = self.project.active_spectrum_key
        return next((item for item in self._ordered_spectra() if item.id == active_id), None)

    def set_active_spectrum(self, spectrum_id: str | None) -> None:
        if spectrum_id != self.project.active_spectrum_key and hasattr(self, "_preview_result"):
            self._preview_result = None
        if (
            hasattr(self, "processing_controller")
            and spectrum_id != self.project.active_spectrum_key
            and self._active_processing_key != "bands"
        ):
            self.cancel_processing_preview()
        spectrum = next((item for item in self._ordered_spectra() if item.id == spectrum_id), None)
        self.project.active_spectrum_key = spectrum.id if spectrum is not None else None
        if spectrum is not None:
            blocked = self.project_tree.blockSignals(True)
            self.project_tree.select_object("spectrum", spectrum.id)
            self.project_tree.blockSignals(blocked)
            metadata = dict(self.project.sample_metadata.get(spectrum.id, {}))
            metadata.setdefault("name", spectrum.name)
            metadata.setdefault("source_path", spectrum.source_path)
            metadata.setdefault("method", spectrum.kind.value.upper())
            self.sample_metadata_panel.set_metadata(metadata, spectrum_name=spectrum.name)
        elif hasattr(self, "sample_metadata_panel"):
            self.sample_metadata_panel.clear()
        self._selected_band_index = None
        self.band_information_card.hide()
        self._redraw_active_spectrum()
        if hasattr(self, "processing_controller"):
            self._refresh_processing_controls()
            self._refresh_band_workspace()
        if hasattr(self, "candidate_workspace"):
            self._refresh_candidate_workspace()
            self._refresh_accepted_components_workspace()

    def _redraw_active_spectrum(self, *, preserve_view: bool = False, preserve_x_range: bool = False) -> None:
        spectrum = self.active_spectrum()
        primary, overlays = self._spectra_for_plot(spectrum)
        active_visible = spectrum is not None and primary is not None and primary.id == spectrum.id
        displayed = ((primary, 0.0), *overlays) if primary is not None else ()
        bands = self.project.sample_bands.get(primary.id, []) if primary is not None else []
        settings = self.project.ui.plot_view_settings
        label_options = {
            "show_mode_labels": bool(settings.get("layer_reference_mode_labels_visible", True)),
            "show_assignment_labels": bool(settings.get("layer_reference_assignment_labels_visible", False)),
        }
        show_observed_spectrum(
            self.spectrum_plot,
            primary,
            bands=bands,
            selected_band_index=self._selected_band_index if active_visible else None,
            show_band_labels=active_visible and self._search_mode == "bands",
            on_band_selected=self.select_band if active_visible else None,
            preserve_view=preserve_view,
            preserve_x_range=preserve_x_range,
            overlays=overlays,
            overlay_bands=self.project.sample_bands,
            all_observed_black=bool(settings.get("all_observed_black", False)),
            **label_options,
        )
        if self.plot_control_bar.normalize_checkbox.isChecked():
            self.spectrum_plot.setLabel("left", "Relative intensity")
        else:
            self.spectrum_plot.setLabel("left", "Intensity", units="a.u.")
        preview = getattr(self, "_preview_result", None)
        if primary is not None and preview is not None and preview.candidate.kind not in {
            primary.kind, SignalKind.UNKNOWN,
        }:
            preview = None
        phases_by_spectrum = {}
        for observed, offset in displayed or ((None, 0.0),):
            profile = self.project.profile_states.get(observed.id) if observed is not None else None
            results = list(profile.selected_results) if profile is not None else []
            visible_keys = set(profile.visible_selected_candidate_keys) if profile is not None else set()
            if observed is not None:
                phases_by_spectrum[observed.id] = [
                    PhaseLegendEntry(result.candidate.key, result.candidate.name or result.candidate.entry_id,
                                     self.project.candidate_colors.get(result.candidate.key, REFERENCE_COLOR))
                    for result in results if result.candidate.key in visible_keys
                ]
            preview_key = None
            if (preview is not None and (observed is None or (active_visible and observed is primary))
                    and not any(item.candidate.key == preview.candidate.key for item in results)):
                preview_key = preview.candidate.key
                results.append(preview)
                visible_keys.add(preview_key)
            if not results and profile is None:
                continue
            show_reference_layers(
                self.spectrum_plot,
                results,
                visible_keys,
                self.project.candidate_colors,
                residual_bands=profile.cumulative_unassigned_bands
                if active_visible and observed is primary and profile is not None else None,
                observed=observed,
                preview_key=preview_key,
                preserve_view=primary is not None,
                show_profiles=bool(settings.get("layer_phase_profiles_visible", True)),
                show_bands=bool(settings.get("layer_phase_ticks_visible", True)),
                show_peak_markers=bool(settings.get("layer_reference_peak_markers_visible", False)),
                show_reference_ticks=bool(settings.get("layer_reference_shift_ticks_visible", True)),
                display_offset=offset,
                clear_existing=False,
                fit_markers=not preserve_view,
                observed_bands=self.project.sample_bands.get(observed.id, ()) if observed is not None else (),
                **label_options,
            )
        if primary is not None and not preserve_view and any(
            (tag := canvas_item_tag(item)) is not None
            and tag.layer in {CanvasLayer.REFERENCE_BANDS, CanvasLayer.REFERENCE_TICKS, CanvasLayer.ASSIGNED_BANDS}
            for item in self.spectrum_plot.plotItem.items
        ):
            kept_x = self.spectrum_plot.viewRange()[0] if preserve_x_range else None
            self.spectrum_plot.autoRange(padding=.045)
            _, (bottom, top) = self.spectrum_plot.viewRange()
            self.spectrum_plot.setYRange(bottom, top + (top - bottom) * .10, padding=0)
            if kept_x is not None:
                self.spectrum_plot.setXRange(*kept_x, padding=0)
        show_spectrum_legends(
            self.spectrum_plot, [observed for observed, _ in displayed], phases_by_spectrum,
            settings=settings, multi=self._in_multi_spectra_mode(), on_move=self._remember_spectrum_legend_position,
        )
        self._apply_plot_appearance()
        if not getattr(self, "_band_annotation_layout_wired", False):
            view = self.spectrum_plot.getViewBox()
            view.sigRangeChanged.connect(self._reposition_band_annotations)
            view.sigResized.connect(self._reposition_band_annotations)
            self._band_annotation_layout_wired = True
        self._reposition_band_annotations()

    def _reposition_band_annotations(self, *_args) -> None:
        if self.spectrum_plot.isVisible():
            layout_band_annotations(self.spectrum_plot)

    def select_band(self, index: int) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            return
        bands = self.project.sample_bands.get(spectrum.id, [])
        if not 0 <= index < len(bands):
            return
        self._selected_band_index = index
        self._redraw_active_spectrum(preserve_view=True)
        if self._active_processing_key == "bands" and hasattr(self._active_processing_panel, "select_band_row"):
            self._active_processing_panel.select_band_row(index)
        self.band_information_card.set_band(spectrum, bands[index], index)
        self.band_information_card.show_anchored()

    def _sample_metadata_edited(self, metadata: dict[str, str]) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None or self.project.sample_metadata.get(spectrum.id) == metadata:
            return
        self.project.sample_metadata[spectrum.id] = dict(metadata)
        self.document.mark_changed()

    def _prompt_create_series(self) -> None:
        default = f"Series {len(self.project.series) + 1}"
        name, accepted = QInputDialog.getText(self, "Add series", "Name:", text=default)
        if accepted and name.strip():
            self.project_tree_controller.create_series(name)

    def _prompt_rename_object(self, object_type: str, object_id: str) -> None:
        if object_type == "project":
            current = self.project.project_name
        elif object_type == "series":
            item = next((item for item in self.project.series if item.id == object_id), None)
            current = item.name if item is not None else ""
        else:
            item = next((item for item in self._ordered_spectra() if item.id == object_id), None)
            current = item.name if item is not None else ""
        if not current:
            return
        name, accepted = QInputDialog.getText(self, "Rename", "Name:", text=current)
        if accepted:
            self.project_tree_controller.rename_object(object_type, object_id, name)

    def _prompt_delete_object(self, object_type: str, object_id: str) -> None:
        if object_type == "series":
            item = next((item for item in self.project.series if item.id == object_id), None)
            label = item.name if item is not None else "series"
            detail = "Its spectra will remain under No series."
        else:
            item = next((item for item in self._ordered_spectra() if item.id == object_id), None)
            label = item.name if item is not None else "spectrum"
            detail = "This removes the spectrum and its project metadata."
        answer = QMessageBox.question(
            self,
            "Delete project item",
            f"Delete '{label}'?\n\n{detail}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.project_tree_controller.delete_object(object_type, object_id)

    def _reorder_current_object(self, direction: int) -> None:
        current = self.project_tree.current_object()
        if current is not None:
            self.project_tree_controller.reorder_object(current[0], current[1], direction)

    def _restore_composition_filter_from_project(self) -> None:
        valid = {"required", "excluded"}
        states = {
            str(element): str(state)
            for element, state in self.project.ui.element_states.items()
            if str(state) in valid
        }
        order = [
            str(element) for element in self.project.ui.selected_element_order
            if states.get(str(element)) == "required"
        ]
        if not states and self.project.ui.composition_elements:
            legacy = list(dict.fromkeys(str(item) for item in self.project.ui.composition_elements))
            states = {element: "required" for element in legacy}
            order = legacy
            if self.project.ui.composition_mode == "only" and hasattr(self, "composition_panel"):
                for element in self.composition_panel.element_table.element_symbols:
                    if element not in states:
                        states[element] = "excluded"
                self.project.ui.exclude_all_other_elements = True
        self.element_states = states
        self.selected_element_order = order
        self.exclude_all_other_elements = bool(self.project.ui.exclude_all_other_elements)
        self._refresh_composition_filter_view()

    def _toggle_required_element(self, element: str) -> None:
        state = "neutral" if self.element_states.get(element) == "required" else "required"
        self._set_element_state(element, state)
        self._store_composition_filter()

    def _toggle_excluded_element(self, element: str) -> None:
        state = "neutral" if self.element_states.get(element) == "excluded" else "excluded"
        self._set_element_state(element, state)
        self._store_composition_filter()

    def _paint_elements(self, elements: list[str], state: str) -> None:
        if state not in {"required", "excluded", "neutral"}:
            return
        for element in elements:
            self._set_element_state(element, state)
        self._store_composition_filter()

    def _toggle_excluded_mode(self) -> None:
        if self.exclude_all_other_elements:
            for element in list(self.element_states):
                if self.element_states.get(element) == "excluded":
                    self._set_element_state(element, "neutral")
            self.exclude_all_other_elements = False
        else:
            for element in self.composition_panel.element_table.element_symbols:
                if self.element_states.get(element, "neutral") == "neutral":
                    self._set_element_state(element, "excluded")
            self.exclude_all_other_elements = True
        self._store_composition_filter()

    def _set_element_state(self, element: str, state: str) -> None:
        if state == "optional":
            state = "neutral"
        if state == "neutral":
            self.element_states.pop(element, None)
        else:
            self.element_states[element] = state
        if state == "required":
            if element not in self.selected_element_order:
                self.selected_element_order.append(element)
        elif element in self.selected_element_order:
            self.selected_element_order.remove(element)
        if hasattr(self, "composition_panel"):
            self.composition_panel.element_table.set_element_state(element, state)

    def _store_composition_filter(self) -> None:
        self.project.ui.selected_element_order = list(self.selected_element_order)
        self.project.ui.element_states = dict(self.element_states)
        self.project.ui.exclude_all_other_elements = self.exclude_all_other_elements
        self.project.ui.composition_mode = "only" if self.exclude_all_other_elements else "contains"
        self.project.ui.composition_elements = list(self.selected_element_order)
        self.document.mark_changed()
        self._refresh_composition_filter_view()

    def _refresh_composition_filter_view(self) -> None:
        if not hasattr(self, "composition_panel"):
            return
        for element in self.composition_panel.element_table.element_symbols:
            self.composition_panel.element_table.set_element_state(
                element, self.element_states.get(element, "neutral")
            )
        required = [item for item in self.selected_element_order if self.element_states.get(item) == "required"]
        excluded = sorted(item for item, state in self.element_states.items() if state == "excluded")
        if not required and not excluded:
            summary = "Chemical filter: none"
        else:
            parts = []
            if required:
                parts.append("required: " + ", ".join(required))
            if excluded:
                parts.append(f"excluded: {len(excluded)}")
            summary = "Chemical filter: " + "; ".join(parts)
        self.composition_panel.filter_summary.setText(summary)
        self.composition_panel.element_table.set_excluded_mode(self.exclude_all_other_elements)

    def _candidate_allowed(self, candidate: object) -> bool:
        return self._formula_allowed(str(getattr(candidate, "formula", "")))

    def _formula_allowed(self, formula: str) -> bool:
        return self._composition_query("", SignalKind.UNKNOWN).allows_formula(formula)

    def _clear_composition_search(self) -> None:
        self._cancel_analysis_jobs()
        self._clear_candidate_preview()
        if self._search_mode != "bands":
            self._set_search_mode("search")
        self.element_states.clear()
        self.selected_element_order.clear()
        self.exclude_all_other_elements = False
        self.project.ui.element_states = {}
        self.project.ui.selected_element_order = []
        self.project.ui.exclude_all_other_elements = False
        self.project.ui.composition_mode = "contains"
        self.project.ui.composition_elements = []
        self.composition_panel.query_edit.clear()
        self.candidate_workspace.set_results([])
        self.document.mark_changed()
        self._refresh_composition_filter_view()

    def capture_workspace_state(self) -> WorkspaceState:
        sizes = self.workspace_splitter.sizes()
        try:
            ratios = normalize_splitter_ratios(sizes, 3)
        except ValueError:
            ratios = (0.18, 0.60, 0.22)
        try:
            center_ratios = normalize_splitter_ratios(self.center_splitter.sizes(), 2)
        except ValueError:
            center_ratios = (2 / 3, 1 / 3)
        try:
            composition_ratios = normalize_splitter_ratios(self.composition_panel.splitter.sizes(), 2)
        except ValueError:
            composition_ratios = (0.4, 0.6)
        return WorkspaceState(
            density=self._ui_scale_percent / 100.0,
            ui_scale_percent=self._ui_scale_percent,
            splitter_ratios={
                "main_splitter": ratios,
                "center_splitter": center_ratios,
                "composition_splitter": composition_ratios,
                # Read compatibility for the 1.0.4 modular preview.
                "main": ratios,
                "center": center_ratios,
            },
            table_column_proportions={
                "candidates": self._table_column_proportions(self.candidate_workspace.table),
                "accepted": self._table_column_proportions(self.accepted_components_workspace.table),
            },
            table_column_order={
                "candidates": self._table_column_order(self.candidate_workspace.table),
                "accepted": self._table_column_order(self.accepted_components_workspace.table),
            },
            plot_aspect_mode=self.plot_control_bar.plot_aspect_mode.currentText(),
        )

    def restore_workspace_state(self, state: WorkspaceState) -> None:
        self._ui_scale_percent = (
            state.ui_scale_percent
            if state.ui_scale_percent in INTERFACE_SCALE_PERCENTAGES
            else 100
        )
        if hasattr(self, "ui_scale_combo"):
            blocked = self.ui_scale_combo.blockSignals(True)
            self.ui_scale_combo.setCurrentText(f"UI {self._ui_scale_percent}%")
            self.ui_scale_combo.blockSignals(blocked)
        ratios = state.splitter_ratios.get("main_splitter", state.splitter_ratios.get("main"))
        if ratios is not None:
            try:
                normalized = normalize_splitter_ratios(ratios, 3)
            except (TypeError, ValueError):
                normalized = None
            if normalized is not None:
                self._set_splitter_ratios(self.workspace_splitter, normalized)
        center_ratios = state.splitter_ratios.get("center_splitter", state.splitter_ratios.get("center"))
        if center_ratios is not None:
            try:
                normalized_center = normalize_splitter_ratios(center_ratios, 2)
            except (TypeError, ValueError):
                normalized_center = None
            if normalized_center is not None:
                self._set_splitter_ratios(self.center_splitter, normalized_center)
        composition_ratios = state.splitter_ratios.get("composition_splitter")
        if composition_ratios is not None:
            try:
                normalized_composition = normalize_splitter_ratios(composition_ratios, 2)
            except (TypeError, ValueError):
                normalized_composition = None
            if normalized_composition is not None:
                self._set_splitter_ratios(self.composition_panel.splitter, normalized_composition)
        aspect_index = self.plot_control_bar.plot_aspect_mode.findText(state.plot_aspect_mode)
        if aspect_index >= 0:
            self.plot_control_bar.plot_aspect_mode.setCurrentIndex(aspect_index)
        self._restore_table_layout(
            self.candidate_workspace.table,
            state.table_column_proportions.get("candidates"),
            state.table_column_order.get("candidates"),
        )
        self._restore_table_layout(
            self.accepted_components_workspace.table,
            state.table_column_proportions.get("accepted"),
            state.table_column_order.get("accepted"),
        )

    @staticmethod
    def _table_column_proportions(table) -> tuple[float, ...]:
        if hasattr(table, "column_layout_state"):
            return tuple(table.column_layout_state()["proportions"])
        widths = tuple(max(1, table.columnWidth(index)) for index in range(table.columnCount()))
        total = sum(widths)
        return tuple(width / total for width in widths)

    @staticmethod
    def _table_column_order(table) -> tuple[int, ...]:
        header = table.horizontalHeader()
        return tuple(header.logicalIndex(visual) for visual in range(table.columnCount()))

    @staticmethod
    def _restore_table_layout(table, proportions, order) -> None:
        count = table.columnCount()
        if hasattr(table, "restore_column_layout"):
            table.restore_column_layout({"proportions": proportions, "order": order})
            return
        if isinstance(order, (list, tuple)) and len(order) == count and set(order) == set(range(count)):
            header = table.horizontalHeader()
            for visual, logical in enumerate(order):
                current = header.visualIndex(int(logical))
                if current != visual:
                    header.moveSection(current, visual)
        if isinstance(proportions, (list, tuple)) and len(proportions) == count:
            try:
                normalized = normalize_splitter_ratios(proportions, count)
            except (TypeError, ValueError):
                return
            available = max(count, table.viewport().width())
            for column, ratio in enumerate(normalized):
                table.setColumnWidth(column, max(6, round(available * ratio)))

    @staticmethod
    def _set_splitter_ratios(splitter: QSplitter, ratios: tuple[float, ...]) -> None:
        available = sum(splitter.sizes())
        if available <= 0:
            available = max(100, splitter.width() - splitter.handleWidth() * (splitter.count() - 1))
        splitter.setSizes([max(1, round(value * available)) for value in ratios])

    def apply_native_theme(self, dark: bool) -> None:
        active_id = self.project.active_spectrum_key
        view_range = self.spectrum_plot.viewRange()
        self._dark_theme = bool(dark)
        self.setStyleSheet(window_style(self._dark_theme))
        self.top_toolbar._apply_style(self._dark_theme)
        # The scientific canvas is paper-like in both application themes.
        # XRD keeps the plot independent from surrounding chrome; Raman/FTIR
        # uses the same rule so figures never change appearance with macOS.
        self.spectrum_plot.setBackground("#ffffff")
        for axis_name in ("bottom", "left", "top", "right"):
            axis = self.spectrum_plot.getAxis(axis_name)
            axis.setPen("#111111")
            axis.setTextPen("#111111")
        self.project.active_spectrum_key = active_id
        self.spectrum_plot.setRange(xRange=view_range[0], yRange=view_range[1], padding=0)
        self.centralWidget().style().unpolish(self.centralWidget())
        self.centralWidget().style().polish(self.centralWidget())
        self._applied_density = None
        self._update_interface_scaling()

    def _set_interface_scale(self, text: str) -> None:
        try:
            percent = int(text.removeprefix("UI ").rstrip("%"))
        except ValueError:
            return
        if percent not in INTERFACE_SCALE_PERCENTAGES:
            return
        self._ui_scale_percent = percent
        self._applied_density = None
        self._update_interface_scaling()
        self.workspace_preferences.save(self.capture_workspace_state())

    def _update_interface_scaling(self) -> None:
        if self._interface_scaling:
            return
        self._interface_scaling = True
        try:
            factor = interface_density_factor(self.width(), self.height(), self._ui_scale_percent)
            self.ui_density_factor = factor
            if factor != self._applied_density:
                self._density.apply(self, factor)
                self._applied_density = factor
            self._layout_state.apply_lock()
            self.layout().activate()
            self._layout_state.apply_proportions()
            self.composition_panel.element_table._fit_cells_to_area()
        finally:
            self._interface_scaling = False

    def is_workspace_layout_editable(self) -> bool:
        return not self._layout_state.pinned

    def begin_workspace_layout_edit(self) -> None:
        self._layout_state.set_pinned(False)

    def save_workspace_layout(self) -> None:
        captured = self.capture_workspace_state()
        self.workspace_preferences.save(captured)
        self._layout_state.set_pinned(True)

    def _set_workspace_layout_editable(self, editable: bool) -> None:
        self._layout_state.set_pinned(not editable)

    def _remember_splitter_ratio(self, name: str, splitter: QSplitter) -> None:
        if not self._layout_state.pinned:
            self._layout_state.remember_splitter_proportions(name, splitter)

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._update_interface_scaling()
        self._layout_state.apply_proportions()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "_interface_scale_timer"):
            self._interface_scale_timer.start(0)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self.isVisible() and not self._confirm_document_replacement("close the project"):
            event.ignore()
            return
        captured = self.capture_workspace_state()
        self.workspace_preferences.save(captured)
        self._layout_state.save()
        self._shutdown_analysis_jobs()
        super().closeEvent(event)

