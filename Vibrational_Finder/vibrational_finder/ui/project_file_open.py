"""Queue native Finder/Dock IRFF open events until the main window is ready."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt, QTimer


class ProjectFileOpenHandler(QObject):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.window = None
        self._paths: list[str] = []
        self._opening = False
        app.installEventFilter(self)

    def set_window(self, window) -> None:
        self.window = window
        QTimer.singleShot(0, self._open_next)

    def eventFilter(self, _watched, event) -> bool:  # noqa: N802 - Qt API
        if event.type() != QEvent.Type.FileOpen:
            return False
        path = event.file() or event.url().toLocalFile()
        if not path or Path(path).suffix.lower() != ".irff":
            return False
        resolved = str(Path(path).expanduser().resolve())
        if resolved not in self._paths:
            self._paths.append(resolved)
        event.accept()
        QTimer.singleShot(0, self._open_next)
        return True

    def _open_next(self) -> None:
        if self.window is None or self._opening or not self._paths:
            return
        path = Path(self._paths.pop(0))
        self._opening = True
        try:
            current = getattr(getattr(self.window, "document", None), "path", None)
            same = current is not None and Path(current).expanduser().resolve() == path
            confirm = getattr(self.window, "_confirm_document_replacement", None)
            allowed = same or not callable(confirm) or confirm("open another project")
            if allowed and not same:
                self.window.open_project_path(path)
            self.window.setWindowState(self.window.windowState() & ~Qt.WindowState.WindowMinimized)
            self.window.raise_()
            self.window.activateWindow()
        finally:
            self._opening = False
        if self._paths:
            QTimer.singleShot(0, self._open_next)
