from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from finder_core.chemistry import parse_formula_elements
from finder_core.models import CandidateRecord, SignalKind, SignalTrace


@dataclass(slots=True)
class SourceQuery:
    text: str = ""
    kind: SignalKind = SignalKind.UNKNOWN
    formula: str = ""
    required_elements: frozenset[str] = frozenset()
    excluded_elements: frozenset[str] = frozenset()

    def allows_formula(self, formula: str) -> bool:
        if not (self.required_elements or self.excluded_elements):
            return True
        elements = parse_formula_elements(formula)
        return bool(elements) and self.required_elements.issubset(elements) and self.excluded_elements.isdisjoint(elements)


class DataSource(Protocol):
    name: str

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        ...

    def load_spectrum(self, candidate: CandidateRecord) -> SignalTrace:
        ...
