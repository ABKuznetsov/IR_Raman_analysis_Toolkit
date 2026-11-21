from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _frozen_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _frozen_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_frozen_value(item) for item in value)
    return deepcopy(value)


def mutable_processing_value(value: object) -> object:
    """Return a JSON-ready copy of a recursively frozen processing value."""
    if isinstance(value, Mapping):
        return {str(key): mutable_processing_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [mutable_processing_value(item) for item in value]
    return deepcopy(value)


@dataclass(frozen=True, slots=True)
class ProcessingOperation:
    kind: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind).strip().lower())
        object.__setattr__(self, "parameters", _frozen_value(dict(self.parameters)))

    def __deepcopy__(self, _memo: dict[int, object]) -> "ProcessingOperation":
        return self


@dataclass(slots=True)
class SpectrumProcessingState:
    operations: list[ProcessingOperation] = field(default_factory=list)
    revision: int = 0

    def __post_init__(self) -> None:
        self.operations = list(self.operations)
        self.revision = int(self.revision)
        if self.revision < 0:
            raise ValueError("Processing revision cannot be negative.")
