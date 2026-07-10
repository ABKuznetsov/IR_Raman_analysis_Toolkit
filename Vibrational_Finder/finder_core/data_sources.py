from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from finder_core.models import CandidateRecord, SignalKind, SignalTrace


@dataclass(slots=True)
class SourceQuery:
    text: str = ""
    kind: SignalKind = SignalKind.UNKNOWN
    formula: str = ""


class DataSource(Protocol):
    name: str

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        ...

    def load_spectrum(self, candidate: CandidateRecord) -> SignalTrace:
        ...
