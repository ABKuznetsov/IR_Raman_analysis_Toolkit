from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from vibrational_finder.services.source_management import SpectroscopySourceManager
from vibrational_finder.ui.background_task import BackgroundTaskHandle


class SourceManagementJobController(QObject):
    """Run one source mutation at a time and suppress cancelled delivery."""

    pending = Signal(str, str)
    succeeded = Signal(str, str, object)
    failed = Signal(str, str, str, str)
    cancelled = Signal(str, str)
    runningChanged = Signal(bool)

    def __init__(
        self,
        manager: SpectroscopySourceManager,
        parent: QObject | None = None,
        *,
        handle_factory: Callable[..., BackgroundTaskHandle] = BackgroundTaskHandle,
    ) -> None:
        super().__init__(parent)
        self.manager = manager
        self._handle_factory = handle_factory
        self._current: BackgroundTaskHandle | None = None
        self._current_context: tuple[str, str] | None = None
        self._handles: list[BackgroundTaskHandle] = []

    def start(self, name: str, operation: str, package_key: str | None = None) -> BackgroundTaskHandle:
        self.cancel()
        task = lambda: self._run(name, operation, package_key)
        handle = self._handle_factory(task, self)
        self._current = handle
        self._current_context = (name, operation)
        self._handles.append(handle)
        handle.finished.connect(lambda result, active=handle: self._finished(active, result))
        handle.failed.connect(lambda message, details, active=handle: self._failed(active, message, details))
        handle.drained.connect(lambda active=handle: self._drained(active))
        self.pending.emit(name, operation)
        self.runningChanged.emit(True)
        handle.start()
        return handle

    def _run(self, name: str, operation: str, package_key: str | None) -> object:
        if operation == "update":
            return self.manager.update(name, package_key)
        if operation == "clear":
            return self.manager.clear(name)
        if operation == "build_index":
            return self.manager.build_index(name)
        if operation == "clear_index":
            return self.manager.clear_index(name)
        raise ValueError(f"Unknown source operation: {operation}")

    def cancel(self) -> None:
        if self._current is None:
            return
        handle = self._current
        context = self._current_context
        self._current = None
        self._current_context = None
        handle.cancel()
        if context is not None:
            self.cancelled.emit(*context)
        self.runningChanged.emit(False)

    def is_running(self) -> bool:
        return self._current is not None

    def _finished(self, handle: BackgroundTaskHandle, result: object) -> None:
        if handle is not self._current or self._current_context is None:
            return
        name, operation = self._current_context
        self._current = None
        self._current_context = None
        self.runningChanged.emit(False)
        self.succeeded.emit(name, operation, result)

    def _failed(self, handle: BackgroundTaskHandle, message: str, details: str) -> None:
        if handle is not self._current or self._current_context is None:
            return
        name, operation = self._current_context
        self._current = None
        self._current_context = None
        self.runningChanged.emit(False)
        self.failed.emit(name, operation, message, details)

    def _drained(self, handle: BackgroundTaskHandle) -> None:
        if handle in self._handles:
            self._handles.remove(handle)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        self.cancel()
        handles = list(self._handles)
        for handle in handles:
            handle.cancel()
        if not handles:
            return True
        per_handle = max(1, timeout_ms // len(handles))
        results = [handle.wait(per_handle) for handle in handles]
        self._handles = [handle for handle in self._handles if handle.is_running()]
        return all(results)
