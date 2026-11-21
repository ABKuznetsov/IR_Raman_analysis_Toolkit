"""Consistent outline toolbar icons rendered at native display scales."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _outline(painter: QPainter, name: str) -> None:
    def line(*points: tuple[float, float]) -> None:
        painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))

    if name == "new":
        line((14, 3), (5, 3), (5, 21), (19, 21), (19, 8), (14, 3), (14, 8), (19, 8))
        line((9, 14), (15, 14)); line((12, 11), (12, 17))
    elif name == "open":
        line((3, 9), (3, 5), (9, 5), (11, 8), (20, 8), (20, 10))
        line((3, 9), (6, 20), (20, 20), (22, 10), (8, 10), (6, 20))
    elif name == "save":
        line((12, 3), (12, 16)); line((7, 11), (12, 16), (17, 11))
        line((4, 18), (4, 21), (20, 21), (20, 18))
    elif name == "import":
        line((12, 3), (12, 15)); line((7, 10), (12, 15), (17, 10))
        line((3, 15), (3, 21), (21, 21), (21, 15))
    elif name == "match":
        painter.drawEllipse(QRectF(3, 3, 13, 13)); line((15, 15), (21, 21))
        line((7, 11), (9, 7), (11, 12), (13, 9))
    elif name == "bands":
        path = QPainterPath(QPointF(2, 13))
        path.cubicTo(5, 13, 5, 7, 8, 7)
        path.cubicTo(11, 7, 11, 17, 14, 17)
        path.cubicTo(17, 17, 17, 10, 22, 10)
        painter.drawPath(path)
    elif name == "residual":
        line((3, 20), (12, 4), (21, 20), (3, 20)); line((8, 16), (16, 16))
    elif name == "export":
        line((12, 16), (12, 3)); line((7, 8), (12, 3), (17, 8))
        line((3, 15), (3, 21), (21, 21), (21, 15))
    elif name == "reset":
        painter.drawArc(QRectF(5, 5, 15, 15), -50 * 16, 280 * 16)
        line((3, 4), (3, 10), (9, 10))
    elif name == "fit":
        line((3, 9), (3, 3), (9, 3)); line((15, 3), (21, 3), (21, 9))
        line((3, 15), (3, 21), (9, 21)); line((15, 21), (21, 21), (21, 15))
        line((8, 15), (11, 9), (14, 15), (17, 11))
    elif name == "database":
        painter.drawEllipse(QRectF(4, 3, 16, 6))
        line((4, 6), (4, 18)); line((20, 6), (20, 18))
        painter.drawArc(QRectF(4, 9, 16, 6), 180 * 16, 180 * 16)
        painter.drawArc(QRectF(4, 15, 16, 6), 180 * 16, 180 * 16)
    elif name == "plot":
        line((3, 3), (3, 21), (22, 21)); line((6, 17), (10, 12), (13, 15), (17, 7), (21, 10))
    elif name == "instrument":
        path = QPainterPath()
        for index in range(32):
            angle = index * math.pi / 16
            radius = 10 if index % 4 in (1, 2) else 8
            point = QPointF(12 + radius * math.cos(angle), 12 + radius * math.sin(angle))
            path.moveTo(point) if index == 0 else path.lineTo(point)
        path.closeSubpath(); painter.drawPath(path); painter.drawEllipse(QRectF(8, 8, 8, 8))
    elif name == "layout":
        painter.drawRect(QRectF(3, 4, 18, 16)); line((9, 4), (9, 20)); line((15, 4), (15, 20))
    elif name == "help":
        painter.drawEllipse(QRectF(3, 3, 18, 18))
        font = painter.font(); font.setPixelSize(16); painter.setFont(font)
        painter.drawText(QRectF(3, 1, 18, 20), Qt.AlignmentFlag.AlignCenter, "?")
    elif name == "more":
        painter.save(); painter.setBrush(painter.pen().color()); painter.setPen(Qt.PenStyle.NoPen)
        for x in (5, 12, 19):
            painter.drawEllipse(QRectF(x - 1.3, 10.7, 2.6, 2.6))
        painter.restore()
    else:
        raise ValueError(f"Unknown toolbar icon: {name}")


def toolbar_icon(name: str, color: str, disabled_color: str) -> QIcon:
    icon = QIcon()
    for scale in (1, 2, 3):
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Disabled):
            for state in (QIcon.State.Off, QIcon.State.On):
                pixmap = QPixmap(20 * scale, 20 * scale)
                pixmap.setDevicePixelRatio(scale)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.scale(20 / 24, 20 / 24)
                stroke = disabled_color if mode == QIcon.Mode.Disabled else ("#ffffff" if state == QIcon.State.On else color)
                pen = QPen(QColor(stroke), 1.7)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                _outline(painter, name)
                painter.end()
                icon.addPixmap(pixmap, mode, state)
    return icon
