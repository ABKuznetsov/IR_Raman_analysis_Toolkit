from __future__ import annotations

from pathlib import Path
import re

from finder_core.chemistry import formula_contains_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from finder_core.spectral_metadata import spectrum_geometry_metadata
from vibrational_finder.io import guess_spectrum_metadata, load_xy_spectrum, supported_spectrum_extensions
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum


_FORMULA_RE = re.compile(r"(?:[A-Z][a-z]?\d*){2,}")


class FolderLibrarySource:
    name = "Folder Library"

    def __init__(self, folder_path: str | Path, *, library_type: str = "measured", source_name: str = "") -> None:
        self.folder_path = Path(folder_path)
        self.library_type = library_type
        self.source_name = source_name or (self.folder_path.name or self.name)
        self._records = self._index_folder()

    def _index_folder(self) -> list[CandidateRecord]:
        suffixes = set(supported_spectrum_extensions())
        records: list[CandidateRecord] = []
        for index, path in enumerate(sorted(self.folder_path.rglob("*")), start=1):
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            kind = self._kind_from_path(path)
            entry_id = path.stem
            geometry = spectrum_geometry_metadata(path, library_type=self.library_type)
            records.append(
                CandidateRecord(
                    key=f"Folder:{self.folder_path.name}:{path.relative_to(self.folder_path)}:{kind.value}",
                    source=self.source_name,
                    entry_id=entry_id,
                    name=path.stem.replace("_", " "),
                    formula=self._formula_from_name(path.stem),
                    kind=kind,
                    metadata={
                        "path": str(path),
                        "compound_key": f"Folder:{self.folder_path.name}:{entry_id}",
                        "library_type": self.library_type,
                        **geometry,
                    },
                )
            )
        return records

    def _kind_from_path(self, path: Path) -> SignalKind:
        guess = guess_spectrum_metadata(path)
        if guess.kind != SignalKind.UNKNOWN:
            return guess.kind
        text = " ".join(part.lower() for part in path.parts)
        if "ftir" in text or "infrared" in text or re.search(r"(^|[_\-\s])ir($|[_\-\s])", text):
            return SignalKind.FTIR
        return SignalKind.RAMAN

    def _formula_from_name(self, name: str) -> str:
        formulas = _FORMULA_RE.findall(name)
        return " ".join(formulas)

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        text = query.text.strip().lower()
        results: list[CandidateRecord] = []
        for record in self._records:
            if query.kind != SignalKind.UNKNOWN and record.kind not in {query.kind, SignalKind.UNKNOWN}:
                continue
            haystack = " ".join([record.name, record.formula, record.entry_id, record.source]).lower()
            if text and text not in haystack:
                continue
            if query.formula and not formula_contains_elements(record.formula, query.formula):
                continue
            results.append(record)
        return results

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        spectrum = load_xy_spectrum(candidate.metadata.get("path", ""), kind=candidate.kind, name=candidate.name, reference=True)
        if not isinstance(spectrum, ReferenceSpectrum):
            raise TypeError("Expected a reference spectrum")
        spectrum.record = candidate
        return spectrum

    def load_candidates(self, query: SourceQuery | None = None) -> list[CompoundCandidate]:
        query = query or SourceQuery()
        candidates: list[CompoundCandidate] = []
        for record in self.search(query):
            reference = self.load_spectrum(record)
            candidates.append(
                CompoundCandidate(
                    key=record.key,
                    source=record.source,
                    entry_id=record.entry_id,
                    name=record.name,
                    formula=record.formula,
                    kind=record.kind,
                    metadata=dict(record.metadata),
                    reference=reference,
                )
            )
        return candidates
