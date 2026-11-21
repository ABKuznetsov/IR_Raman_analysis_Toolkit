from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html import escape
from math import isfinite

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Qt

from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.plot_export.metadata import CanvasLayer, canvas_item_tag, tag_canvas_item


PHASE_LEGEND_CHOICES = (
    ("common", "Common to all spectra"),
    ("individual", "Individual per spectrum"),
    ("hidden", "Hidden"),
)
REFERENCE_COLOR = "#1a73e8"


def multi_legend_mode(settings: Mapping[str, object]) -> str:
    mode = settings.get("multi_phase_legend_mode")
    return str(mode) if any(mode == code for code, _ in PHASE_LEGEND_CHOICES) else "individual"


@dataclass(frozen=True, slots=True)
class PhaseLegendEntry:
    key: str
    name: str
    color: str


class _LegendText(pg.TextItem):
    def __init__(self, html, color, *, anchor, on_move=None) -> None:
        super().__init__("", anchor=anchor, fill=pg.mkBrush(255, 255, 255, 230),
                         border=pg.mkPen(color, width=0.8))
        self.textItem.document().setDocumentMargin(3.0)
        self.setHtml(html)
        self.setZValue(100)
        self.natural_width = self.boundingRect().width()
        self._on_move = on_move
        self._drag_offset = None
        self.setAcceptHoverEvents(on_move is not None)

    def hoverEvent(self, event) -> None:
        if self._on_move is not None:
            event.acceptDrags(Qt.MouseButton.LeftButton)

    def mouseDragEvent(self, event) -> None:
        # Same drag coordinates as the XRD legend: the item's parent is in data units.
        if self._on_move is None or event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        parent = self.parentItem()
        p = parent.mapFromScene(event.scenePos()) if parent is not None else event.scenePos()
        if event.isStart() or self._drag_offset is None:
            self._drag_offset = self.pos() - p
        self.setPos(p + self._drag_offset)
        if event.isFinish():
            self._drag_offset = None
            self._on_move(float(self.pos().x()), float(self.pos().y()))
        event.accept()

    def wrap_to(self, width: float) -> None:
        width = max(1.0, width)
        wanted = width if self.natural_width > width else -1.0
        if self.textItem.textWidth() != wanted:
            self.setTextWidth(wanted)


@dataclass(slots=True)
class _SpectrumBox:
    item: _LegendText
    manual: tuple[float, float] | None
    baseline: float


def _phase_html(entries: Sequence[PhaseLegendEntry]) -> str:
    return "&nbsp; ".join(
        f'<span style="color:{escape(entry.color)};">●</span> '
        f'<span style="color:#111111;">{escape(entry.name)}</span>'
        for entry in entries
    )


def _text_box_html(contents: str) -> str:
    return f'<div style="font-size:10pt;">{contents}</div>'


def _saved_position(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        x, y = map(float, value)
    except (TypeError, ValueError, OverflowError):
        return None
    return (x, y) if isfinite(x) and isfinite(y) else None


class _LegendLayer:
    def __init__(self, plot: pg.PlotWidget) -> None:
        self.plot = plot
        self.view = plot.getViewBox()
        self.boxes: dict[str, _SpectrumBox] = {}
        self.traces: list[tuple[np.ndarray, np.ndarray, float]] = []
        self.common: _LegendText | None = None
        self.common_position: tuple[float, float] | None = None
        self.view.sigRangeChanged.connect(self.layout)
        self.view.sigResized.connect(self.layout)

    def set_contents(self, spectra, phases_by_spectrum, settings, *, multi, on_move) -> None:
        for item in [self.common, *(box.item for box in self.boxes.values())]:
            if item is not None and item in self.plot.plotItem.items:
                self.plot.removeItem(item)
        self.boxes.clear()
        self.traces.clear()
        self.common = None
        self.common_position = _saved_position(settings.get("multi_common_legend_position"))

        names_visible = bool(settings.get("legend_visible", True))
        mode = multi_legend_mode(settings) if multi else "individual"
        if not multi and not names_visible:
            return
        positions = settings.get("multi_legend_positions")
        positions = positions if isinstance(positions, Mapping) else {}
        traces = {}
        for item in self.plot.listDataItems():
            tag = canvas_item_tag(item)
            if tag is not None and tag.layer == CanvasLayer.OBSERVED:
                traces[tag.owner_id] = item
        common: dict[str, PhaseLegendEntry] = {}
        for spectrum in spectra:
            trace = traces.get(spectrum.id)
            if trace is None or not trace.isVisible():
                continue
            x, y = (np.asarray(values, dtype=float) for values in trace.getData())
            finite = np.isfinite(x) & np.isfinite(y)
            x, y = x[finite], y[finite]
            baseline = float(y.min()) if y.size else 0.0
            if y.size:
                order = np.argsort(x, kind="stable")
                self.traces.append((x[order], y[order], baseline))
            entries = phases_by_spectrum.get(spectrum.id, ())
            if mode == "common":
                for entry in entries:
                    common.setdefault(entry.key, entry)
            color = pg.mkPen(trace.opts["pen"]).color().name()
            name = f'<span style="color:{color}; font-weight:600;">{escape(spectrum.name)}</span>'
            rows = [name] if names_visible else []
            if mode == "individual" and entries:
                rows.append(_phase_html(entries))
            if not rows:
                continue
            item = _LegendText(
                _text_box_html("<br>".join(rows)), color, anchor=(1, .5),
                on_move=(lambda x, y, owner=spectrum.id: self._move(owner, x, y, on_move)) if multi else None,
            )
            self.boxes[spectrum.id] = _SpectrumBox(
                item, _saved_position(positions.get(spectrum.id)) if multi else None, baseline,
            )
            tag_canvas_item(item, layer=CanvasLayer.LEGEND, owner_id=spectrum.id,
                            object_id=f"spectrum-legend-{spectrum.id}")
            self.plot.addItem(item, ignoreBounds=True)
        if common:
            self.common = _LegendText(_text_box_html(_phase_html(tuple(common.values()))),
                                      "#c5c5c5", anchor=(0, 0),
                                      on_move=lambda x, y: self._move(None, x, y, on_move))
            tag_canvas_item(self.common, layer=CanvasLayer.LEGEND, object_id="common-phase-legend")
            self.plot.addItem(self.common, ignoreBounds=True)
        self.layout()

    def _move(self, owner: str | None, x: float, y: float, callback) -> None:
        position = _saved_position((x, y))
        if position is not None:
            if owner is None:
                self.common_position = position
            else:
                self.boxes[owner].manual = position
            self.layout()
            if callback is not None:
                callback(owner, *position)

    def layout(self, *_args) -> None:
        bounds = self.view.sceneBoundingRect().adjusted(5, 5, -5, -5)
        if bounds.isEmpty():
            return
        occupied: list[QRectF] = []
        if self.common is not None and self.common in self.plot.plotItem.items:
            self._place(self.common, bounds, occupied, manual=self.common_position)
        # Place manual boxes first, then find space for the ones that follow the curves.
        for box in sorted(self.boxes.values(), key=lambda entry: entry.manual is None):
            if box.item in self.plot.plotItem.items:
                self._place(box.item, bounds, occupied, manual=box.manual, baseline=box.baseline)

    def _place(self, item, bounds: QRectF, occupied: list[QRectF], *, manual, baseline=None) -> None:
        item.wrap_to(bounds.width())
        width, height = item.boundingRect().size().toTuple()
        max_x, max_y = bounds.right() - width, bounds.bottom() - height
        if max_x < bounds.left() or max_y < bounds.top():
            item.setVisible(False)
            return
        common = baseline is None
        if manual is not None:
            point = self.view.mapViewToScene(QPointF(*manual))
            x = point.x() - (0 if common else width)
            y = point.y() - (0 if common else height / 2)
            position = (float(np.clip(x, bounds.left(), max_x)), float(np.clip(y, bounds.top(), max_y)))
        else:
            position = self._find_space(bounds, width, height, occupied, baseline)
        item.setVisible(position is not None)
        if position is None:
            return
        x, y = position
        occupied.append(QRectF(x, y, width, height))
        anchor = QPointF(x, y) if common else QPointF(x + width, y + height / 2)
        item.setPos(self.view.mapSceneToView(anchor))

    def _find_space(self, bounds: QRectF, width: float, height: float, occupied, baseline):
        """Prefer the gap for this spectrum, falling back only to trace-free space."""
        top, bottom = bounds.top(), bounds.bottom()
        left, right = bounds.left(), bounds.right() - width
        common = baseline is None
        preferred_top, preferred_bottom = top, bottom
        if not common:
            above = min((level for _, _, level in self.traces if level > baseline), default=None)
            if above is not None:
                preferred_top = max(top, self.view.mapViewToScene(QPointF(0, above)).y())
            preferred_bottom = min(bottom, self.view.mapViewToScene(QPointF(0, baseline)).y())
        target = top if common else preferred_bottom - height
        fallback = None
        for x in np.linspace(left, right, 16) if common else np.linspace(right, left, 16):
            blocked = self._trace_intervals(x, x + width)
            blocked.extend((r.top(), r.bottom()) for r in occupied if r.left() < x + width and r.right() > x)
            for start, stop in _free_spans(top, bottom, blocked):
                low, high = max(start, preferred_top), min(stop, preferred_bottom)
                if high - low >= height:
                    return (x, low if common else high - height)
                if stop - start >= height:
                    y = float(np.clip(target, start, stop - height))
                    distance = abs(y - target)
                    if fallback is None or distance < fallback[0]:
                        fallback = (distance, x, y)
        return fallback[1:] if fallback is not None else None

    def _trace_intervals(self, left: float, right: float) -> list[tuple[float, float]]:
        low, high = sorted(self.view.mapSceneToView(QPointF(x, 0)).x() for x in (left, right))
        blocked = []
        for grid, trace, _ in self.traces:
            if high < grid[0] or low > grid[-1]:
                continue
            start = int(np.searchsorted(grid, low))
            stop = int(np.searchsorted(grid, high, side="right"))
            finite = trace[max(0, start - 1):stop + 1]
            a, b = (self.view.mapViewToScene(QPointF(0, float(y))).y() for y in (finite.min(), finite.max()))
            blocked.append((min(a, b), max(a, b)))
        return blocked


def _free_spans(top: float, bottom: float, blocked: list[tuple[float, float]]):
    cursor = top
    for start, stop in sorted(blocked):
        if start - 5 > cursor:
            yield cursor, min(bottom, start - 5)
        cursor = max(cursor, stop + 5)
        if cursor >= bottom:
            return
    yield cursor, bottom


def show_spectrum_legends(
    plot: pg.PlotWidget,
    spectra: Sequence[ObservedSpectrum],
    phases_by_spectrum: Mapping[str, Sequence[PhaseLegendEntry]],
    *,
    settings: Mapping[str, object],
    multi: bool = False,
    on_move: Callable[[str | None, float, float], None] | None = None,
) -> None:
    layer = getattr(plot, "_spectrum_legend_layer", None)
    if layer is None:
        layer = plot._spectrum_legend_layer = _LegendLayer(plot)
    layer.set_contents(spectra, phases_by_spectrum, settings, multi=multi, on_move=on_move)
