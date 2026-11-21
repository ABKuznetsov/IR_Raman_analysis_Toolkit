from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class WrappingLayout(QLayout):
    def __init__(self, parent=None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._arrange(QRect(0, 0, width, 0), False)

    def sizeHint(self) -> QSize:
        widths = sum(item.sizeHint().width() for item in self._items)
        return QSize(widths + max(0, len(self._items) - 1) * self.spacing(), self.minimumSize().height())

    def minimumSize(self) -> QSize:
        size = QSize(0, 0)
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        return size

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._arrange(rect, True)

    def _arrange(self, rect: QRect, apply: bool) -> int:
        x, y = rect.x(), rect.y()
        height = 0
        gap = self.spacing()
        for item in self._items:
            widget = item.widget()
            hint = widget.sizeHint() if widget is not None else item.sizeHint()
            width = max(0, min(hint.width(), max(1, rect.width())))
            if x > rect.x() and x + width > rect.x() + rect.width():
                x = rect.x()
                y += height + gap
                height = 0
            if apply:
                item.setGeometry(QRect(x, y, width, max(0, hint.height())))
            x += width + gap
            height = max(height, hint.height())
        return y - rect.y() + height
