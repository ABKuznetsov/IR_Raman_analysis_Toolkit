from __future__ import annotations

from collections.abc import Callable
import traceback

import time

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal


class BackgroundTaskWorker(QObject):
    finished = Signal(object)
    failed = Signal(str, str)

    def __init__(self, task: Callable[[], object]) -> None:
        super().__init__()
        self._task = task

    def run(self) -> None:
        try:
            self.finished.emit(self._task())
        except Exception as exc:
            self.failed.emit(str(exc), traceback.format_exc())


class BackgroundTaskHandle(QObject):
    finished = Signal(object)
    failed = Signal(str, str)
    drained = Signal()

    def __init__(self, task: Callable[[], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._thread = QThread(self)
        self._active = True
        self._worker = BackgroundTaskWorker(task)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_drained)

    def start(self) -> None:
        self._thread.start()

    def cancel(self) -> None:
        """Suppress delivery; the Python callable is allowed to finish safely."""
        self._active = False

    def is_running(self) -> bool:
        return self._thread.isRunning()

    def wait(self, timeout_ms: int = 5000) -> bool:
        deadline = time.monotonic() + max(timeout_ms, 0) / 1000.0
        app = QCoreApplication.instance()
        while self._thread.isRunning() and time.monotonic() < deadline:
            if app is not None:
                app.processEvents()
            self._thread.wait(10)
        if app is not None:
            app.processEvents()
        return not self._thread.isRunning()

    def _on_finished(self, result: object) -> None:
        if self._active:
            self.finished.emit(result)

    def _on_failed(self, message: str, details: str) -> None:
        if self._active:
            self.failed.emit(message, details)

    def _on_drained(self) -> None:
        self.drained.emit()
