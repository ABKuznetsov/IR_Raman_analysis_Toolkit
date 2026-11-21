from __future__ import annotations

import re
from xml.dom import Node

from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont, QPainterPath, QTextLayout

from .options import SvgTextMode


_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
_FONT_ATTRIBUTES = {"font-family", "font-size", "font-style", "font-weight"}


def _inherited_attribute(element, name: str, default: str = "") -> str:
    current = element
    while current is not None and current.nodeType == Node.ELEMENT_NODE:
        if current.hasAttribute(name):
            return current.getAttribute(name)
        current = current.parentNode
    return default


def _number_attribute(element, name: str, default: float = 0.0) -> float:
    match = _NUMBER.search(element.getAttribute(name))
    return float(match.group()) if match else default


def _font_family(element) -> str:
    value = _inherited_attribute(element, "font-family", "Sans Serif").strip()
    return value.strip('"\'') or "Sans Serif"


def svg_font_families(root) -> tuple[str, ...]:
    return tuple(sorted({_font_family(element) for element in root.getElementsByTagName("text")}))


def _font_for_text(element) -> tuple[QFont, float]:
    family = _font_family(element)
    pixel_size = max(0.01, float(_inherited_attribute(element, "font-size", "12")))
    font = QFont(family)
    weight = int(float(_inherited_attribute(element, "font-weight", "400")))
    font.setWeight(QFont.Weight(max(1, min(1000, weight))))
    font.setItalic(_inherited_attribute(element, "font-style", "normal") in {"italic", "oblique"})
    # SVGExporter writes CSS pixels at 96 dpi from Qt point sizes.
    font.setPointSizeF(pixel_size * 72.0 / 96.0)
    return font, pixel_size


def _text_path(element) -> QPainterPath:
    text = "".join(
        child.data for child in element.childNodes
        if child.nodeType in {Node.TEXT_NODE, Node.CDATA_SECTION_NODE}
    )
    x = _number_attribute(element, "x")
    y = _number_attribute(element, "y")
    font, pixel_size = _font_for_text(element)
    layout = QTextLayout(text, font)
    layout.beginLayout()
    line = layout.createLine()
    layout.endLayout()
    result = QPainterPath()
    if not line.isValid():
        return result
    for glyph_run in layout.glyphRuns():
        raw_font = glyph_run.rawFont()
        source_pixel_size = raw_font.pixelSize()
        scale = pixel_size / source_pixel_size if source_pixel_size > 0 else 1.0
        raw_font.setPixelSize(pixel_size)
        baseline_offset = y - line.ascent() * scale
        for glyph, position in zip(glyph_run.glyphIndexes(), glyph_run.positions(), strict=True):
            origin = QPointF(x + position.x() * scale, baseline_offset + position.y() * scale)
            result.addPath(raw_font.pathForGlyph(glyph).translated(origin))
    return result


def _number(value: float) -> str:
    rounded = round(float(value), 6)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:g}"


def painter_path_svg_data(path: QPainterPath) -> str:
    commands: list[str] = []
    index = 0
    while index < path.elementCount():
        element = path.elementAt(index)
        if element.type == QPainterPath.ElementType.MoveToElement:
            commands.append(f"M{_number(element.x)} {_number(element.y)}")
        elif element.type == QPainterPath.ElementType.LineToElement:
            commands.append(f"L{_number(element.x)} {_number(element.y)}")
        elif element.type == QPainterPath.ElementType.CurveToElement:
            control_2 = path.elementAt(index + 1)
            end = path.elementAt(index + 2)
            commands.append(
                "C"
                f"{_number(element.x)} {_number(element.y)} "
                f"{_number(control_2.x)} {_number(control_2.y)} "
                f"{_number(end.x)} {_number(end.y)}"
            )
            index += 2
        index += 1
    return " ".join(commands)


def convert_svg_text_to_curves(root) -> int:
    text_elements = list(root.getElementsByTagName("text"))
    for index, text_element in enumerate(text_elements, start=1):
        path_element = root.ownerDocument.createElement("path")
        for name in list(text_element.attributes.keys()):
            if name not in _FONT_ATTRIBUTES | {"x", "y", "xml:space", "id"}:
                path_element.setAttribute(name, text_element.getAttribute(name))
        path_element.setAttribute("id", f"text-curve-{index:04d}")
        path_element.setAttribute("data-source", "text")
        path_element.setAttribute("d", painter_path_svg_data(_text_path(text_element)))
        text_element.parentNode.replaceChild(path_element, text_element)
    return len(text_elements)


def apply_svg_text_mode(root, mode: SvgTextMode) -> None:
    families = svg_font_families(root)
    root.setAttribute("data-text-mode", mode.value)
    root.setAttribute("data-font-families", ", ".join(families))
    if mode is SvgTextMode.CURVES:
        convert_svg_text_to_curves(root)
