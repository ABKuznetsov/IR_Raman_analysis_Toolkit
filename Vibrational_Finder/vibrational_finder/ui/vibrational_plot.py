from __future__ import annotations

from html import escape
from collections.abc import Mapping, Sequence
from dataclasses import replace

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLayout, QMenu, QVBoxLayout, QWidget

from vibrational_finder.plot_export.metadata import CanvasLayer, canvas_item_tag, tag_canvas_item
from vibrational_finder.models import ObservedSpectrum, VibrationalMatchResult
from vibrational_finder.models import SpectralBand
from vibrational_finder.layers.bands import matched_reference_band_positions, reference_peak_label
from vibrational_finder.matching import MatchingOptions
from vibrational_finder.services.phase_deconvolution import PhaseDeconvolutionFit


class VibrationalViewBox(pg.ViewBox):
    def __init__(self) -> None:
        super().__init__(enableMenu=False)
        self.setMouseMode(pg.ViewBox.RectMode)
        self.setMouseEnabled(x=True, y=True)
        self.full_range_callback = None

    def wheelEvent(self, event, axis=None) -> None:
        delta = event.delta() if hasattr(event, "delta") else event.angleDelta().y()
        factor = 0.9 if delta > 0 else 1.1
        center = self.mapSceneToView(event.scenePos())
        self.scaleBy(x=factor, y=1.0, center=center)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        if self.full_range_callback is not None:
            self.full_range_callback()
        else:
            self.autoRange(padding=0.04)
        event.accept()


def register_structural_plot_items(plot: pg.PlotWidget) -> None:
    plot_item = plot.plotItem
    view_box = plot_item.vb
    tag_canvas_item(
        plot_item,
        layer=CanvasLayer.BACKGROUND,
        object_id="plot-container",
        exportable=False,
    )
    tag_canvas_item(
        view_box,
        layer=CanvasLayer.BACKGROUND,
        object_id="view-box",
        exportable=False,
    )
    tag_canvas_item(
        view_box.childGroup,
        layer=CanvasLayer.BACKGROUND,
        object_id="view-box-children",
        exportable=False,
    )
    for axis_name in ("bottom", "left", "top", "right"):
        axis = plot.getAxis(axis_name)
        tag_canvas_item(
            axis,
            layer=CanvasLayer.AXES,
            object_id=f"axis-{axis_name}",
        )
        tag_canvas_item(
            axis.label,
            layer=CanvasLayer.AXES,
            object_id=f"axis-{axis_name}-label",
        )
    tag_canvas_item(
        plot_item.titleLabel,
        layer=CanvasLayer.AXES,
        object_id="plot-title",
    )

def create_vibrational_plot_widget() -> pg.PlotWidget:
    plot = pg.PlotWidget(viewBox=VibrationalViewBox())
    plot.setBackground("w")
    plot.showGrid(x=False, y=False)
    plot.setMenuEnabled(False)
    plot.setTitle("IR/Raman Phase Finder: spectrum and candidate markers", color="#111111", size="13pt")
    for axis_name in ("bottom", "left"):
        axis = plot.getAxis(axis_name)
        axis.setPen(pg.mkPen("#111111", width=1.2))
        axis.setTextPen(pg.mkPen("#111111"))
        axis_font = QFont()
        axis_font.setPointSize(10)
        axis.setTickFont(axis_font)
        axis.setStyle(tickTextOffset=8)
    plot.setLabel("bottom", "Wavenumber", units="cm-1", color="#111111", **{"font-size": "12pt"})
    plot.setLabel("left", "Intensity", units="a.u.", color="#111111", **{"font-size": "12pt"})
    plot.getAxis("bottom").enableAutoSIPrefix(False)
    plot.getAxis("left").enableAutoSIPrefix(False)
    register_structural_plot_items(plot)
    return plot


class SpectrumPlotCanvas(QWidget):
    """Fit the active plot to the available canvas, never to a data-unit ratio."""

    def __init__(self, plot: QWidget) -> None:
        super().__init__()
        self.plot = plot
        self._shown_plot = plot
        self._aspect: float | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.addWidget(plot, 1)

    def show_preview(self, preview: QWidget) -> None:
        self.layout().insertWidget(0, preview, 1)
        self.plot.hide()
        self._shown_plot = preview
        preview.show()
        self._fit_widget()

    def close_preview(self, preview: QWidget) -> None:
        self.layout().removeWidget(preview)
        preview.hide()
        preview.deleteLater()
        self._shown_plot = self.plot
        self.plot.show()
        self._fit_widget()

    def set_aspect(self, aspect: float | None) -> None:
        self._aspect = aspect
        self._fit_widget()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_widget()

    def _fit_widget(self) -> None:
        widget = self._shown_plot
        if self._aspect is None:
            widget.setMinimumSize(0, 0)
            widget.setMaximumSize(16777215, 16777215)
            self.layout().setAlignment(widget, Qt.AlignmentFlag(0))
            return
        width, height = max(1, self.width()), max(1, self.height())
        target_width = min(width, max(1, round(height * self._aspect)))
        target_height = min(height, max(1, round(target_width / self._aspect)))
        self.layout().setAlignment(widget, Qt.AlignmentFlag.AlignCenter)
        widget.setFixedSize(target_width, target_height)


def _add_layer_menu_action(menu: QMenu, title: str, visible: bool, set_visible) -> None:
    action = menu.addAction(title)
    action.setCheckable(True)
    action.setChecked(visible)
    action.toggled.connect(set_visible)


class PhaseDeconvolutionPlot(QWidget):
    """Temporary two-track preview; the publication canvas remains untouched."""

    differenceVisibilityRequested = Signal(bool)

    def __init__(self, observed: ObservedSpectrum, fit: PhaseDeconvolutionFit, additional_name: str) -> None:
        super().__init__()
        self._fit = fit
        self.main_plot = create_vibrational_plot_widget()
        self.difference_plot = create_vibrational_plot_widget()
        title = f"{escape(observed.name)} · Phase deconvolution" if observed.name else "Phase deconvolution"
        self.main_plot.setTitle(title, color="#111111")
        self.difference_plot.setTitle(None)
        for plot in (self.main_plot, self.difference_plot):
            plot.getAxis("left").setWidth(74)
            plot.getAxis("left").setStyle(autoExpandTextSpace=False)
            plot.showGrid(x=True, y=False, alpha=0.16)
            plot.setLabel("bottom", "Raman shift" if observed.kind.value == "raman" else "Wavenumber",
                          units=observed.x_unit, color="#111111")
        self.main_plot.setLabel("left", "Intensity", units=observed.y_unit, color="#111111")
        self.difference_plot.setLabel("left", "Difference", color="#007f7b")
        self.difference_plot.setMinimumHeight(88)
        self.difference_plot.setMaximumHeight(145)
        self.difference_plot.setXLink(self.main_plot)
        self.difference_plot.setMouseEnabled(x=False, y=False)

        self.legend = self.main_plot.addLegend(
            offset=(-10, 10), labelTextColor="#24212a", brush=pg.mkBrush(255, 255, 255, 225),
        )
        self.measured_curve = self.main_plot.plot(
            observed.x, observed.y, pen=pg.mkPen("#25222b", width=1.6, style=Qt.PenStyle.DashLine),
        )
        self.additional_curve = self.main_plot.plot(
            fit.x, fit.additional, pen=pg.mkPen("#a52555", width=2),
        )
        self.additional_curve.setToolTip(additional_name)
        self.total_curve = self.main_plot.plot(fit.x, fit.measured - fit.difference(), pen=pg.mkPen("#3068b2", width=1.7))
        self.main_phase_curve = self.main_plot.plot(fit.x, fit.main, pen=pg.mkPen("#ad652a", width=1.7))
        self.background_curve = self.main_plot.plot(
            fit.x, np.full_like(fit.x, fit.offset), pen=pg.mkPen("#74707a", style=Qt.PenStyle.DotLine),
        )
        self._main_layers = (
            ("Measured spectrum", self.measured_curve), ("Calculated total", self.total_curve),
            ("Main phase", self.main_phase_curve), ("Additional phase", self.additional_curve),
            ("Background", self.background_curve),
        )
        for curve in (self.total_curve, self.main_phase_curve, self.background_curve):
            curve.hide()
        self._sync_legend()
        self.difference_plot.addLine(y=0, pen=pg.mkPen("#809693", style=Qt.PenStyle.DotLine))
        self.difference_curve = self.difference_plot.plot(fit.x, fit.difference(), pen=pg.mkPen("#007f7b", width=1.7))
        self.layer_menu = QMenu(self)
        for plot in (self.main_plot, self.difference_plot):
            plot.scene().sigMouseClicked.connect(self._plot_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.main_plot, 4)
        layout.addWidget(self.difference_plot, 1)
        self.set_difference_visible(True)
        self.fit_to_data()

    def update_contribution(self, multiplier: float) -> None:
        self.additional_curve.setData(self._fit.x, self._fit.additional * multiplier)
        difference = self._fit.difference(multiplier)
        self.total_curve.setData(self._fit.x, self._fit.measured - difference)
        self.difference_curve.setData(self._fit.x, difference)

    def set_difference_visible(self, visible: bool) -> None:
        self.difference_plot.setVisible(visible)
        self.main_plot.showAxis("bottom", show=not visible)

    def _plot_clicked(self, event) -> None:
        if event.button() != Qt.MouseButton.RightButton:
            return
        event.accept()
        self.layer_menu.clear()
        self.layer_menu.addAction("Show full spectrum", self.fit_to_data)
        _add_layer_menu_action(self.layer_menu, "Legend", self.legend.isVisible(), self.legend.setVisible)
        self.layer_menu.addSeparator()
        for label, curve in self._main_layers:
            _add_layer_menu_action(self.layer_menu, label, curve.isVisible(),
                                   lambda visible, item=curve: self._set_curve_visible(item, visible))
        _add_layer_menu_action(self.layer_menu, "Difference curve", not self.difference_plot.isHidden(),
                               self._set_difference_from_menu)
        self.layer_menu.popup(event.screenPos().toPoint())

    def _set_difference_from_menu(self, visible: bool) -> None:
        self.set_difference_visible(visible)
        self.differenceVisibilityRequested.emit(visible)

    def _set_curve_visible(self, curve: pg.PlotDataItem, visible: bool) -> None:
        curve.setVisible(visible)
        self._sync_legend()

    def _sync_legend(self) -> None:
        self.legend.clear()
        for label, curve in self._main_layers:
            if curve.isVisible():
                self.legend.addItem(curve, label)

    def fit_to_data(self) -> None:
        self.main_plot.getViewBox().autoRange(padding=0.05)
        # Fixed scale over the slider range avoids magnifying noise as the fit improves.
        extent = max(float(np.max(np.abs(self._fit.difference(value)))) for value in (0.0, 2.0))
        extent = max(extent, float(np.ptp(self._fit.measured)) * 0.04, 1e-12)
        self.difference_plot.setYRange(-extent, extent, padding=0.12)


_BAND_ANNOTATION_LAYERS = {CanvasLayer.MODE_LABELS, CanvasLayer.ASSIGNMENT_LABELS}


def _add_band_annotations(
    plot, band, x, y, color, owner_id, object_id, *,
    mode=False, assignment=False, position=False, below=False, exportable=True,
) -> None:
    labels = (
        (CanvasLayer.PEAK_LABELS, f"{band.position:.1f}" if position else ""),
        (CanvasLayer.MODE_LABELS, reference_peak_label(band) if mode else ""),
        (CanvasLayer.ASSIGNMENT_LABELS,
         reference_peak_label(band, show_mode=False, show_assignment=True) if assignment else ""),
    )
    for row, (layer, text) in enumerate((layer, text) for layer, text in labels if text):
        anchor_y = -0.2 - row if below else 1.2 + row
        label = pg.TextItem(text, color=color, anchor=(0.5, anchor_y))
        label.textItem.document().setDocumentMargin(1)
        label._band_annotation_anchor = anchor_y
        label.setPos(float(x), float(y))
        tag_canvas_item(label, layer=layer, owner_id=owner_id, object_id=f"{object_id}-{layer.value}",
                        exportable=exportable)
        plot.addItem(label, ignoreBounds=True)


def layout_band_annotations(plot) -> None:
    """Pack labels in screen space while their scientific x/y anchors stay fixed."""
    view = plot.getViewBox()
    bounds = view.sceneBoundingRect().adjusted(2, 2, -2, -2)
    if bounds.isEmpty():
        return
    occupied = []
    labels = []
    priorities = {CanvasLayer.PEAK_LABELS: 0, CanvasLayer.MODE_LABELS: 1, CanvasLayer.ASSIGNMENT_LABELS: 2}
    for item in plot.plotItem.items:
        tag = canvas_item_tag(item)
        if tag is None:
            continue
        if tag.layer == CanvasLayer.LEGEND and item.isVisible():
            item.updateTransform()
            occupied.append(item.sceneBoundingRect())
        elif hasattr(item, "_band_annotation_anchor"):
            labels.append((priorities[tag.layer], not tag.exportable, item))
    for _, _, item in sorted(labels, key=lambda entry: (*entry[:2], entry[2].pos().x())):
        point = view.mapViewToScene(item.pos())
        anchor = item._band_annotation_anchor
        width, height = item.textItem.boundingRect().size().toTuple()
        placed = False
        if bounds.left() <= point.x() <= bounds.right() and bounds.top() <= point.y() <= bounds.bottom():
            for row in range(4):
                candidate = anchor + row * (1 if anchor > 0 else -1)
                box = QRectF(point.x() - width / 2, point.y() - candidate * height, width, height)
                if bounds.contains(box) and not any(previous.intersects(box) for previous in occupied):
                    item.setAnchor((.5, candidate))
                    occupied.append(box.adjusted(-2, -1, 2, 1))
                    placed = True
                    break
        if item.isVisible() != placed:
            item.setVisible(placed)


def _measured_band_points(spectrum, bands, offset=0.0):
    x, y = np.asarray(spectrum.x, dtype=float), np.asarray(spectrum.y, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not np.any(finite):
        return
    x, y = x[finite], y[finite]
    top = float(y.max())
    span = float(np.ptp(y))
    for i, band in enumerate(bands):
        if not np.isfinite(band.position) or not x.min() <= band.position <= x.max():
            continue
        level = float(y[np.argmin(abs(x - band.position))])
        yield i, band, level + offset, span > 0 and level > top - span * .12


def show_observed_spectrum(
    plot: pg.PlotWidget,
    spectrum: ObservedSpectrum | None,
    *,
    preview: bool = False,
    background_y: list[float] | None = None,
    bands: list[SpectralBand] | None = None,
    selected_band_index: int | None = None,
    show_band_labels: bool = True,
    show_mode_labels: bool = False,
    show_assignment_labels: bool = False,
    on_band_selected=None,
    preserve_view: bool = False,
    preserve_x_range: bool = False,
    overlays: tuple[tuple[ObservedSpectrum, float], ...] = (),
    overlay_bands: Mapping[str, Sequence[SpectralBand]] | None = None,
    all_observed_black: bool = False,
) -> None:
    """Replace the plotted trace without changing the source spectrum."""
    old_range = plot.viewRange() if preserve_view or preserve_x_range else None
    plot.clear()
    if spectrum is None:
        plot._vibrational_spectrum_id = None
        return
    plot._vibrational_spectrum_id = spectrum.id
    color = "#d81b60" if spectrum.kind.value == "raman" else "#008ca8"
    trace_color = "#000000" if all_observed_black else color
    trace = plot.plot(spectrum.x, spectrum.y, pen=pg.mkPen(trace_color, width=1.6), name=spectrum.name)
    tag_canvas_item(
        trace,
        layer=CanvasLayer.PROCESSED if preview else CanvasLayer.OBSERVED,
        owner_id=spectrum.id,
        object_id=f"{'preview' if preview else 'observed'}-{spectrum.id}",
        exportable=not preview,
    )
    overlay_colors = ("#176e99", "#986323", "#7451a1", "#197664", "#ad4736")
    for index, (other, offset) in enumerate(overlays):
        overlay_color = overlay_colors[index % len(overlay_colors)]
        trace_color = "#000000" if all_observed_black else overlay_color
        item = plot.plot(other.x, (np.asarray(other.y) + offset).tolist(), name=other.name,
                         pen=pg.mkPen(trace_color, width=1.6))
        tag_canvas_item(item, layer=CanvasLayer.OBSERVED, owner_id=other.id, object_id=f"observed-{other.id}")
        if overlay_bands and (show_mode_labels or show_assignment_labels):
            for row, band, height, below in _measured_band_points(other, overlay_bands.get(other.id, ()), offset):
                _add_band_annotations(plot, band, band.position, height, overlay_color, other.id,
                                      f"observed-band-label-{other.id}-{row}", mode=show_mode_labels,
                                      assignment=show_assignment_labels, below=below)
    if background_y is not None and len(background_y) == len(spectrum.x):
        background = plot.plot(
            spectrum.x,
            background_y,
            pen=pg.mkPen("#7e8792", width=1.2, style=Qt.PenStyle.DashLine),
            name="Background preview",
        )
        tag_canvas_item(
            background,
            layer=CanvasLayer.BACKGROUND,
            object_id=f"background-preview-{spectrum.id}",
            exportable=False,
        )
    for index, band, marker_y, below in _measured_band_points(spectrum, bands or ()):
        marker = pg.ScatterPlotItem(
            [band.position],
            [marker_y],
            symbol="o",
            size=11 if index == selected_band_index else 8,
            pen=pg.mkPen("#b71c1c", width=1.2),
            brush=pg.mkBrush("#ef5350"),
            hoverable=True,
            useCache=False,
        )
        callback = (lambda band_index=index: on_band_selected(band_index)) if callable(on_band_selected) else lambda: None
        marker._vibrational_band_index = index
        marker._vibrational_select_callback = callback
        marker.sigClicked.connect(lambda *_args, select=callback: select())
        tag_canvas_item(
            marker,
            layer=CanvasLayer.OBSERVED_BANDS,
            owner_id=spectrum.id,
            object_id=f"observed-band-{spectrum.id}-{index}",
        )
        plot.addItem(marker)
        _add_band_annotations(
            plot, band, band.position, marker_y, "#b71c1c", spectrum.id,
            f"observed-band-label-{spectrum.id}-{index}", mode=show_mode_labels,
            assignment=show_assignment_labels, position=show_band_labels or index == selected_band_index,
            below=below, exportable=not preview,
        )
    plot.setTitle(spectrum.name, color="#111111", size="13pt")
    plot.setLabel("bottom", "Raman shift" if spectrum.kind.value == "raman" else "Wavenumber", units="cm-1")
    plot.setLabel("left", "Intensity", units="a.u.")
    if preserve_view and old_range is not None:
        plot.setRange(xRange=old_range[0], yRange=old_range[1], padding=0)
    else:
        plot.autoRange(padding=0.04)
        if old_range is not None and spectrum.x:
            left, right = old_range[0]
            if max(left, min(spectrum.x)) < min(right, max(spectrum.x)):
                plot.setXRange(left, right, padding=0)


def show_reference_layers(
    plot: pg.PlotWidget,
    results: list[VibrationalMatchResult],
    visible_keys: set[str],
    colors: dict[str, str],
    *,
    residual_bands: list[SpectralBand] | None = None,
    observed: ObservedSpectrum | None = None,
    preview_key: str | None = None,
    preserve_view: bool = True,
    show_profiles: bool = True,
    show_bands: bool = True,
    show_peak_markers: bool = False,
    show_reference_ticks: bool = False,
    show_mode_labels: bool = False,
    show_assignment_labels: bool = False,
    display_offset: float = 0.0,
    clear_existing: bool = True,
    fit_markers: bool = False,
    observed_bands: Sequence[SpectralBand] = (),
) -> None:
    old_range = plot.viewRange() if preserve_view else None
    removable_layers = {
        CanvasLayer.REFERENCE_PROFILE, CanvasLayer.REFERENCE_BANDS, CanvasLayer.REFERENCE_TICKS,
        CanvasLayer.ASSIGNED_BANDS, CanvasLayer.UNASSIGNED_BANDS,
    }
    if clear_existing:
        for item in list(plot.plotItem.items):
            tag = getattr(item, "_vibrational_export_tag", None)
            if tag is not None and (
                tag.layer in removable_layers
                or (tag.layer in _BAND_ANNOTATION_LAYERS and (tag.object_id or "").startswith("reference-band-label-"))
            ):
                plot.removeItem(item)
    measured = _finite_sorted_trace(observed)
    lane_index = 0
    for result in results:
        key = result.candidate.key
        if key not in visible_keys:
            continue
        color = colors.get(key, "#1a73e8")
        is_preview = key == preview_key
        visual_key = f"{observed.id}-{key}" if observed is not None else key
        reference = result.aligned_reference or result.candidate.reference
        if show_profiles and reference is not None and reference.x and reference.y:
            y = np.asarray(_reference_display_y(reference.y, observed, profile=True)) + display_offset
            curve = pg.PlotCurveItem(
                reference.x, y,
                pen=pg.mkPen(color, width=1.4, style=Qt.PenStyle.DashLine if is_preview else Qt.PenStyle.SolidLine),
            )
            tag_canvas_item(
                curve,
                layer=CanvasLayer.REFERENCE_PROFILE,
                owner_id=key,
                object_id=f"reference-profile-{visual_key}",
                exportable=not is_preview,
            )
            plot.addItem(curve, ignoreBounds=preserve_view)
        bands = result.reference_bands or (
            list(result.candidate.band_set.bands) if result.candidate.band_set is not None else []
        )
        if bands and (show_bands or show_peak_markers or show_reference_ticks
                      or show_mode_labels or show_assignment_labels):
            reference_positions = np.asarray([band.position for band in bands], dtype=float)
            nominal_preview = measured is None or (
                is_preview and result.matched_peak_pairs is None and not result.observed_bands and not observed_bands
            )
            positions = reference_positions + result.score.x_shift if nominal_preview else _matched_peak_x(
                result, bands, observed_bands,
            )
            valid = np.isfinite(positions)
            if measured is not None:
                grid, trace = measured
                valid &= (positions >= grid[0]) & (positions <= grid[-1])
                span = float(np.ptp(trace)) or float(np.max(np.abs(trace))) or 1.0
                spectrum_base = float(trace.min()) + display_offset
                first_lane_top = spectrum_base - span * .045
                drawn_x = positions[valid]
                peak_y = np.interp(drawn_x, grid, trace)
                heights = peak_y + display_offset
                if show_bands:
                    # Start just above the nearest comparison row, even when
                    # that row is hidden. Browse previews have no comparison row.
                    start = spectrum_base if is_preview else first_lane_top + span * .010
                    bases = np.full_like(heights, start)
                if show_mode_labels or show_assignment_labels:
                    label_y = _nearby_trace_tops(grid, trace, drawn_x) + display_offset + span * .055
                if show_reference_ticks and not is_preview:
                    top = first_lane_top - span * lane_index * .059
                    height = span * .037
                    bottom, middle = top - height, top - height / 2
                    lane_x, lane_y = [], []
                    for index, nominal in enumerate(reference_positions):
                        if np.isfinite(nominal) and (grid[0] <= nominal <= grid[-1] or valid[index]):
                            lane_x.extend((nominal, nominal))
                            lane_y.extend((bottom, middle))
                            if valid[index]:
                                lane_x.extend((positions[index], positions[index]))
                                lane_y.extend((middle, top))
                    if lane_x:
                        _add_reference_lines(
                            plot, np.asarray(lane_x), np.asarray(lane_y), color, key,
                            f"reference-ticks-{visual_key}", layer=CanvasLayer.REFERENCE_TICKS,
                            ignore_bounds=not fit_markers,
                        )
                        lane_index += 1
            else:
                intensities = np.asarray([band.intensity for band in bands], dtype=float)
                valid &= np.isfinite(intensities)
                strengths = np.clip(intensities[valid], 0.0, None)
                maximum = float(np.max(strengths, initial=0))
                heights = np.maximum(strengths / maximum, .025) if maximum > 0 else np.ones_like(strengths)
                heights += display_offset
                bases = np.full_like(heights, display_offset)
                label_y = heights if show_bands else bases
            if not np.any(valid):
                continue
            positions = positions[valid]
            if show_bands:
                _add_reference_lines(
                    plot, np.repeat(positions, 2), np.column_stack((bases, heights)).ravel(), color, key,
                    f"reference-bands-{visual_key}", exportable=not is_preview, ignore_bounds=not fit_markers,
                )
            if show_peak_markers and not nominal_preview:
                dots = pg.ScatterPlotItem(
                    positions, heights, symbol="o", size=8, brush=pg.mkBrush(color),
                    pen=pg.mkPen("#ffffff", width=1), useCache=False,
                )
                dots.setZValue(3)
                tag_canvas_item(
                    dots, layer=CanvasLayer.ASSIGNED_BANDS, owner_id=key,
                    object_id=f"reference-markers-{visual_key}", exportable=not is_preview,
                )
                plot.addItem(dots, ignoreBounds=True)
            if (show_mode_labels or show_assignment_labels) and (not nominal_preview or measured is None):
                for index, x, y in zip(np.flatnonzero(valid), positions, label_y, strict=True):
                    _add_band_annotations(
                        plot, bands[index], x, y, color, key, f"reference-band-label-{visual_key}-{index}",
                        mode=show_mode_labels, assignment=show_assignment_labels,
                        exportable=not is_preview,
                    )
    residual = list(residual_bands or [])
    if residual:
        owner = str(getattr(plot, "_vibrational_spectrum_id", None) or "residual")
        marker = pg.ScatterPlotItem(
            [float(band.position) for band in residual],
            [float(band.intensity) for band in residual],
            symbol="x",
            size=10,
            pen=pg.mkPen("#f57c00", width=1.5),
            useCache=False,
        )
        tag_canvas_item(
            marker,
            layer=CanvasLayer.UNASSIGNED_BANDS,
            owner_id=owner,
            object_id=f"residual-bands-{owner}",
        )
        plot.addItem(marker, ignoreBounds=True)
    if old_range is not None:
        plot.setRange(xRange=old_range[0], yRange=old_range[1], padding=0)
    elif visible_keys:
        plot.autoRange(padding=0.04)


def _add_reference_lines(plot, x, y, color, owner, object_id, *, layer=CanvasLayer.REFERENCE_BANDS,
                         exportable=True, ignore_bounds=False) -> None:
    item = pg.PlotCurveItem(x, y, connect="pairs", pen=pg.mkPen(color, width=1.3))
    tag_canvas_item(item, layer=layer, owner_id=owner, object_id=object_id, exportable=exportable)
    plot.addItem(item, ignoreBounds=ignore_bounds)


def _matched_peak_x(result, bands, sample_bands) -> np.ndarray:
    positions = np.full(len(bands), np.nan)
    if result.matched_peak_pairs is not None:
        for index, observed_x in result.matched_peak_pairs:
            if 0 <= index < len(bands):
                positions[index] = observed_x
        return positions
    # Older projects did not save pairs; use their detected bands and the legacy
    # one-to-one association, never a nominal position as a measured peak.
    if not result.observed_bands and sample_bands:
        result = replace(result, observed_bands=list(sample_bands))
    matched = matched_reference_band_positions(result, bands, result.score.x_shift, MatchingOptions().tolerance_cm1)
    return np.asarray([matched.get(id(band), np.nan) for band in bands], dtype=float)


def _finite_sorted_trace(observed):
    if observed is None:
        return None
    x, y = np.asarray(observed.x, dtype=float), np.asarray(observed.y, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    if not np.any(finite):
        return None
    x, y = x[finite], y[finite]
    order = np.argsort(x, kind="stable")
    return x[order], y[order]


def _nearby_trace_tops(x, y, positions):
    # A nearby maximum gives the mark clearance from a slightly displaced
    # peak without moving the reference wavenumber or asserting a match.
    tops = np.interp(positions, x, y)
    for index, (left, right) in enumerate(zip(np.searchsorted(x, positions - 4.0),
                                             np.searchsorted(x, positions + 4.0, side="right"), strict=True)):
        if right > left:
            tops[index] = max(tops[index], y[left:right].max())
    return tops


def _reference_display_y(values: list[float], observed: ObservedSpectrum | None, *, profile: bool = False):
    if observed is None or not observed.y:
        return values
    y = np.asarray(values, dtype=float)
    measured = np.asarray(observed.y, dtype=float)
    measured = measured[np.isfinite(measured)]
    finite = y[np.isfinite(y)]
    if not len(measured) or not len(finite):
        return values
    bottom = np.min(measured)
    span = float(np.ptp(measured)) or 1.0
    if profile:
        relative = (y - np.min(finite)) / (float(np.ptp(finite)) or 1.0)
    else:
        relative = np.clip(y / max(1.0, float(np.max(finite))), 0.0, 1.0)
    return bottom + span * relative
