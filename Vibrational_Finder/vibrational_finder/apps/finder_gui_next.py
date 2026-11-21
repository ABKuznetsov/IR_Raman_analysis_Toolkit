from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
import time
from collections.abc import Sequence
from typing import Protocol

from PySide6.QtWidgets import QApplication

from finder_core.models import SignalKind
from vibrational_finder.io.xy_loader import load_xy_spectrum
from vibrational_finder.models import ObservedSpectrum
from vibrational_finder.metadata import APP_NAME
from vibrational_finder.project_state import VibrationalProjectState
from vibrational_finder.ui.analysis_windows import SpectroscopyFinderWindow
from vibrational_finder.ui.project_file_open import ProjectFileOpenHandler


class EventProcessor(Protocol):
    def processEvents(self) -> None: ...  # noqa: N802 - Qt API


@dataclass(frozen=True, slots=True)
class StartupHandshake:
    prepared_file: Path | None
    show_signal_file: Path | None
    ready_file: Path | None
    timeout_seconds: float = 180.0

    @classmethod
    def from_environment(cls) -> "StartupHandshake":
        def path(name: str) -> Path | None:
            value = os.environ.get(name, "").strip()
            return Path(value) if value else None

        return cls(
            path("IR_RAMAN_PHASE_FINDER_PREPARED_FILE"),
            path("IR_RAMAN_PHASE_FINDER_SHOW_SIGNAL_FILE"),
            path("IR_RAMAN_PHASE_FINDER_READY_FILE"),
        )

    @staticmethod
    def _write(path: Path | None, value: str) -> None:
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        except OSError:
            pass

    def mark_prepared(self) -> None:
        self._write(self.prepared_file, "prepared")

    def wait_until_show(self, app: EventProcessor) -> None:
        if self.show_signal_file is None:
            return
        deadline = time.monotonic() + self.timeout_seconds
        while not self.show_signal_file.exists() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.05)

    def mark_ready(self) -> None:
        self._write(self.ready_file, "ready")


def build_local_project(spectrum_paths: Sequence[str]) -> VibrationalProjectState:
    project = VibrationalProjectState()
    for path in spectrum_paths:
        spectrum = load_xy_spectrum(path)
        if not isinstance(spectrum, ObservedSpectrum):
            continue
        if spectrum.kind == SignalKind.RAMAN:
            project.raman_spectra.append(spectrum)
        elif spectrum.kind == SignalKind.FTIR:
            project.ftir_spectra.append(spectrum)
        else:
            continue
        project.spectrum_order_ids.append(spectrum.id)
        project.visible_observed_keys.add(spectrum.id)
    if project.spectrum_order_ids:
        project.active_spectrum_key = project.spectrum_order_ids[0]
    return project


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("spectra", nargs="*")
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    file_open_handler = ProjectFileOpenHandler(app)
    project = build_local_project(args.spectra)
    window = SpectroscopyFinderWindow(project, defer_source_settings=True)
    file_open_handler.set_window(window)
    handshake = StartupHandshake.from_environment()
    handshake.mark_prepared()
    handshake.wait_until_show(app)
    if args.smoke_test:
        window.show()
        app.processEvents()
        handshake.mark_ready()
        window.close()
        app.processEvents()
        return 0
    window.show()
    app.processEvents()
    handshake.mark_ready()
    if os.environ.get("IR_RAMAN_CHECK_UPDATES") == "1":
        from vibrational_finder.ui.deferred_updates import update_controller

        update_controller(window).schedule()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
