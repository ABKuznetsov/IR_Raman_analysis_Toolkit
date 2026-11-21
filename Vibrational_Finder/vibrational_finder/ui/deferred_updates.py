"""Check releases after the main window opens, without downloading installers."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
import os
import re
from threading import Thread
import time
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QTimer, Qt, Signal, Slot
from PySide6.QtWidgets import QMessageBox

from vibrational_finder.metadata import APP_NAME, APP_VERSION, GITHUB_URL
from vibrational_finder.ui.app_settings import app_settings

RELEASES_URL = f"{GITHUB_URL}/releases"
MANIFEST_URL = (
    "https://raw.githubusercontent.com/ABKuznetsov/IR_Raman_analysis_Toolkit/"
    "main/toolkit/updates/ir_raman_phase_finder.json"
)


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    version: str
    url: str


def _version(value: object) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"v?(\d{1,8})\.(\d{1,8})\.(\d{1,8})", str(value))
    return tuple(int(part) for part in match.groups()) if match else None


def parse_update(payload: dict, *, current_version: str = APP_VERSION) -> UpdateInfo | None:
    apps = payload.get("apps")
    if isinstance(apps, dict):
        payload = apps.get("ir_raman_phase_finder", {})
    if not isinstance(payload, dict):
        return None
    remote = _version(payload.get("version"))
    current = _version(current_version)
    if remote is None or current is None or remote <= current:
        return None
    url = str(payload.get("release_page_url") or payload.get("release_url") or RELEASES_URL)
    try:
        address = urlsplit(url)
    except ValueError:
        address = urlsplit(RELEASES_URL)
        url = RELEASES_URL
    official_path = urlsplit(RELEASES_URL).path
    if address.scheme != "https" or address.netloc != "github.com" or (
        address.path != official_path and not address.path.startswith(f"{official_path}/")
    ):
        url = RELEASES_URL
    return UpdateInfo(".".join(map(str, remote)), url)


def fetch_update() -> UpdateInfo | None:
    import json
    import ssl
    from urllib.request import Request, urlopen

    import certifi

    request = Request(MANIFEST_URL, headers={"User-Agent": f"IR-Raman-Phase-Finder/{APP_VERSION}"})
    maximum = 2 * 1024 * 1024
    with urlopen(request, timeout=4, context=ssl.create_default_context(cafile=certifi.where())) as reply:
        raw = reply.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("The release manifest is too large.")
    payload = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid release manifest.")
    return parse_update(payload)


def _offline() -> bool:
    return os.environ.get("IR_RAMAN_OFFLINE", "").strip().casefold() in {"1", "true", "yes", "on"}


class UpdateController(QObject):
    finished = Signal(object, str)

    def __init__(self, window, settings=None) -> None:
        super().__init__(window)
        self.window = window
        self.settings = settings if settings is not None else app_settings()
        self.setting_key = f"updates/last_check/{APP_VERSION}"
        self.result: UpdateInfo | None = None
        self.busy = self.manual = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.check)
        self.finished.connect(self._complete)

    def schedule(self, delay_ms: int = 5000) -> None:
        self.timer.start(delay_ms)

    def check(self, *, manual: bool = False) -> None:
        if _offline():
            if manual:
                self._show("Offline mode is enabled. Updates were not checked.")
            return
        if self.busy:
            self.manual |= manual
            return
        try:
            last = float(self.settings.value(self.setting_key, 0))
        except (TypeError, ValueError):
            last = 0
        now = time.time()
        if not manual and 0 <= now - last < 86400:
            return
        self.settings.setValue(self.setting_key, now)
        self.busy = True
        self.manual = manual

        def work() -> None:
            info, error = None, ""
            try:
                info = fetch_update()
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            try:
                self.finished.emit(info, error)
            except RuntimeError:
                pass  # Qt may already have destroyed the window.

        Thread(target=work, name="ir-raman-update-check", daemon=True).start()

    @Slot(object, str)
    def _complete(self, info: UpdateInfo | None, error: str) -> None:
        self.busy = False
        self.result = info
        if not self.window.isVisible() or _offline():
            return
        if info is not None:
            action = getattr(self.window, "check_updates_action", None)
            if action is not None:
                action.setText(f"Update available: {info.version}…")
            self.window.statusBar().showMessage(
                f"{APP_NAME} {info.version} is available — see Help.", 15000,
            )
        if self.manual:
            if error:
                text = f"Could not check for updates: {escape(error)}"
            elif info is not None:
                text = f"{APP_NAME} {info.version} is available. <a href='{escape(info.url, quote=True)}'>View release</a>."
            else:
                text = f"{APP_NAME} {APP_VERSION} is up to date."
            self._show(text)

    def _show(self, text: str) -> None:
        message = QMessageBox(self.window)
        message.setWindowTitle("Updates")
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        message.setText(text)
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.exec()


def update_controller(window) -> UpdateController:
    controller = getattr(window, "_update_controller", None)
    if controller is None:
        controller = UpdateController(window)
        window._update_controller = controller
    return controller
