from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol

from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.matching import MatchingOptions, rank_candidates
from vibrational_finder.models import CompoundCandidate, ObservedSpectrum, ReferenceSpectrum, SpectralBand, VibrationalMatchResult
from vibrational_finder.preprocessing import preprocess_spectrum
from vibrational_finder.services.staged_search import ReferenceSearchSource, StagedReferenceSearchService


class CandidateLoadingSource(Protocol):
    name: str

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        ...

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        ...


@dataclass(slots=True)
class CandidateSearchOptions:
    auto_match: bool = False
    shortlist_per_source: int = 80
    fallback_limit: int = 80
    candidate_gate: Callable[[CandidateRecord], bool] | None = None
    matching_options: MatchingOptions = field(default_factory=MatchingOptions)


@dataclass(slots=True)
class CandidateSearchResult:
    matches: list[VibrationalMatchResult] = field(default_factory=list)
    observed_bands: list[SpectralBand] = field(default_factory=list)
    shortlist_records: list[CandidateRecord] = field(default_factory=list)
    source_failures: dict[str, str] = field(default_factory=dict)


class CandidateSearchService:
    """Search references and rank candidates without coupling the workflow to the GUI."""

    def __init__(self, sources: Iterable[ReferenceSearchSource]) -> None:
        self.sources = list(sources)

    def search(
        self,
        query: SourceQuery,
        observed: ObservedSpectrum,
        options: CandidateSearchOptions | None = None,
        *,
        observed_bands: list[SpectralBand] | None = None,
        prefilter_bands: list[SpectralBand] | None = None,
    ) -> CandidateSearchResult:
        options = options or CandidateSearchOptions()
        observed_processed = preprocess_spectrum(observed, options.matching_options.preprocessing)
        observed_bands = observed_bands or detect_bands(observed_processed, options.matching_options.band_detection)
        prefilter_bands = prefilter_bands or detect_bands(
            observed,
            BandDetectionOptions(min_prominence=0.04, max_bands=60, backend="auto", fit_peaks=False),
        )
        if options.auto_match:
            result = StagedReferenceSearchService(self.sources).search_and_rank(
                query,
                observed,
                observed_bands=observed_bands,
                observed_processed=observed_processed,
                matching_options=options.matching_options,
                shortlist_per_source=options.shortlist_per_source,
                fallback_limit=options.fallback_limit,
                candidate_gate=options.candidate_gate,
            )
            return CandidateSearchResult(
                matches=result.matches,
                observed_bands=result.observed_bands,
                shortlist_records=result.shortlist_records,
                source_failures=result.source_failures,
            )
        candidates, source_failures = self._load_manual_candidates(
            query,
            observed,
            prefilter_bands,
            limit=options.fallback_limit,
        )
        if options.candidate_gate is not None:
            candidates = [candidate for candidate in candidates if options.candidate_gate(candidate)]
        return CandidateSearchResult(
            matches=rank_candidates(
                observed,
                candidates,
                options.matching_options,
                observed_processed=observed_processed,
                observed_bands=observed_bands,
            ),
            observed_bands=observed_bands,
            source_failures=source_failures,
        )

    def _load_manual_candidates(
        self,
        query: SourceQuery,
        observed: ObservedSpectrum,
        observed_bands: list[SpectralBand],
        *,
        limit: int,
    ) -> tuple[list[CompoundCandidate], dict[str, str]]:
        candidates: list[CompoundCandidate] = []
        failures: dict[str, str] = {}
        for source in self.sources:
            try:
                load_candidates = getattr(source, "load_candidates", None)
                if callable(load_candidates):
                    candidates.extend(self._call_load_candidates(load_candidates, query, observed, observed_bands, limit))
                    continue
                candidates.extend(self._load_records(source, query, limit))
            except Exception as exc:
                name = str(getattr(source, "name", type(source).__name__))
                failures[name] = f"{type(exc).__name__}: {exc}"
        return candidates, failures

    @staticmethod
    def _call_load_candidates(
        load_candidates,
        query: SourceQuery,
        observed: ObservedSpectrum,
        observed_bands: list[SpectralBand],
        limit: int,
    ) -> list[CompoundCandidate]:
        attempts = (
            lambda: load_candidates(query, observed=observed, observed_bands=observed_bands, limit=limit),
            lambda: load_candidates(query, observed=observed, observed_bands=observed_bands),
            lambda: load_candidates(query),
        )
        for attempt in attempts:
            try:
                return list(attempt())
            except TypeError:
                continue
        return []

    @staticmethod
    def _load_records(source, query: SourceQuery, limit: int) -> list[CompoundCandidate]:
        candidates: list[CompoundCandidate] = []
        for record in list(source.search(query))[:limit]:
            try:
                reference = source.load_spectrum(record)
            except Exception:
                continue
            candidates.append(
                CompoundCandidate(
                    key=record.key,
                    source=record.source,
                    entry_id=record.entry_id,
                    name=record.name,
                    formula=record.formula,
                    kind=record.kind,
                    metadata=dict(record.metadata),
                    reference=reference if reference.x and reference.y else None,
                    band_set=reference.band_set,
                )
            )
        return candidates
