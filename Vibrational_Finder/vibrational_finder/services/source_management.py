from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from vibrational_finder.services.spectroscopy_source_catalog import SpectroscopySourceCatalog


@dataclass(frozen=True, slots=True)
class SourcePackageOption:
    key: str
    label: str
    cached: bool = False


@dataclass(frozen=True, slots=True)
class SourceManagementCapabilities:
    can_update: bool = False
    can_clear: bool = False
    can_build_index: bool = False
    can_clear_index: bool = False
    packages: tuple[SourcePackageOption, ...] = ()


class SpectroscopySourceManager:
    """Normalize cache lifecycle operations exposed by spectroscopy adapters."""

    def __init__(self, catalog: SpectroscopySourceCatalog) -> None:
        self.catalog = catalog

    def packages(self, name: str) -> list[SourcePackageOption]:
        source = self.catalog.source(name)
        raw_packages: list[Any]
        if hasattr(source, "available_archives"):
            raw_packages = list(source.available_archives())
        elif hasattr(source, "available_libraries"):
            raw_packages = list(source.available_libraries())
        else:
            return []
        return [
            SourcePackageOption(
                key=str(item.key),
                label=str(getattr(item, "label", item.key)),
                cached=bool(getattr(item, "is_cached", False)),
            )
            for item in raw_packages
        ]

    def capabilities(self, name: str) -> SourceManagementCapabilities:
        source = self.catalog.source(name)
        packages = tuple(self.packages(name))
        return SourceManagementCapabilities(
            can_update=any(
                hasattr(source, method)
                for method in ("download_archive", "download_library", "download_metadata")
            ),
            can_clear=hasattr(source, "clear"),
            can_build_index=hasattr(source, "build_band_index"),
            can_clear_index=hasattr(source, "clear_band_index"),
            packages=packages,
        )

    def update(self, name: str, package_key: str | None = None) -> object:
        source = self.catalog.source(name)
        packages = self.packages(name)
        if package_key is not None and packages and package_key not in {item.key for item in packages}:
            raise ValueError(f"Unknown package for {name}: {package_key}")
        if hasattr(source, "download_library"):
            return source.download_library(package_key) if package_key is not None else source.download_library()
        if hasattr(source, "download_archive"):
            return source.download_archive(package_key) if package_key is not None else source.download_archive()
        if hasattr(source, "download_metadata"):
            if package_key is not None:
                raise ValueError(f"{name} does not provide selectable packages")
            return source.download_metadata()
        raise RuntimeError(f"{name} does not support cache updates")

    def clear(self, name: str) -> None:
        source = self.catalog.source(name)
        if not hasattr(source, "clear"):
            raise RuntimeError(f"{name} does not support cache clearing")
        source.clear()

    def build_index(self, name: str) -> tuple[int, int]:
        source = self.catalog.source(name)
        if not hasattr(source, "build_band_index"):
            raise RuntimeError(f"{name} does not support line indexing")
        result = source.build_band_index()
        return int(result[0]), int(result[1])

    def clear_index(self, name: str) -> None:
        source = self.catalog.source(name)
        if not hasattr(source, "clear_band_index"):
            raise RuntimeError(f"{name} does not support line-index clearing")
        source.clear_band_index()
