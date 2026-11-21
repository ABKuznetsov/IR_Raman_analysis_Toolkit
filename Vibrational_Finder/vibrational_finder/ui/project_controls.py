from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget


class ProjectControlsWidget(QWidget):
    """Compact project-tree controls matching the XRD Finder sidebar."""

    addSeriesRequested = Signal()
    moveRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("projectControls")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 4)
        layout.setSpacing(6)

        self.add_series_button = QPushButton("+  Add series")
        self.add_series_button.setObjectName("seriesAddButton")
        self.add_series_button.setAccessibleName("Add series")
        self.add_series_button.setMinimumHeight(26)
        self.add_series_button.setToolTip("Add a named series to the project tree")
        self.add_series_button.clicked.connect(self.addSeriesRequested)
        layout.addWidget(self.add_series_button)

        order_row = QHBoxLayout()
        order_row.setContentsMargins(0, 0, 0, 0)
        order_row.setSpacing(4)
        order_row.addWidget(QLabel("Order"))

        self.move_up_button = QToolButton()
        self.move_up_button.setObjectName("moveUpButton")
        self.move_up_button.setText("Up")
        self.move_up_button.setToolTip("Move the selected series or spectrum up")
        self.move_up_button.clicked.connect(lambda: self.moveRequested.emit(-1))

        self.move_down_button = QToolButton()
        self.move_down_button.setObjectName("moveDownButton")
        self.move_down_button.setText("Down")
        self.move_down_button.setToolTip("Move the selected series or spectrum down")
        self.move_down_button.clicked.connect(lambda: self.moveRequested.emit(1))

        order_row.addWidget(self.move_up_button)
        order_row.addWidget(self.move_down_button)
        order_row.addStretch(1)
        layout.addLayout(order_row)
