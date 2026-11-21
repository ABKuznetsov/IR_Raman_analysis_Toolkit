"""Follow the OS light/dark mode while retaining Finder widget styling."""

from PySide6.QtCore import QEvent, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from vibrational_finder.ui.theme import is_dark_theme


class SystemThemeObserver(QObject):
    changed = Signal(bool, bool)

    def __init__(self, window) -> None:
        super().__init__(window)
        self._dark = is_dark_theme(window)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._refresh)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            app.styleHints().colorSchemeChanged.connect(self._schedule)

    def _schedule(self, *_args) -> None:
        self._timer.start(0)

    def eventFilter(self, watched, event) -> bool:
        if watched is QApplication.instance() and event.type() == QEvent.Type.ApplicationPaletteChange:
            self._schedule()
        return False

    def _refresh(self) -> None:
        dark = is_dark_theme(self.parent())
        if dark != self._dark:
            previous, self._dark = self._dark, dark
            self.changed.emit(dark, previous)
