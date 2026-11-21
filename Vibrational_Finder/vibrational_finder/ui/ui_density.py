"""Scale native interface chrome without changing spectroscopy plot geometry."""
from __future__ import annotations

import re

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QLayout, QToolButton, QWidget


_PIXEL = re.compile(r"(?<![\w.])([0-9]+(?:\.[0-9]+)?)px")


def scaled_style(style: str, factor: float) -> str:
    return _PIXEL.sub(
        lambda match: f"{max(1, round(float(match.group(1)) * factor)) if float(match.group(1)) else 0}px",
        style,
    )


def independent_ui_scale(widget: QWidget | None) -> bool:
    while widget is not None:
        if widget.property("independentUiScale"):
            return True
        widget = widget.parentWidget()
    return False


class UiDensity:
    def __init__(self) -> None:
        self._styles: dict[QWidget, tuple[str, str]] = {}
        self._metrics: dict[QWidget, tuple[QSize, QSize]] = {}
        self._layouts: dict[QLayout, tuple[tuple[int, int, int, int], int]] = {}
        self._tables: dict[QAbstractItemView, int] = {}

    def apply(self, root: QWidget, factor: float) -> None:
        plot = getattr(root, "spectrum_plot", None)
        excluded = {
            getattr(root, name, None)
            for name in ("spectrum_plot", "plot_host", "center", "center_splitter", "candidate_panel", "main_splitter")
        }
        for widget in [root, *root.findChildren(QWidget)]:
            if independent_ui_scale(widget):
                continue
            if plot is not None and (widget is plot or plot.isAncestorOf(widget)):
                continue
            style = widget.styleSheet()
            if style:
                cached = self._styles.get(widget)
                base = style if cached is None or style != cached[1] else cached[0]
                scaled = scaled_style(base, factor)
                if scaled != style:
                    widget.setStyleSheet(scaled)
                self._styles[widget] = (base, scaled)
            if widget is not root and widget not in excluded:
                if widget not in self._metrics:
                    self._metrics[widget] = (widget.minimumSize(), widget.maximumSize())
                minimum, maximum = self._metrics[widget]
                widget.setMinimumSize(round(minimum.width() * factor), round(minimum.height() * factor))
                widget.setMaximumSize(
                    *(round(value * factor) if value < 16777215 else value for value in (maximum.width(), maximum.height()))
                )
                if isinstance(widget, QToolButton):
                    size = max(8, round(20 * factor))
                    widget.setIconSize(QSize(size, size))
            layout = widget.layout()
            if layout is not None and widget not in excluded:
                if layout not in self._layouts:
                    margins = layout.contentsMargins()
                    self._layouts[layout] = (
                        (margins.left(), margins.top(), margins.right(), margins.bottom()),
                        layout.spacing(),
                    )
                margins, spacing = self._layouts[layout]
                layout.setContentsMargins(*(round(value * factor) for value in margins))
                if spacing >= 0:
                    layout.setSpacing(max(0, round(spacing * factor)))
            if isinstance(widget, QAbstractItemView) and hasattr(widget, "verticalHeader"):
                if widget not in self._tables:
                    self._tables[widget] = widget.verticalHeader().defaultSectionSize()
                widget.verticalHeader().setDefaultSectionSize(max(10, round(self._tables[widget] * factor)))
                widget.horizontalHeader().setMinimumSectionSize(max(6, round(20 * factor)))
