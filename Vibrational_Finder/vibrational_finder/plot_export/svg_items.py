"""Exact item SVG adapter based on pyqtgraph 0.14.0 SVGExporter (MIT)."""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from xml.dom import Node

import pyqtgraph
from PySide6.QtGui import QColor

from .snapshot import CanvasItemSnapshot


SUPPORTED_PYQTGRAPH_VERSION = "0.14.0"


class UnsupportedPlotExporterError(RuntimeError):
    pass


@dataclass(slots=True)
class SvgItemFragment:
    node: object
    definitions: list[object]


def _svg_module():
    if pyqtgraph.__version__ != SUPPORTED_PYQTGRAPH_VERSION:
        raise UnsupportedPlotExporterError(
            f"Layered SVG export supports pyqtgraph {SUPPORTED_PYQTGRAPH_VERSION}; "
            f"detected {pyqtgraph.__version__}"
        )
    module = importlib.import_module("pyqtgraph.exporters.SVGExporter")
    if not hasattr(module, "_generateItemSvg"):
        raise UnsupportedPlotExporterError("pyqtgraph item-level SVG API is unavailable")
    return module


def _reset_export_mode(item) -> None:
    pending = [item]
    while pending:
        current = pending.pop()
        pending.extend(current.childItems())
        if hasattr(current, "setExportMode"):
            current.setExportMode(False)


def render_item_svg(
    item_snapshot: CanvasItemSnapshot,
    *,
    root_item,
    canvas_size: tuple[int, int],
) -> SvgItemFragment:
    module = _svg_module()
    options = {
        "width": float(canvas_size[0]),
        "height": float(canvas_size[1]),
        "background": QColor("transparent"),
        "scaling stroke": False,
    }
    try:
        node, definitions = module._generateItemSvg(
            item_snapshot.item,
            root=root_item,
            options=options,
        )
    finally:
        _reset_export_mode(item_snapshot.item)
    return SvgItemFragment(node=node, definitions=list(definitions))


def _has_descendant(element, tag_name: str) -> bool:
    return bool(element.getElementsByTagName(tag_name))


def split_axis_fragment(fragment: SvgItemFragment, *, grid_enabled: bool) -> tuple[SvgItemFragment, SvgItemFragment | None]:
    axis_root = fragment.node.cloneNode(False)
    grid_root = fragment.node.cloneNode(False)
    elements = [child for child in fragment.node.childNodes if child.nodeType == Node.ELEMENT_NODE]
    text_started = False
    for index, child in enumerate(elements):
        contains_text = _has_descendant(child, "text")
        if contains_text:
            text_started = True
        if grid_enabled and index > 0 and not text_started:
            grid_root.appendChild(child.cloneNode(True))
        else:
            axis_root.appendChild(child.cloneNode(True))
    grid_fragment = (
        SvgItemFragment(node=grid_root, definitions=[])
        if any(child.nodeType == Node.ELEMENT_NODE for child in grid_root.childNodes)
        else None
    )
    return SvgItemFragment(node=axis_root, definitions=fragment.definitions), grid_fragment


def namespace_svg_fragment(element, definitions: list[object], prefix: str) -> None:
    id_mapping: dict[str, str] = {}
    roots = [element, *definitions]
    all_elements = [
        current
        for root in roots
        for current in [root, *root.getElementsByTagName("*")]
    ]
    for current in all_elements:
        if current.hasAttribute("id"):
            old_id = current.getAttribute("id")
            new_id = f"{prefix}-{old_id}"
            id_mapping[old_id] = new_id
            current.setAttribute("id", new_id)
    if not id_mapping:
        return
    for current in all_elements:
        for attribute_name in list(current.attributes.keys()):
            value = current.getAttribute(attribute_name)
            for old_id, new_id in id_mapping.items():
                value = value.replace(f"url(#{old_id})", f"url(#{new_id})")
                value = re.sub(rf"(?<![\w-])#{re.escape(old_id)}(?![\w-])", f"#{new_id}", value)
            current.setAttribute(attribute_name, value)


def namespace_svg_references(element, prefix: str) -> None:
    namespace_svg_fragment(element, [], prefix)
