"""Persistent click-to-explain mode that never executes the intercepted command."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QSignalBlocker, Qt
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QRubberBand, QVBoxLayout, QWidget

from vibrational_finder.ui.context_help_topics import HelpArticle, resolve_help


class _HelpPopup(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("contextHelpPopup")
        self.setProperty("independentUiScale", True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "QFrame#contextHelpPopup { background: #fff7f8; color: #2c1720; "
            "border: 2px solid #c8324b; border-radius: 9px; }"
            "QLabel { color: #2c1720; background: transparent; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size: 16px; font-weight: 600;")
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setMaximumWidth(380)
        layout.addWidget(self.heading)
        layout.addWidget(self.body)

    def show_article(self, article: HelpArticle, target: QWidget) -> None:
        self.heading.setText(article.title)
        self.body.setText(f"{article.what}\n\nWhy: {article.why}\n\nHow: {article.how}")
        self.adjustSize()
        position = target.mapToGlobal(QPoint(target.width() + 10, 0))
        self.move(position)
        self.show()


class ContextHelpController(QObject):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window = window
        self.enabled = False
        self.popup = _HelpPopup(window)
        self.highlight = QRubberBand(QRubberBand.Shape.Rectangle, window)
        self.highlight.setProperty("independentUiScale", True)

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        app = QApplication.instance()
        if app is not None:
            if enabled:
                app.installEventFilter(self)
                app.setOverrideCursor(Qt.CursorShape.WhatsThisCursor)
            else:
                app.removeEventFilter(self)
                app.restoreOverrideCursor()
        if not enabled:
            self.popup.hide()
            self.highlight.hide()
        button = self.window._layout_state.help_button
        if button is not None:
            with QSignalBlocker(button):
                button.setChecked(enabled)
        self.window.top_toolbar._apply_style(self.window._dark_theme)

    def _belongs_to_window(self, widget: QWidget) -> bool:
        current: QWidget | None = widget
        while current is not None:
            if current is self.window:
                return True
            current = current.parentWidget()
        return False

    def _show_highlight(self, target: QWidget) -> None:
        top_left = target.mapTo(self.window, QPoint(0, 0))
        self.highlight.setGeometry(target.rect().translated(top_left))
        self.highlight.show()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if not self.enabled or not isinstance(watched, QWidget) or not self._belongs_to_window(watched):
            return False
        kind = event.type()
        if kind in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride) and event.key() == Qt.Key.Key_Escape:
            event.accept()
            if kind == QEvent.Type.KeyPress:
                self.set_enabled(False)
            return True
        if watched is self.popup or self.popup.isAncestorOf(watched):
            return False
        help_button = self.window._layout_state.help_button
        if watched is help_button or (help_button is not None and help_button.isAncestorOf(watched)):
            return False
        if kind == QEvent.Type.MouseButtonPress:
            target, article = resolve_help(self.window, watched)
            self._show_highlight(target)
            self.popup.show_article(article, target)
            event.accept()
            return True
        if kind in (
            QEvent.Type.MouseButtonRelease,
            QEvent.Type.MouseButtonDblClick,
            QEvent.Type.ContextMenu,
            QEvent.Type.Wheel,
            QEvent.Type.KeyPress,
            QEvent.Type.KeyRelease,
            QEvent.Type.ShortcutOverride,
        ):
            event.accept()
            return True
        return kind == QEvent.Type.ToolTip
