from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QSettings


def _default_data_root() -> Path:
    configured = os.environ.get("IR_RAMAN_DATA_DIR")
    if configured:
        return Path(configured)
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "Sci" / "apps" / "ir_raman_analysis_toolkit" / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sci" / "apps" / "ir_raman_analysis_toolkit" / "data"
    return Path.home() / ".local" / "share" / "Sci" / "apps" / "ir_raman_analysis_toolkit" / "data"


def configure_app_settings_storage() -> None:
    settings_root = _default_data_root() / "settings" / "qt"
    settings_root.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        str(settings_root),
    )


def app_settings() -> QSettings:
    configure_app_settings_storage()
    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "IRRamanPhaseFinder",
        "Standalone",
    )
