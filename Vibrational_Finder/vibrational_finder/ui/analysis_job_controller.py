from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, Signal

from vibrational_finder.ui.background_task import BackgroundTaskHandle


class AnalysisJobController(QObject):
    """Own Match workers and suppress cancelled or revision-stale outcomes."""

    pending = Signal(object)
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str, str)
    cancelled = Signal()
    stale = Signal(object)
    runningChanged = Signal(bool)

    def __init__(
        self,
        analysis_controller: Any,
        parent: QObject | None = None,
        *,
        handle_factory: Callable[..., BackgroundTaskHandle] = BackgroundTaskHandle,
    ) -> None:
        super().__init__(parent)
        self.analysis_controller = analysis_controller
        self._handle_factory = handle_factory
        self._current: BackgroundTaskHandle | None = None
        self._handles: list[BackgroundTaskHandle] = []

    def start(self, request: object) -> BackgroundTaskHandle:
        if self._current is not None:
            self._cancel_current(emit_signal=True)
        handle = self._handle_factory(lambda: self.analysis_controller.run(request), self)
        self._current = handle
        self._handles.append(handle)
        handle.finished.connect(lambda outcome, active=handle: self._finished(active, outcome))
        handle.failed.connect(lambda message, details, active=handle: self._failed(active, message, details))
        handle.drained.connect(lambda active=handle: self._drained(active))
        self.pending.emit(request)
        self.progress.emit(0, "Searching spectroscopy references")
        self.runningChanged.emit(True)
        handle.start()
        return handle

    def cancel(self) -> None:
        self._cancel_current(emit_signal=True)

    def _cancel_current(self, *, emit_signal: bool) -> None:
        handle = self._current
        if handle is None:
            return
        self._current = None
        handle.cancel()
        if emit_signal:
            self.cancelled.emit()
        self.runningChanged.emit(False)

    def is_running(self) -> bool:
        return self._current is not None

    def _finished(self, handle: BackgroundTaskHandle, outcome: object) -> None:
        if handle is not self._current:
            return
        self._current = None
        self.runningChanged.emit(False)
        if self.analysis_controller.apply_if_current(outcome):
            self.progress.emit(100, "Match complete")
            self.succeeded.emit(outcome)
        else:
            self.stale.emit(outcome)

    def _failed(self, handle: BackgroundTaskHandle, message: str, details: str) -> None:
        if handle is not self._current:
            return
        self._current = None
        self.runningChanged.emit(False)
        self.failed.emit(message, details)

    def _drained(self, handle: BackgroundTaskHandle) -> None:
        if handle in self._handles:
            self._handles.remove(handle)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        self._cancel_current(emit_signal=False)
        handles = list(self._handles)
        for handle in handles:
            handle.cancel()
        if not handles:
            return True
        per_handle = max(1, timeout_ms // len(handles))
        drained_results = [handle.wait(per_handle) for handle in handles]
        self._handles = [handle for handle in self._handles if handle.is_running()]
        return all(drained_results)
