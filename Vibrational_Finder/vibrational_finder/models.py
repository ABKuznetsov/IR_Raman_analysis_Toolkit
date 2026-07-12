from __future__ import annotations

from dataclasses import dataclass, field

from finder_core.models import CandidateRecord, MatchScore, SignalFeature, SignalKind, SignalTrace


@dataclass(slots=True)
class ObservedSpectrum(SignalTrace):
    pass


@dataclass(slots=True)
class SpectralBand(SignalFeature):
    prominence: float = 0.0
    mode: str = ""
    assignment: str = ""
    symmetry: str = ""
    polarization: str = ""
    orientation: str = ""
    source_comment: str = ""
    confidence: float = 1.0


@dataclass(slots=True)
class ReferenceBandSet:
    bands: list[SpectralBand] = field(default_factory=list)
    origin: str = "experimental"
    extraction_method: str = "scipy"
    processing_recipe: dict[str, str | float | int | bool] = field(default_factory=dict)


@dataclass(slots=True)
class ReferenceSpectrum(SignalTrace):
    record: CandidateRecord | None = None
    band_set: ReferenceBandSet | None = None


@dataclass(slots=True)
class CompoundCandidate(CandidateRecord):
    reference: ReferenceSpectrum | None = None
    band_set: ReferenceBandSet | None = None


@dataclass(slots=True)
class VibrationalMatchResult:
    candidate: CompoundCandidate
    score: MatchScore
    observed_bands: list[SpectralBand] = field(default_factory=list)
    reference_bands: list[SpectralBand] = field(default_factory=list)
    unassigned_bands: list[SpectralBand] = field(default_factory=list)
    aligned_reference: ReferenceSpectrum | None = None


@dataclass(slots=True)
class CompoundSpectrumSet:
    key: str
    source: str
    entry_id: str
    name: str = ""
    formula: str = ""
    mineral: str = ""
    space_group: str = ""
    references: dict[SignalKind, ReferenceSpectrum] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def raman_available(self) -> bool:
        return SignalKind.RAMAN in self.references

    @property
    def ftir_available(self) -> bool:
        return SignalKind.FTIR in self.references


@dataclass(slots=True)
class CombinedVibrationalMatchResult:
    compound: CompoundSpectrumSet
    combined_score: float
    raman: VibrationalMatchResult | None = None
    ftir: VibrationalMatchResult | None = None


def spectrum_kind(value: str | SignalKind | None) -> SignalKind:
    if isinstance(value, SignalKind):
        return value
    text = (value or "").strip().lower()
    if text in {"raman", "r"}:
        return SignalKind.RAMAN
    if text in {"ftir", "ir", "infrared"}:
        return SignalKind.FTIR
    return SignalKind.UNKNOWN
