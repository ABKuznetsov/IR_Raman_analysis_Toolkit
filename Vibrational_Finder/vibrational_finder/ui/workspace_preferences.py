from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math

from PySide6.QtCore import QSettings

from vibrational_finder.ui.app_settings import app_settings
from vibrational_finder.ui.layout_state import normalize_splitter_ratios
from vibrational_finder.ui.interface_scaling import INTERFACE_SCALE_PERCENTAGES


WORKSPACE_KEY = "ui/workspace_view_v1"

# Exact reference proportions from XRD Phase Finder 1.6.7. They are stored
# as ratios, never screen pixels, so the same workspace survives DPI and
# monitor-size changes.
DEFAULT_SPLITTER_PROPORTIONS = {
    "main_splitter": (0.12429378531073448, 0.5954802259887007, 0.280225988700565),
    "center_splitter": (0.7208053691275169, 0.27919463087248314),
    "composition_splitter": (0.3714585519412382, 0.6285414480587619),
}


@dataclass(slots=True)
class WorkspaceState:
    density: float = 1.0
    ui_scale_percent: int = 100
    splitter_ratios: dict[str, tuple[float, ...]] = field(default_factory=dict)
    table_column_proportions: dict[str, tuple[float, ...]] = field(default_factory=dict)
    table_column_order: dict[str, tuple[int, ...]] = field(default_factory=dict)
    plot_aspect_mode: str = "Fit"


class WorkspacePreferences:
    def __init__(self, settings: QSettings | None = None) -> None:
        self.settings = settings or app_settings()

    def load(self) -> WorkspaceState:
        try:
            payload = json.loads(self.settings.value(WORKSPACE_KEY, "", type=str))
            if not isinstance(payload, dict):
                return WorkspaceState()
            percent = self._scale_percent(payload)
            density = percent / 100.0
            splitter_ratios = self._safe_ratio_mapping(payload.get("splitter_ratios", {}))
            table_proportions = self._safe_ratio_mapping(payload.get("table_column_proportions", {}))
            table_order = self._safe_order_mapping(payload.get("table_column_order", {}))
            aspect = str(payload.get("plot_aspect_mode", "Fit"))
            return WorkspaceState(
                density=density,
                ui_scale_percent=percent,
                splitter_ratios=splitter_ratios,
                table_column_proportions=table_proportions,
                table_column_order=table_order,
                plot_aspect_mode=aspect,
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return WorkspaceState()

    def save(self, state: WorkspaceState) -> None:
        payload = asdict(state)
        percent = int(state.ui_scale_percent)
        if percent not in INTERFACE_SCALE_PERCENTAGES:
            percent = 100
        payload["ui_scale_percent"] = percent
        payload["density"] = percent / 100.0
        self.settings.setValue(WORKSPACE_KEY, json.dumps(payload, separators=(",", ":")))

    def has_saved_state(self) -> bool:
        return self.settings.contains(WORKSPACE_KEY)

    @staticmethod
    def _safe_ratio_mapping(value: object) -> dict[str, tuple[float, ...]]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, tuple[float, ...]] = {}
        for key, ratios in value.items():
            if not isinstance(ratios, (list, tuple)):
                continue
            try:
                result[str(key)] = normalize_splitter_ratios(ratios, len(ratios))
            except (TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _safe_order_mapping(value: object) -> dict[str, tuple[int, ...]]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, tuple[int, ...]] = {}
        for key, order in value.items():
            if not isinstance(order, (list, tuple)) or any(isinstance(item, bool) for item in order):
                continue
            try:
                items = tuple(int(item) for item in order)
            except (TypeError, ValueError):
                continue
            if len(set(items)) != len(items) or any(item < 0 for item in items):
                continue
            result[str(key)] = items
        return result

    @staticmethod
    def _scale_percent(payload: dict[str, object]) -> int:
        try:
            percent = int(payload.get("ui_scale_percent", 0))
        except (TypeError, ValueError):
            percent = 0
        if percent in INTERFACE_SCALE_PERCENTAGES:
            return percent
        try:
            density = float(payload.get("density", 1.0))
        except (TypeError, ValueError):
            return 100
        if not math.isfinite(density) or not 0.3 <= density <= 1.5:
            return 100
        return min(INTERFACE_SCALE_PERCENTAGES, key=lambda value: abs(value / 100.0 - density))
