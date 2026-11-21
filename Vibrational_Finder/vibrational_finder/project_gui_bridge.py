from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from pathlib import Path
from typing import TypeVar

from vibrational_finder.io.project_io import PORTABLE_PROJECT_SUFFIX


_DataclassT = TypeVar("_DataclassT")


def project_save_path(path: str) -> str:
    if Path(path).suffix.lower() == PORTABLE_PROJECT_SUFFIX:
        return path
    return f"{path}{PORTABLE_PROJECT_SUFFIX}"


def project_save_filter() -> str:
    return "IR/Raman Finder projects (*.irff);;All files (*)"


def project_open_filter() -> str:
    return (
        "IR/Raman Finder projects (*.irff);;"
        "Legacy IR/Raman projects (*.irraman.json *.json);;All files (*)"
    )


def dataclass_values(cls: type[_DataclassT], values: dict[str, object]) -> dict[str, object]:
    defaults = cls()
    return {
        field.name: deepcopy(values.get(field.name, getattr(defaults, field.name)))
        for field in fields(cls)
    }
