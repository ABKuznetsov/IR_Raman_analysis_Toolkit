from __future__ import annotations

from dataclasses import dataclass, field

from finder_core.data_sources import DataSource


@dataclass(slots=True)
class SourceRegistry:
    sources: list[DataSource] = field(default_factory=list)

    def register(self, source: DataSource) -> None:
        self.sources.append(source)

    def names(self) -> list[str]:
        return [source.name for source in self.sources]
