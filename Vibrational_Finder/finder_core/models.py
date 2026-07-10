from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SignalKind(str, Enum):
    RAMAN = "raman"
    FTIR = "ftir"
    UNKNOWN = "unknown"


@dataclass(slots=True)
class SignalTrace:
    x: list[float]
    y: list[float]
    kind: SignalKind = SignalKind.UNKNOWN
    name: str = ""
    source_path: str = ""
    x_unit: str = "cm-1"
    y_unit: str = "a.u."


@dataclass(slots=True)
class SignalFeature:
    position: float
    intensity: float
    width: float = 0.0
    assigned_candidate_keys: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CandidateRecord:
    key: str
    source: str
    entry_id: str
    name: str = ""
    formula: str = ""
    kind: SignalKind = SignalKind.UNKNOWN
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class MatchScore:
    combined: float = 0.0
    position: float = 0.0
    intensity: float = 0.0
    correlation: float = 0.0
    coverage: float = 0.0
    matched_features: int = 0
    total_features: int = 0
    x_shift: float = 0.0
