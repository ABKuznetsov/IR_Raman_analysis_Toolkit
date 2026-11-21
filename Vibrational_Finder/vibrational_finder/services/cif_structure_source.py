from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from finder_core.chemistry import formula_contains_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum


_FORMULA_TOKEN_RE = re.compile(r"(?:[A-Z][a-z]?\d*)+")


@dataclass(slots=True)
class BandHint:
    position: float
    intensity: float
    width: float
    assignment: str


class CifStructureSource:
    name = "CIF IR hints"

    def __init__(self, folder_path: str | Path) -> None:
        self.folder_path = Path(folder_path)
        self._single_file = self.folder_path if self.folder_path.is_file() else None
        self._records = self._index_folder()

    def _index_folder(self) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        if self._single_file is not None:
            files = [self._single_file]
            root = self._single_file.parent
        else:
            files = sorted(self.folder_path.rglob("*.cif"))
            root = self.folder_path
        for path in files:
            formula = self._formula_from_cif(path)
            name = self._name_from_cif(path)
            records.append(
                CandidateRecord(
                    key=f"CIF:{path.relative_to(root)}",
                    source=self.name,
                    entry_id=path.stem,
                    name=name or path.stem.replace("_", " "),
                    formula=formula,
                    kind=SignalKind.FTIR,
                    metadata={
                        "path": str(path),
                        "compound_key": f"CIF:{path.stem}",
                        "library_type": "cif_ir_hints",
                        "quality": "weak structural hint",
                        "orientation": "not applicable",
                        "polarization": "not applicable",
                        "geometry": "not applicable",
                    },
                )
            )
        return records

    def _name_from_cif(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key in ("_chemical_name_mineral", "_chemical_name_common", "_chemical_name_systematic"):
            match = re.search(rf"^{re.escape(key)}\s+(.+)$", text, flags=re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip().strip("'\"")
        return ""

    def _formula_from_cif(self, path: Path) -> str:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for key in ("_chemical_formula_sum", "_chemical_formula_structural", "_chemical_formula_moiety"):
            match = re.search(rf"^{re.escape(key)}\s+(.+)$", text, flags=re.MULTILINE | re.IGNORECASE)
            if match:
                return self._clean_formula(match.group(1))
        formulas = _FORMULA_TOKEN_RE.findall(path.stem)
        return " ".join(formulas)

    def _clean_formula(self, value: str) -> str:
        value = value.strip().strip("'\"")
        value = re.sub(r"[\[\](),]", " ", value)
        return " ".join(value.split())

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        text = query.text.strip().lower()
        results: list[CandidateRecord] = []
        for record in self._records:
            if query.kind not in {SignalKind.UNKNOWN, SignalKind.FTIR}:
                continue
            haystack = " ".join([record.name, record.formula, record.entry_id, record.source]).lower()
            if text and text not in haystack:
                continue
            if query.formula and not formula_contains_elements(record.formula, query.formula):
                continue
            results.append(record)
        return results

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        hints = self._band_hints(candidate.formula)
        x = np.linspace(80.0, 3800.0, 2400)
        y = np.zeros_like(x)
        assignments: list[str] = []
        for hint in hints:
            y += hint.intensity * np.exp(-0.5 * ((x - hint.position) / hint.width) ** 2)
            assignments.append(f"{hint.position:.0f} cm-1: {hint.assignment}")
        if float(np.max(y)) > 0:
            y = y / float(np.max(y))
        spectrum = ReferenceSpectrum(
            x=x.tolist(),
            y=y.tolist(),
            kind=SignalKind.FTIR,
            name=f"{candidate.name} CIF IR hints",
            source_path=candidate.metadata.get("path", ""),
            record=candidate,
        )
        spectrum.record.metadata["assignments"] = "; ".join(assignments)
        return spectrum

    def _band_hints(self, formula: str) -> list[BandHint]:
        elements = set(re.findall(r"[A-Z][a-z]?", formula))
        hints: list[BandHint] = []
        if {"Si", "O"}.issubset(elements):
            hints.extend([
                BandHint(465, 0.55, 28, "Si-O bending"),
                BandHint(800, 0.45, 36, "Si-O symmetric stretching"),
                BandHint(1050, 0.85, 58, "Si-O stretching"),
            ])
        if {"Al", "O"}.issubset(elements):
            hints.extend([
                BandHint(520, 0.35, 36, "Al-O lattice/bending"),
                BandHint(750, 0.30, 45, "Al-O stretching"),
            ])
        if {"C", "O"}.issubset(elements):
            hints.extend([
                BandHint(710, 0.45, 24, "CO3 bending"),
                BandHint(875, 0.55, 28, "CO3 out-of-plane bending"),
                BandHint(1420, 0.90, 70, "CO3 stretching"),
            ])
        if {"S", "O"}.issubset(elements):
            hints.extend([
                BandHint(610, 0.45, 30, "SO4 bending"),
                BandHint(1110, 0.85, 62, "SO4 stretching"),
            ])
        if {"P", "O"}.issubset(elements):
            hints.extend([
                BandHint(575, 0.45, 35, "PO4 bending"),
                BandHint(1020, 0.85, 55, "PO4 stretching"),
            ])
        if {"B", "O"}.issubset(elements):
            hints.extend([
                BandHint(720, 0.40, 38, "B-O bending"),
                BandHint(1350, 0.70, 70, "B-O stretching"),
            ])
        if "H" in elements and "O" in elements:
            hints.extend([
                BandHint(1630, 0.45, 55, "H2O bending"),
                BandHint(3450, 0.75, 130, "OH/H2O stretching"),
            ])
        if not hints:
            hints.append(BandHint(500, 0.25, 120, "low-confidence lattice modes"))
        return hints

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
