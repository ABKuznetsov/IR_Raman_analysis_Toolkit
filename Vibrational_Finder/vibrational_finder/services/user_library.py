from __future__ import annotations

import csv
from pathlib import Path

from finder_core.data_sources import SourceQuery
from finder_core.chemistry import formula_contains_elements
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.io.xy_loader import load_xy_spectrum
from vibrational_finder.models import CompoundCandidate, CompoundSpectrumSet, ReferenceSpectrum, spectrum_kind


class UserLibrarySource:
    name = "User Library"

    def __init__(self, manifest_path: str | Path) -> None:
        self.manifest_path = Path(manifest_path)
        self.base_dir = self.manifest_path.parent
        self._records = self._load_manifest()

    def _load_manifest(self) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        with self.manifest_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=1):
                path = (row.get("path") or "").strip()
                source = (row.get("source") or self.name).strip()
                entry_id = (row.get("entry_id") or row.get("id") or f"entry-{index}").strip()
                kind = spectrum_kind(row.get("kind"))
                compound_key = (row.get("compound_key") or f"{source}:{entry_id}").strip()
                key = f"{compound_key}:{kind.value}"
                records.append(
                    CandidateRecord(
                        key=key,
                        source=source,
                        entry_id=entry_id,
                        name=(row.get("name") or "").strip(),
                        formula=(row.get("formula") or "").strip(),
                        kind=kind,
                        metadata={
                            "path": path,
                            "compound_key": compound_key,
                            "mineral": (row.get("mineral") or "").strip(),
                            "space_group": (row.get("space_group") or "").strip(),
                        },
                    )
                )
        return records

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
        raw_path = candidate.metadata.get("path", "")
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.base_dir / path
        spectrum = load_xy_spectrum(path, kind=candidate.kind, name=candidate.name, reference=True)
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

    def load_compound_sets(self, query: SourceQuery | None = None) -> list[CompoundSpectrumSet]:
        query = query or SourceQuery()
        grouped: dict[str, CompoundSpectrumSet] = {}
        for record in self.search(query):
            compound_key = record.metadata.get("compound_key", f"{record.source}:{record.entry_id}")
            compound = grouped.get(compound_key)
            if compound is None:
                compound = CompoundSpectrumSet(
                    key=compound_key,
                    source=record.source,
                    entry_id=record.entry_id,
                    name=record.name,
                    formula=record.formula,
                    mineral=record.metadata.get("mineral", ""),
                    space_group=record.metadata.get("space_group", ""),
                    metadata=dict(record.metadata),
                )
                grouped[compound_key] = compound
            reference = self.load_spectrum(record)
            compound.references[record.kind] = reference
        return list(grouped.values())
