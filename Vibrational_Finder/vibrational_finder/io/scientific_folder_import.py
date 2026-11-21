from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ScientificFolderGroup:
    name: str
    directory: Path
    paths: tuple[Path, ...]


def _supported_files(directory: Path, suffixes: set[str], *, recursive: bool) -> tuple[Path, ...]:
    candidates = directory.rglob("*") if recursive else directory.iterdir()
    paths = [path for path in candidates if path.is_file() and path.suffix.lower() in suffixes]
    return tuple(sorted(paths, key=lambda path: path.relative_to(directory).as_posix().casefold()))


def collect_scientific_folder_groups(
    root: str | Path,
    supported_suffixes: Iterable[str],
) -> list[ScientificFolderGroup]:
    root = Path(root)
    if not root.is_dir():
        return []
    suffixes = {
        str(suffix).lower() if str(suffix).startswith(".") else f".{str(suffix).lower()}"
        for suffix in supported_suffixes
    }
    groups: list[ScientificFolderGroup] = []
    root_paths = _supported_files(root, suffixes, recursive=False)
    if root_paths:
        groups.append(ScientificFolderGroup(root.name, root, root_paths))
    for child in sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()):
        child_paths = _supported_files(child, suffixes, recursive=True)
        if child_paths:
            groups.append(ScientificFolderGroup(child.name, child, child_paths))
    return groups


def unique_series_name(name: str, existing_names: Iterable[str]) -> str:
    base = str(name).strip() or "Series"
    occupied = {str(existing).strip().casefold() for existing in existing_names}
    if base.casefold() not in occupied:
        return base
    index = 2
    while f"{base} ({index})".casefold() in occupied:
        index += 1
    return f"{base} ({index})"
