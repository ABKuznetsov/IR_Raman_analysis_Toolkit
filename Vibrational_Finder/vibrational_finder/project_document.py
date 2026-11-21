from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from vibrational_finder.project_state import VibrationalProjectState


@dataclass(slots=True)
class ProjectDocument:
    """Runtime lifecycle state around the portable spectroscopy project model."""

    state: VibrationalProjectState
    path: Path | None = None
    revision: int = 0
    saved_revision: int = 0

    def __post_init__(self) -> None:
        self.state.normalize()
        if self.path is not None:
            self.path = Path(self.path)

    @property
    def dirty(self) -> bool:
        return self.revision != self.saved_revision

    def replace_state(self, state: VibrationalProjectState, *, path: Path | None) -> None:
        state.normalize()
        self.state = state
        self.path = Path(path) if path is not None else None
        self.revision = 0
        self.saved_revision = 0

    def mark_changed(self) -> None:
        self.revision += 1

    def mark_saved(self, path: Path) -> None:
        self.path = Path(path)
        self.saved_revision = self.revision
