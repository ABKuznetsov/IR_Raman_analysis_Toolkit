from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceViewVisibility:
    profiles: bool
    lines: bool


def reference_view_visibility(mode: str) -> ReferenceViewVisibility:
    normalized = str(mode or "profiles").strip().lower()
    return ReferenceViewVisibility(
        profiles=normalized in {"profiles", "both"},
        lines=normalized in {"lines", "both"},
    )
