from __future__ import annotations

from finder_core.data_sources import SourceQuery
from finder_core.models import MatchScore, SignalKind

from vibrational_finder.analysis_controller import AnalysisController
from vibrational_finder.band_detection import extract_reference_band_set
from vibrational_finder.matching import score_candidate
from vibrational_finder.models import CompoundCandidate, VibrationalMatchResult
from vibrational_finder.preprocessing import preprocess_spectrum
from vibrational_finder.services.candidate_search_service import CandidateSearchOptions
from vibrational_finder.ui.analysis_job_controller import AnalysisJobController
from vibrational_finder.ui.source_management_jobs import SourceManagementJobController
from vibrational_finder.accepted_components_controller import AcceptedComponentsController
from vibrational_finder.residual_search import (
    ResidualSearchController,
    ResidualSearchUnavailable,
    build_residual_request,
)


class SpectroscopyAnalysisActionsMixin:
    def _init_analysis_actions(self) -> None:
        self.analysis_controller = AnalysisController(self.document)
        self.accepted_components_controller = AcceptedComponentsController(self.document)
        self.analysis_job_controller = AnalysisJobController(self.analysis_controller, self)
        self.residual_search_controller = ResidualSearchController(self.analysis_controller)
        self.residual_job_controller = AnalysisJobController(self.residual_search_controller, self)
        self.source_management_job_controller = SourceManagementJobController(
            self.source_settings_panel.manager,
            self,
        )
        self.top_toolbar.matchRequested.connect(self._identify_compounds)
        self.top_toolbar.detectBandsRequested.connect(self._toggle_band_search)
        self.top_toolbar.residualSearchRequested.connect(self.start_residual_search)
        self.top_toolbar.databaseRequested.connect(self._show_source_settings)
        self.candidate_workspace.matchRequested.connect(self.start_match)
        self.candidate_workspace.cancelRequested.connect(self._cancel_analysis_jobs)
        self.candidate_workspace.previewRequested.connect(self.preview_candidate)
        self.candidate_workspace.acceptRequested.connect(self.accept_candidate)
        self.source_settings_panel.sourcesChanged.connect(self._analysis_sources_changed)
        self.source_settings_panel.updateRequested.connect(
            lambda name, package: self._start_source_operation(name, "update", package or None)
        )
        self.source_settings_panel.clearCacheRequested.connect(
            lambda name: self._start_source_operation(name, "clear")
        )
        self.source_settings_panel.buildIndexRequested.connect(
            lambda name: self._start_source_operation(name, "build_index")
        )
        self.source_settings_panel.clearIndexRequested.connect(
            lambda name: self._start_source_operation(name, "clear_index")
        )
        self.source_management_job_controller.pending.connect(self.source_settings_panel.set_operation_pending)
        self.source_management_job_controller.succeeded.connect(self._source_operation_succeeded)
        self.source_management_job_controller.failed.connect(
            lambda name, operation, message, _details: self.source_settings_panel.set_operation_failed(
                name, operation, message
            )
        )
        self.source_management_job_controller.cancelled.connect(self.source_settings_panel.set_operation_cancelled)
        self.accepted_components_workspace.visibilityChanged.connect(self._set_component_visible)
        self.accepted_components_workspace.removeRequested.connect(self._remove_component)
        self.accepted_components_workspace.clearRequested.connect(self._clear_components)
        self.analysis_job_controller.pending.connect(lambda _request: self.candidate_workspace.set_pending())
        self.analysis_job_controller.succeeded.connect(self._ordinary_search_succeeded)
        self.analysis_job_controller.failed.connect(lambda message, _details: self.candidate_workspace.set_failed(message))
        self.analysis_job_controller.cancelled.connect(self.candidate_workspace.set_cancelled)
        self.analysis_job_controller.stale.connect(
            lambda _outcome: self.candidate_workspace.set_failed("Results became stale after the project changed")
        )
        self.residual_job_controller.pending.connect(lambda _request: self.candidate_workspace.set_pending())
        self.residual_job_controller.succeeded.connect(self._residual_search_succeeded)
        self.residual_job_controller.failed.connect(lambda message, _details: self.candidate_workspace.set_failed(message))
        self.residual_job_controller.cancelled.connect(self.candidate_workspace.set_cancelled)
        self.residual_job_controller.stale.connect(
            lambda _outcome: self.candidate_workspace.set_failed("Next-component results became stale")
        )
        self._preview_result: VibrationalMatchResult | None = None
        self._browse_sources_by_key: dict[str, object] = {}
        self._refresh_candidate_workspace()
        self._refresh_accepted_components_workspace()

    def _set_search_mode(self, mode: str) -> None:
        if mode not in {"search", "auto", "bands"}:
            raise ValueError(f"Unknown search mode: {mode}")
        labels_changed = (self._search_mode == "bands") != (mode == "bands")
        self._search_mode = mode
        self.top_toolbar.set_search_mode(mode)
        self.composition_panel.set_search_mode(mode)
        if labels_changed:
            self._redraw_active_spectrum(preserve_view=True)

    def _identify_compounds(self) -> None:
        self._set_search_mode("auto")
        self.start_match(auto_match=True)

    def _toggle_band_search(self) -> None:
        if self._search_mode == "bands":
            self._cancel_analysis_jobs()
            self._set_search_mode("search")
            return
        if self.active_spectrum() is None:
            self.top_toolbar.set_search_mode(self._search_mode)
            self.candidate_workspace.set_unavailable("Import or select a Raman/FTIR spectrum first")
            return
        self._cancel_analysis_jobs()
        self._set_search_mode("bands")
        self._open_band_workspace()
        self.right_tabs.setCurrentWidget(self.action_bar)

    def _search_candidates_in_current_mode(self, query_text: str = "") -> None:
        if self._search_mode == "search":
            self._browse_reference_sources(query_text)
            return
        if self._search_mode == "bands":
            spectrum = self.active_spectrum()
            bands = self.project.sample_bands.get(spectrum.id, []) if spectrum is not None else []
            if not bands:
                self.candidate_workspace.set_unavailable(
                    "Detect or add at least one Raman/FTIR band before Band search"
                )
                return
        self.start_match(query_text, auto_match=self._search_mode in {"auto", "bands"})

    def _browse_reference_sources(self, query_text: str = "") -> None:
        self._cancel_analysis_jobs()
        self._clear_candidate_preview()
        self._browse_sources_by_key.clear()
        include_raman = bool(self.project.ui.include_raman)
        include_ftir = bool(self.project.ui.include_ftir)
        if include_raman and include_ftir:
            kind = SignalKind.UNKNOWN
        elif include_raman:
            kind = SignalKind.RAMAN
        elif include_ftir:
            kind = SignalKind.FTIR
        else:
            self.candidate_workspace.set_unavailable("Enable Raman references, FTIR references, or both")
            return
        sources = self.source_catalog.enabled_sources(kind)
        if not sources:
            self.candidate_workspace.set_unavailable("No enabled reference source is available")
            return
        self.candidate_workspace.set_pending()
        query = self._composition_query(query_text, kind)
        records = []
        failures: list[str] = []
        for source in sources:
            try:
                for record in source.search(query):
                    if record.key in self._browse_sources_by_key or not query.allows_formula(record.formula):
                        continue
                    self._browse_sources_by_key[record.key] = source
                    records.append(record)
            except Exception:
                failures.append(str(getattr(source, "name", type(source).__name__)))
        self.candidate_workspace.set_records(records)
        if failures:
            self.candidate_workspace.status_label.setText(
                f"{len(records)} references; unavailable: {', '.join(sorted(failures))}"
            )
        elif not records:
            self.candidate_workspace.status_label.setText("No references found; check the name and element filters")

    def start_match(self, query_text: str | None = None, *, auto_match: bool | None = None) -> None:
        self.residual_job_controller.cancel()
        self._clear_candidate_preview()
        spectrum = self.active_spectrum()
        if spectrum is None:
            self.candidate_workspace.set_unavailable("Select a Raman or FTIR spectrum first")
            return
        sources = self.source_catalog.enabled_sources(spectrum.kind)
        if not sources:
            self.candidate_workspace.set_unavailable("No enabled source is available for this spectrum")
            return
        text = self.candidate_workspace.query_edit.text().strip() if query_text is None else str(query_text).strip()
        query = self._composition_query(text, spectrum.kind)
        staged_match = self._search_mode in {"auto", "bands"} if auto_match is None else auto_match
        request = self.analysis_controller.make_request(
            spectrum.id,
            sources,
            query,
            CandidateSearchOptions(
                auto_match=staged_match,
                candidate_gate=lambda candidate: query.allows_formula(candidate.formula),
            ),
            use_sample_bands=not staged_match or self._search_mode == "bands",
        )
        self.analysis_job_controller.start(request)

    def _composition_query(self, text: str, kind: SignalKind) -> SourceQuery:
        return SourceQuery(
            text=str(text).strip(),
            kind=kind,
            required_elements=frozenset(item for item, state in self.element_states.items() if state == "required"),
            excluded_elements=frozenset(item for item, state in self.element_states.items() if state == "excluded"),
        )

    def start_residual_search(self) -> None:
        self.analysis_job_controller.cancel()
        spectrum = self.active_spectrum()
        if spectrum is None:
            self.candidate_workspace.set_unavailable("Select a Raman or FTIR spectrum first")
            return
        sources = self.source_catalog.enabled_sources(spectrum.kind)
        if not sources:
            self.candidate_workspace.set_unavailable("No enabled source is available for next-component search")
            return
        try:
            request = build_residual_request(
                self.analysis_controller,
                spectrum.id,
                sources,
                SourceQuery(text=self.candidate_workspace.query_edit.text().strip(), kind=spectrum.kind),
            )
        except ResidualSearchUnavailable as exc:
            self.candidate_workspace.set_failed(str(exc))
            return
        self.residual_job_controller.start(request)

    def _residual_search_succeeded(self, _outcome: object) -> None:
        spectrum = self.active_spectrum()
        profile = self.project.profile_states.get(spectrum.id) if spectrum is not None else None
        self.candidate_workspace.set_residual_results(profile.residual_results if profile is not None else [])
        failures = getattr(getattr(_outcome, "result", None), "source_failures", {})
        if failures:
            names = ", ".join(sorted(failures))
            self.candidate_workspace.status_label.setText(
                f"Next component — {self.candidate_workspace.table.rowCount()} candidates; unavailable: {names}"
            )

    def _refresh_candidate_workspace(self) -> None:
        spectrum = self.active_spectrum()
        profile = self.project.profile_states.get(spectrum.id) if spectrum is not None else None
        if profile is None:
            self.candidate_workspace.set_results([])
            return
        self.candidate_workspace.set_results(profile.results)

    def _ordinary_search_succeeded(self, outcome: object) -> None:
        self._refresh_candidate_workspace()
        failures = getattr(getattr(outcome, "result", None), "source_failures", {})
        count = self.candidate_workspace.table.rowCount()
        if failures:
            names = ", ".join(sorted(failures))
            self.candidate_workspace.status_label.setText(
                f"{count} candidates; unavailable: {names}"
            )
        elif count == 0:
            self.candidate_workspace.status_label.setText("No candidates found; check the element filters and enabled sources")
        else:
            self.statusBar().showMessage(f"Search complete — {count} candidates", 5000)

    def preview_candidate(self, candidate_key: str) -> None:
        try:
            result = self._reference_preview(candidate_key)
        except Exception as exc:
            self._clear_candidate_preview()
            self.candidate_workspace.status_label.setText(f"Reference preview unavailable: {exc}")
            return
        if result is None:
            return
        spectrum = self.active_spectrum()
        if spectrum is not None and result.candidate.kind not in {SignalKind.UNKNOWN, spectrum.kind}:
            self._clear_candidate_preview()
            self.candidate_workspace.status_label.setText("Select a spectrum of the same method to overlay this reference")
            return
        self._preview_result = result
        self._redraw_active_spectrum(preserve_view=True)
        self.candidate_workspace.status_label.setText(f"Preview: {result.candidate.name or result.candidate.entry_id}")

    def _reference_preview(self, candidate_key: str) -> VibrationalMatchResult | None:
        result = self.candidate_workspace.result_for_key(candidate_key)
        if result is not None:
            return result
        if self._preview_result is not None and self._preview_result.candidate.key == candidate_key:
            return self._preview_result
        record = self.candidate_workspace.record_for_key(candidate_key)
        if record is None:
            return None
        source = self._browse_sources_by_key.get(candidate_key)
        if source is None:
            return None
        reference = source.load_spectrum(record)
        band_set = reference.band_set
        if band_set is None and reference.x and reference.y:
            band_set = extract_reference_band_set(preprocess_spectrum(reference))
        candidate = CompoundCandidate(
            key=record.key, source=record.source, entry_id=record.entry_id, name=record.name,
            formula=record.formula, kind=reference.kind, metadata=dict(record.metadata),
            reference=reference if reference.x and reference.y else None, band_set=band_set,
        )
        bands = list(band_set.bands) if band_set is not None else []
        if candidate.reference is None and not bands:
            raise ValueError("This entry has no spectrum or bands")
        return VibrationalMatchResult(candidate=candidate, score=MatchScore(), reference_bands=bands)

    def _clear_candidate_preview(self) -> None:
        if self._preview_result is not None:
            self._preview_result = None
            self._redraw_active_spectrum(preserve_view=True)

    def accept_candidate(self, candidate_key: str) -> None:
        spectrum = self.active_spectrum()
        if spectrum is None:
            self.candidate_workspace.status_label.setText("Select an observed spectrum to accept a reference")
            return
        result = self.candidate_workspace.result_for_key(candidate_key)
        if result is None:
            try:
                preview = self._reference_preview(candidate_key)
                if preview is not None:
                    if preview.candidate.kind not in {SignalKind.UNKNOWN, spectrum.kind}:
                        raise ValueError("The reference and observed spectrum use different methods")
                    result = score_candidate(spectrum, preview.candidate)
            except Exception as exc:
                self.candidate_workspace.status_label.setText(f"Cannot accept the reference: {exc}")
                return
        if result is not None:
            self._preview_result = None
            added = self.accepted_components_controller.add(spectrum.id, result)
            self._refresh_accepted_components_workspace()
            self.right_tabs.setCurrentWidget(self.composition_panel)
            self._redraw_active_spectrum(preserve_view=True)
            self.statusBar().showMessage("Component accepted" if added else "Component already accepted", 3000)

    def _refresh_accepted_components_workspace(self) -> None:
        spectrum = self.active_spectrum()
        profile = self.project.profile_states.get(spectrum.id) if spectrum is not None else None
        if profile is None:
            self.accepted_components_workspace.set_components([], set(), self.project.candidate_colors)
            return
        self.accepted_components_workspace.set_components(
            profile.selected_results,
            profile.visible_selected_candidate_keys,
            self.project.candidate_colors,
        )

    def _set_component_visible(self, key: str, visible: bool) -> None:
        spectrum = self.active_spectrum()
        if spectrum is not None:
            self.accepted_components_controller.set_visible(spectrum.id, key, visible)
            self._redraw_active_spectrum(preserve_view=True)

    def _remove_component(self, key: str) -> None:
        spectrum = self.active_spectrum()
        if spectrum is not None and self.accepted_components_controller.remove(spectrum.id, key):
            self._refresh_accepted_components_workspace()
            self._redraw_active_spectrum(preserve_view=True)

    def _clear_components(self) -> None:
        spectrum = self.active_spectrum()
        if spectrum is not None and self.accepted_components_controller.clear(spectrum.id):
            self._refresh_accepted_components_workspace()
            self._redraw_active_spectrum(preserve_view=True)

    def _show_source_settings(self) -> None:
        self.source_settings_panel.ensure_populated()
        self.source_settings_dialog.show()
        self.source_settings_dialog.raise_()
        self.source_settings_dialog.activateWindow()

    def _analysis_sources_changed(self) -> None:
        self._cancel_analysis_jobs()

    def _start_source_operation(self, name: str, operation: str, package_key: str | None = None) -> None:
        self._cancel_analysis_jobs()
        self.source_management_job_controller.start(name, operation, package_key)

    def _source_operation_succeeded(self, name: str, operation: str, result: object) -> None:
        if operation == "build_index" and isinstance(result, tuple) and len(result) == 2:
            message = f"{name}: indexed {result[0]}, skipped {result[1]}"
        elif operation == "update":
            message = f"{name}: cache updated"
        elif operation == "clear":
            message = f"{name}: cache cleared"
        else:
            message = f"{name}: line index cleared"
        self.source_settings_panel.set_operation_succeeded(name, operation, message)
        self.statusBar().showMessage(message, 5000)

    def _cancel_analysis_jobs(self) -> None:
        self.analysis_job_controller.cancel()
        self.residual_job_controller.cancel()

    def _analysis_project_replaced(self) -> None:
        self._preview_result = None
        self._browse_sources_by_key.clear()
        self.analysis_job_controller.shutdown()
        self.residual_job_controller.shutdown()
        self.source_management_job_controller.shutdown()
        self.source_catalog = self.source_catalog.for_project(self.project)
        self.source_settings_panel.set_catalog(self.source_catalog)
        self.source_management_job_controller.manager = self.source_settings_panel.manager
        self._restore_composition_filter_from_project()
        self.analysis_controller = AnalysisController(self.document)
        self.accepted_components_controller = AcceptedComponentsController(self.document)
        self.analysis_job_controller.analysis_controller = self.analysis_controller
        self.residual_search_controller = ResidualSearchController(self.analysis_controller)
        self.residual_job_controller.analysis_controller = self.residual_search_controller
        self._refresh_candidate_workspace()
        self._refresh_accepted_components_workspace()
        self._set_search_mode("search")

    def _shutdown_analysis_jobs(self) -> None:
        if hasattr(self, "analysis_job_controller"):
            self.analysis_job_controller.shutdown()
        if hasattr(self, "residual_job_controller"):
            self.residual_job_controller.shutdown()
        if hasattr(self, "source_management_job_controller"):
            self.source_management_job_controller.shutdown()
