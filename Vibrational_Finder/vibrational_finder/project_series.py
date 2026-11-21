from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable
from uuid import uuid4


def new_project_object_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


@dataclass(slots=True)
class ProjectSeries:
    id: str
    name: str
    spectrum_ids: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, name: str) -> "ProjectSeries":
        return cls(id=new_project_object_id("series"), name=name.strip() or "Series")

    def add_spectrum(self, spectrum_id: str) -> None:
        if spectrum_id not in self.spectrum_ids:
            self.spectrum_ids.append(spectrum_id)

    def remove_spectrum(self, spectrum_id: str) -> None:
        self.spectrum_ids[:] = [item for item in self.spectrum_ids if item != spectrum_id]


def assign_spectrum_to_series(
    series: list[ProjectSeries],
    spectrum_id: str,
    target_series_id: str | None,
) -> None:
    for item in series:
        item.remove_spectrum(spectrum_id)
    if not target_series_id:
        return
    target = next((item for item in series if item.id == target_series_id), None)
    if target is not None:
        target.add_spectrum(spectrum_id)


def prune_series_memberships(series: list[ProjectSeries], valid_ids: Iterable[str]) -> None:
    valid = set(valid_ids)
    claimed: set[str] = set()
    for item in series:
        item.spectrum_ids = [
            spectrum_id
            for spectrum_id in item.spectrum_ids
            if spectrum_id in valid and spectrum_id not in claimed
        ]
        claimed.update(item.spectrum_ids)


def normalized_spectrum_order(preferred_ids: Iterable[str], valid_ids: Iterable[str]) -> list[str]:
    valid_order = list(dict.fromkeys(valid_ids))
    valid = set(valid_order)
    result: list[str] = []
    for spectrum_id in preferred_ids:
        if spectrum_id in valid and spectrum_id not in result:
            result.append(spectrum_id)
    result.extend(spectrum_id for spectrum_id in valid_order if spectrum_id not in result)
    return result
