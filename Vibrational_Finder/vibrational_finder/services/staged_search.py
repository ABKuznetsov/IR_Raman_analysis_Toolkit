from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalTrace
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.matching import MatchingOptions, rank_candidates
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum, SpectralBand, VibrationalMatchResult


class ReferenceSearchSource(Protocol):
    name: str

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        ...

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        ...


@dataclass(slots=True)
class StagedReferenceSearchResult:
    shortlist_records: list[CandidateRecord] = field(default_factory=list)
    matches: list[VibrationalMatchResult] = field(default_factory=list)
    observed_bands: list[SpectralBand] = field(default_factory=list)
    source_failures: dict[str, str] = field(default_factory=dict)


class StagedReferenceSearchService:
    """Fast local shortlist first, expensive spectral scoring second."""

    def __init__(self, sources: Iterable[ReferenceSearchSource]) -> None:
        self.sources = list(sources)
        self._record_sources: dict[str, ReferenceSearchSource] = {}
        self._source_failures: dict[str, str] = {}

    def search_and_rank(
        self,
        query: SourceQuery,
        observed: SignalTrace,
        *,
        observed_bands: list[SpectralBand] | None = None,
        observed_processed: SignalTrace | None = None,
        matching_options: MatchingOptions | None = None,
        shortlist_per_source: int = 80,
        fallback_limit: int = 80,
        candidate_gate: Callable[[CandidateRecord], bool] | None = None,
    ) -> StagedReferenceSearchResult:
        matching_options = matching_options or MatchingOptions()
        observed_bands = observed_bands or detect_bands(
            observed,
            BandDetectionOptions(min_prominence=0.04, max_bands=60, backend="auto", fit_peaks=False),
        )
        shortlist = self.shortlist_records(
            query,
            observed_bands,
            shortlist_per_source=shortlist_per_source,
            fallback_limit=fallback_limit,
            candidate_gate=candidate_gate,
        )
        candidates = self.load_candidates(shortlist)
        matches = rank_candidates(
            observed,
            candidates,
            matching_options,
            observed_processed=observed_processed,
            observed_bands=observed_bands,
        )
        return StagedReferenceSearchResult(
            shortlist_records=shortlist,
            matches=matches,
            observed_bands=observed_bands,
            source_failures=dict(self._source_failures),
        )

    def shortlist_records(
        self,
        query: SourceQuery,
        observed_bands: list[SpectralBand],
        *,
        shortlist_per_source: int = 80,
        fallback_limit: int = 80,
        candidate_gate: Callable[[CandidateRecord], bool] | None = None,
    ) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        self._record_sources.clear()
        self._source_failures.clear()
        for source in self.sources:
            try:
                source_records = self._source_shortlist(
                    source, query, observed_bands, limit=shortlist_per_source, fallback_limit=fallback_limit,
                )
            except Exception as exc:
                self._record_failure(source, exc)
                continue
            if candidate_gate is not None:
                source_records = [record for record in source_records if candidate_gate(record)]
            for record in source_records:
                self._record_sources[record.key] = source
            records.extend(source_records)
        return self._dedupe_records(records)

    def load_candidates(self, records: list[CandidateRecord]) -> list[CompoundCandidate]:
        sources_by_name = {source.name: source for source in self.sources}
        candidates: list[CompoundCandidate] = []
        for record in records:
            source = self._record_sources.get(record.key) or sources_by_name.get(record.source)
            if source is None:
                continue
            try:
                reference = source.load_spectrum(record)
            except Exception as exc:
                self._record_failure(source, exc)
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

    def _source_shortlist(
        self,
        source: ReferenceSearchSource,
        query: SourceQuery,
        observed_bands: list[SpectralBand],
        *,
        limit: int,
        fallback_limit: int,
    ) -> list[CandidateRecord]:
        search_by_bands = getattr(source, "search_by_bands", None)
        if callable(search_by_bands):
            try:
                return list(
                    search_by_bands(
                        query,
                        None,
                        limit=limit,
                        observed_bands=observed_bands,
                    )
                )[:limit]
            except TypeError:
                pass
        cache = getattr(source, "reference_cache", None)
        recipe_version = str(getattr(source, "band_recipe_version", ""))
        indexed_band_count = getattr(source, "indexed_band_count", None)
        has_index = False
        if callable(indexed_band_count):
            try:
                has_index = int(indexed_band_count()) > 0
            except Exception:
                has_index = False
        if cache is not None and has_index:
            strongest = sorted(observed_bands, key=lambda band: band.intensity, reverse=True)[:24]
            try:
                return cache.search_by_bands(
                    query,
                    [band.position for band in strongest],
                    tolerance_cm1=20.0,
                    sources=[source.name],
                    recipe_version=recipe_version,
                    limit=limit,
                )
            except Exception:
                pass
        return [record for record in source.search(query) if query.allows_formula(record.formula)][:fallback_limit]

    def _record_failure(self, source: ReferenceSearchSource, exc: Exception) -> None:
        self._source_failures.setdefault(source.name, f"{type(exc).__name__}: {exc}")

    @staticmethod
    def _dedupe_records(records: list[CandidateRecord]) -> list[CandidateRecord]:
        deduped: list[CandidateRecord] = []
        seen: set[str] = set()
        for record in records:
            if record.key in seen:
                continue
            seen.add(record.key)
            deduped.append(record)
        return deduped
