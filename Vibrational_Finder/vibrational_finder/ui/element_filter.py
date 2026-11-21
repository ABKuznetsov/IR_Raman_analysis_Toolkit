from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from vibrational_finder.ui.wrapping_layout import WrappingLayout
from vibrational_finder.ui.theme import colored_hover_background


def periodic_table_positions() -> list[tuple[str, int, int]]:
    return [
        ("H", 1, 1), ("He", 1, 18),
        ("Li", 2, 1), ("Be", 2, 2),
        ("B", 2, 13), ("C", 2, 14), ("N", 2, 15), ("O", 2, 16), ("F", 2, 17), ("Ne", 2, 18),
        ("Na", 3, 1), ("Mg", 3, 2),
        ("Al", 3, 13), ("Si", 3, 14), ("P", 3, 15), ("S", 3, 16), ("Cl", 3, 17), ("Ar", 3, 18),
        ("K", 4, 1), ("Ca", 4, 2), ("Sc", 4, 3), ("Ti", 4, 4), ("V", 4, 5),
        ("Cr", 4, 6), ("Mn", 4, 7), ("Fe", 4, 8), ("Co", 4, 9), ("Ni", 4, 10),
        ("Cu", 4, 11), ("Zn", 4, 12), ("Ga", 4, 13), ("Ge", 4, 14), ("As", 4, 15),
        ("Se", 4, 16), ("Br", 4, 17), ("Kr", 4, 18),
        ("Rb", 5, 1), ("Sr", 5, 2), ("Y", 5, 3), ("Zr", 5, 4), ("Nb", 5, 5),
        ("Mo", 5, 6), ("Tc", 5, 7), ("Ru", 5, 8), ("Rh", 5, 9), ("Pd", 5, 10),
        ("Ag", 5, 11), ("Cd", 5, 12), ("In", 5, 13), ("Sn", 5, 14), ("Sb", 5, 15),
        ("Te", 5, 16), ("I", 5, 17), ("Xe", 5, 18),
        ("Cs", 6, 1), ("Ba", 6, 2), ("La", 6, 3), ("Hf", 6, 4), ("Ta", 6, 5),
        ("W", 6, 6), ("Re", 6, 7), ("Os", 6, 8), ("Ir", 6, 9), ("Pt", 6, 10),
        ("Au", 6, 11), ("Hg", 6, 12), ("Tl", 6, 13), ("Pb", 6, 14), ("Bi", 6, 15),
        ("Po", 6, 16), ("At", 6, 17), ("Rn", 6, 18),
        ("Fr", 7, 1), ("Ra", 7, 2), ("Ac", 7, 3), ("Rf", 7, 4), ("Db", 7, 5),
        ("Sg", 7, 6), ("Bh", 7, 7), ("Hs", 7, 8), ("Mt", 7, 9), ("Ds", 7, 10),
        ("Rg", 7, 11), ("Cn", 7, 12), ("Nh", 7, 13), ("Fl", 7, 14), ("Mc", 7, 15),
        ("Lv", 7, 16), ("Ts", 7, 17), ("Og", 7, 18),
    ]


def lanthanides() -> list[str]:
    return ["Ce", "Pr", "Nd", "Pm", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"]


def actinides() -> list[str]:
    return ["Th", "Pa", "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr"]


_ELEMENT_SORT_ORDER: dict[str, int] | None = None


def element_sort_key(symbol: str) -> int:
    global _ELEMENT_SORT_ORDER
    if _ELEMENT_SORT_ORDER is None:
        order = [item[0] for item in periodic_table_positions()] + lanthanides() + actinides()
        _ELEMENT_SORT_ORDER = {element: index for index, element in enumerate(order)}
    return _ELEMENT_SORT_ORDER.get(symbol, len(_ELEMENT_SORT_ORDER))


def element_state_style(state: str) -> str:
    palette = {
        "neutral": ("#0f8a75", "#2c927e", "#ffffff"),
        "optional": ("#0f8a75", "#2c927e", "#ffffff"),
        "required": ("#315f92", "#69a7e8", "#f3f9ff"),
        "excluded": ("#9b1b59", "#d85a98", "#ffffff"),
        "any": ("#5f6368", "#8a8d91", "#ffffff"),
    }
    bg, border, color = palette.get(state, palette["neutral"])
    return (
        "QPushButton {"
        f"background: {bg}; border: 1px solid {border}; color: {color};"
        "border-radius: 4px; font-weight: 600; padding: 0px;"
        "}"
        f"QPushButton:hover:enabled {{ background: {colored_hover_background(bg)}; "
        f"border-color: {border}; color: {color}; }}"
    )


class ElementFilterButton(QPushButton):
    leftClicked = Signal(str)
    rightClicked = Signal(str)
    gestureStarted = Signal(str, object)
    gestureMoved = Signal(object)
    gestureFinished = Signal(object)

    def __init__(self, symbol: str) -> None:
        super().__init__(symbol)
        self.symbol = symbol
        self.setToolTip(
            f"{symbol}\n"
            "Left click: required element (blue).\n"
            "Right click: exclude structures containing this element (pink).\n"
            "Click again to remove the filter.\n"
            "Hold and drag to select several elements."
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.gestureStarted.emit(self.symbol, event.button())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self.gestureMoved.emit(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.gestureFinished.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PeriodicTableWidget(QWidget):
    leftClicked = Signal(str)
    rightClicked = Signal(str)
    elementsPainted = Signal(list, str)
    modeToggleRequested = Signal()
    _GRID_COLUMNS = 19
    _GRID_ROWS = 11

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # The element grid already computes its cell geometry from the space
        # available.  Applying the global UI multiplier to its 360 px minimum
        # width makes the right dock overflow at 150% instead of making the
        # cells adapt, so keep this one responsive widget on its own scale.
        self.setProperty("independentUiScale", True)
        self.setToolTip(
            "Element filter table\n"
            "Left click marks an element as required.\n"
            "Right click marks an element as absent.\n"
            "Green elements may be present.\n"
            "Pink elements are excluded from the current search gate."
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._widgets: list[QWidget] = []
        self._buttons: dict[str, ElementFilterButton] = {}
        self._element_states: dict[str, str] = {}
        self._grid: QGridLayout | None = None
        self.mode_button: QPushButton | None = None
        self._excluded_mode = False
        self._drag_button = None
        self._drag_state = ""
        self._drag_symbols: list[str] = []
        self._legend_labels: list[QLabel] = []
        self._legend_swatches: list[QLabel] = []
        self._build_ui()

    def _start_element_gesture(self, symbol: str, button) -> None:
        self._drag_button = button
        self._drag_symbols = [symbol]
        selected_state = "required" if button == Qt.MouseButton.LeftButton else "excluded"
        current_state = self._element_states.get(symbol, "neutral")
        self._drag_state = "neutral" if current_state == selected_state else selected_state
        self._buttons[symbol].setStyleSheet(element_state_style(self._drag_state))

    def _extend_element_gesture(self, global_position) -> None:
        if self._drag_button is None:
            return
        widget = self.childAt(self.mapFromGlobal(global_position))
        if not isinstance(widget, ElementFilterButton):
            return
        if widget.symbol in self._drag_symbols:
            previous_index = self._drag_symbols.index(widget.symbol)
            for symbol in self._drag_symbols[previous_index + 1:]:
                self._buttons[symbol].setStyleSheet(
                    element_state_style(self._element_states.get(symbol, "neutral"))
                )
            del self._drag_symbols[previous_index + 1:]
        else:
            self._drag_symbols.append(widget.symbol)
            widget.setStyleSheet(element_state_style(self._drag_state))

    def _finish_element_gesture(self, global_position) -> None:
        if self._drag_button is None:
            return
        self._extend_element_gesture(global_position)
        button = self._drag_button
        state = self._drag_state
        symbols = list(self._drag_symbols)
        self._drag_button = None
        self._drag_state = ""
        self._drag_symbols = []
        if len(symbols) > 1:
            self.elementsPainted.emit(symbols, state)
        elif button == Qt.MouseButton.LeftButton:
            self.leftClicked.emit(symbols[0])
        else:
            self.rightClicked.emit(symbols[0])

    @property
    def element_symbols(self) -> list[str]:
        return list(self._buttons)

    def set_element_state(self, element: str, state: str) -> None:
        button = self._buttons.get(element)
        if button is not None:
            self._element_states[element] = state
            button.setStyleSheet(element_state_style(state))

    def set_excluded_mode(self, strict: bool) -> None:
        self._excluded_mode = bool(strict)
        if self.mode_button is None:
            return
        self.mode_button.setText("Allow others" if strict else "Exclude others")
        self.mode_button.setToolTip(
            "Allow all excluded elements in the search again; keep the required elements."
            if strict else
            "Exclude all optional elements from the search; keep the required elements."
        )
        if strict:
            self.mode_button.setStyleSheet(
                "QPushButton { background: #0f8a75; color: #ffffff; border: 2px solid #42c7ad; "
                "border-radius: 5px; font-weight: 700; padding: 3px; }"
                f"QPushButton:hover:enabled {{ background: {colored_hover_background('#0f8a75')}; border-color: #42c7ad; }}"
            )
        else:
            self.mode_button.setStyleSheet(
                "QPushButton { background: #9b1b59; color: #ffffff; border: 2px solid #d85a98; "
                "border-radius: 5px; font-weight: 700; padding: 3px; }"
                f"QPushButton:hover:enabled {{ background: {colored_hover_background('#9b1b59')}; border-color: #d85a98; }}"
            )

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._fit_cells_to_area()

    def _fit_cells_to_area(self) -> None:
        if self._grid is None:
            return
        margins = self.layout().contentsMargins()
        spacing_x = self._grid.horizontalSpacing()
        spacing_y = self._grid.verticalSpacing()
        available_width = max(1, self.width() - margins.left() - margins.right() - spacing_x * (self._GRID_COLUMNS - 1))
        density = getattr(self.window(), "ui_density_factor", 1.0)
        section_gap = round(6 * density)
        legend_height = self._legend_layout.heightForWidth(max(1, self.width()))
        available_height = max(
            1,
            self.height() - margins.top() - margins.bottom()
            - spacing_y * (self._GRID_ROWS - 1) - section_gap - round(18 * density) - legend_height,
        )
        width = max(4, available_width // self._GRID_COLUMNS)
        height = max(3, min(round(width * 1.2), available_height // 9))
        self._grid.setRowMinimumHeight(8, max(1, round(4 * density)))
        self._set_cell_size(width, height)

    def _set_cell_size(self, width: int, height: int) -> None:
        density = getattr(self.window(), "ui_density_factor", 1.0)
        font_size = max(3, min(round(20 * density), round(min(width * 0.7, height * 0.7))))
        font = self.font()
        font.setBold(True)
        while font_size > 3:
            font.setPixelSize(font_size)
            metrics = QFontMetrics(font)
            if metrics.height() <= height - 2 and max(
                metrics.horizontalAdvance(symbol) for symbol in self._buttons
            ) <= width - 2:
                break
            font_size -= 1
        header_size = max(3, min(round(12 * density), round(width * 0.45)))
        for widget in self._widgets:
            widget.setFixedSize(
                width,
                max(4, header_size + round(5 * density)) if isinstance(widget, QLabel) else height,
            )
            font = widget.font()
            font.setPixelSize(font_size)
            font.setBold(True)
            widget.setFont(font)
        if self.mode_button is not None:
            self.mode_button.setFixedSize(
                min(round(150 * density), width * 6 + round(10 * density)),
                min(round(34 * density), height * 2 + round(4 * density)),
            )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        grid = QGridLayout()
        self._grid = grid
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(1)
        grid.setVerticalSpacing(1)

        for group in range(1, 19):
            label = self._header_label(str(group))
            self._widgets.append(label)
            grid.addWidget(label, 0, group)

        for period in range(1, 8):
            label = self._header_label(f"P{period}")
            self._widgets.append(label)
            grid.addWidget(label, period, 0)

        for symbol, period, group in periodic_table_positions():
            self._add_element_button(grid, symbol, period, group)

        self.mode_button = QPushButton(self)
        self.mode_button.clicked.connect(self.modeToggleRequested)
        self.set_excluded_mode(False)
        grid.addWidget(self.mode_button, 2, 4, 2, 6, alignment=Qt.AlignmentFlag.AlignCenter)

        grid.setRowMinimumHeight(8, 4)
        lanth_label = self._header_label("L")
        act_label = self._header_label("A")
        self._widgets.extend([lanth_label, act_label])
        grid.addWidget(lanth_label, 9, 3)
        grid.addWidget(act_label, 10, 3)

        for index, symbol in enumerate(lanthanides()):
            self._add_element_button(grid, symbol, 9, 4 + index)

        for index, symbol in enumerate(actinides()):
            self._add_element_button(grid, symbol, 10, 4 + index)

        layout.addLayout(grid)
        legend = self._legend_layout = WrappingLayout(spacing=10)
        legend.setContentsMargins(2, 0, 2, 0)
        for state, label_text in (
            ("required", "Required"),
            ("neutral", "Optional"),
            ("excluded", "Excluded"),
        ):
            swatch = QLabel("H", self)
            swatch.setAlignment(Qt.AlignmentFlag.AlignCenter)
            swatch.setFixedSize(18, 18)
            swatch.setStyleSheet(element_state_style(state).replace("QPushButton", "QLabel"))
            label = QLabel(label_text, self)
            group = QWidget()
            row = QHBoxLayout(group)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(4)
            row.addWidget(swatch)
            row.addWidget(label)
            legend.addWidget(group)
            self._legend_swatches.append(swatch)
            self._legend_labels.append(label)
        layout.addLayout(legend)
        layout.addStretch(1)
        self.setMinimumHeight(215)
        self._fit_cells_to_area()

    def _header_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setProperty("periodicHeader", True)
        label.setStyleSheet("background: transparent; border: 0; color: #8c9ba9;")
        label.setFixedSize(22, 18)
        return label

    def _add_element_button(self, grid: QGridLayout, symbol: str, row: int, column: int) -> None:
        button = ElementFilterButton(symbol)
        button.setFixedSize(22, 18)
        button.setStyleSheet(element_state_style("neutral"))
        self._element_states[symbol] = "neutral"
        button.gestureStarted.connect(self._start_element_gesture)
        button.gestureMoved.connect(self._extend_element_gesture)
        button.gestureFinished.connect(self._finish_element_gesture)
        self._buttons[symbol] = button
        self._widgets.append(button)
        grid.addWidget(button, row, column)
