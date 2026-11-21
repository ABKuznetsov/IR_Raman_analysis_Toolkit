from __future__ import annotations

import json
from pathlib import Path

from finder_core.cache import app_cache_dir
from finder_core.chemistry import formula_contains_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.models import (
    CompoundCandidate,
    ReferenceBandSet,
    ReferenceSpectrum,
    SpectralBand,
    spectrum_kind,
)
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache
from vibrational_finder.services.user_reference_store import UserReferenceStore


USER_REFERENCE_BAND_RECIPE_VERSION = "user-reference-manual-lines-v1"
USER_LIBRARY_NAME = "User Library"


def user_reference_root() -> Path:
    return app_cache_dir() / "user_references"


def open_user_reference_library() -> EditableReferenceSource:
    root = user_reference_root()
    return EditableReferenceSource(root, cache_root=root, index_cache=False, store=UserReferenceStore(root))


class EditableReferenceSource:
    name = "User References"

    def __init__(
        self, path: str | Path, cache_root: str | Path | None = None, *,
        index_cache: bool = True, store: UserReferenceStore | None = None,
    ) -> None:
        self.path = Path(path)
        self.store = store
        self.files = sorted(self.path.glob("*.vsref")) if self.path.is_dir() else [self.path]
        default_cache_root = self.path if self.path.is_dir() else self.path.parent
        self._cache_root = Path(cache_root) if cache_root is not None else default_cache_root
        self._reference_cache: ReferenceSpectrumCache | None = None
        self._payloads: dict[str, dict] = {}
        self._records = self._load_records()
        if index_cache:
            self.index_records()

    @property
    def reference_cache(self) -> ReferenceSpectrumCache:
        if self._reference_cache is None:
            self._reference_cache = ReferenceSpectrumCache(self._cache_root)
        return self._reference_cache

    def _card_payloads(self):
        if self.store is not None:
            for card_id, payload in self.store.cards().items():
                legacy_path = Path(card_id)
                if legacy_path.is_absolute():
                    yield card_id, legacy_path, legacy_path.stem, payload
                else:
                    yield card_id, self.store.path, card_id, payload
            return
        for path in self.files:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                yield str(path.resolve()), path, path.stem, payload

    def _load_records(self) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        for card_id, path, fallback, payload in self._card_payloads():
            metadata = dict(payload.get("metadata") or {})
            kind = spectrum_kind(payload.get("kind") or metadata.get("method"))
            entry_id = str(payload.get("entry_id") or fallback)
            key = f"UserReference:{card_id}:{kind.value}"
            record = CandidateRecord(
                key=key,
                source=self.name,
                entry_id=entry_id,
                name=str(metadata.get("name") or "Untitled reference"),
                formula=str(metadata.get("formula") or ""),
                kind=kind,
                metadata={
                    **{str(k): str(v) for k, v in metadata.items() if v is not None},
                    "original_source": str(payload.get("source") or self.name),
                    "path": str(path),
                    "origin": str(metadata.get("origin") or "experimental"),
                    "library_type": str(metadata.get("origin") or "experimental"),
                    "compound_key": str(payload.get("compound_key") or f"UserReference:{entry_id}"),
                },
            )
            self._payloads[key] = payload
            records.append(record)
        return records

    def index_records(self, *, clear_existing: bool = False) -> tuple[int, int]:
        if clear_existing:
            self.reference_cache.clear_source(self.name)
        self.reference_cache.upsert_records(self._records)
        items: list[tuple[str, ReferenceBandSet]] = []
        for record in self._records:
            band_set = self._band_set(record)
            if band_set.bands:
                items.append((record.key, band_set))
        self.reference_cache.upsert_band_sets(items, USER_REFERENCE_BAND_RECIPE_VERSION)
        return len(self._records), sum(len(band_set.bands) for _key, band_set in items)

    def clear_sql_index(self) -> None:
        self.reference_cache.clear_source(self.name)

    def indexed_record_count(self) -> int:
        return self.reference_cache.indexed_count(source=self.name)

    def indexed_band_count(self) -> int:
        return self.reference_cache.indexed_band_count(self.name, USER_REFERENCE_BAND_RECIPE_VERSION)

    def indexed_band_reference_count(self) -> int:
        return self.reference_cache.indexed_band_reference_count(self.name, USER_REFERENCE_BAND_RECIPE_VERSION)

    def sql_size_bytes(self) -> int:
        return self.reference_cache.size_bytes()

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

    def search_by_bands(
        self,
        query: SourceQuery,
        observed: ReferenceSpectrum,
        *,
        limit: int = 80,
        observed_bands: list[SpectralBand] | None = None,
    ) -> list[CandidateRecord]:
        if observed_bands is None:
            observed_bands = detect_bands(
                observed,
                BandDetectionOptions(min_prominence=0.04, max_bands=60, backend="auto", fit_peaks=False),
            )
        # Stored cards are authoritative. In-memory shortlisting uses the
        # current bands, including edits not reflected in a legacy index.
        if self.store is not None:
            strongest = sorted(observed_bands, key=lambda band: band.intensity, reverse=True)[:24]
            matches = [record for record in self.search(query) if query.allows_formula(record.formula)]

            def overlap(record: CandidateRecord) -> int:
                bands = self._band_set(record).bands
                return sum(any(abs(item.position - band.position) <= 20.0 for band in bands) for item in strongest)

            return sorted(matches, key=lambda record: -overlap(record))[:limit]
        strongest_observed = sorted(observed_bands, key=lambda band: band.intensity, reverse=True)[:24]
        records = self.reference_cache.search_by_bands(
            query,
            [band.position for band in strongest_observed],
            tolerance_cm1=20.0,
            sources=[self.name],
            recipe_version=USER_REFERENCE_BAND_RECIPE_VERSION,
            limit=max(limit * 4, 200),
        )
        local_keys = {record.key for record in self._records}
        records = [record for record in records if record.key in local_keys]
        if len(records) < limit:
            selected = {record.key for record in records}
            records.extend(record for record in self.search(query) if record.key not in selected)
        return records[:limit]

    def _band_set(self, record: CandidateRecord) -> ReferenceBandSet:
        payload = self._payloads[record.key]
        bands: list[SpectralBand] = []
        for item in payload.get("bands") or []:
            position = item.get("position_cm1")
            if position in {None, ""}:
                continue
            bands.append(
                SpectralBand(
                    position=float(position),
                    intensity=float(item.get("intensity") or 0.0),
                    width=float(item.get("fwhm_cm1") or 0.0),
                    mode=str(item.get("mode") or ""),
                    assignment=str(item.get("assignment") or ""),
                    symmetry=str(item.get("symmetry") or ""),
                    polarization=str(item.get("polarization") or ""),
                    orientation=str(item.get("orientation") or ""),
                    source_comment=str(item.get("comment") or ""),
                    confidence=float(item.get("confidence_value") or 1.0),
                )
            )
        scale = max((band.intensity for band in bands), default=0.0)
        if scale > 0:
            for band in bands:
                band.intensity /= scale
        elif bands:
            for band in bands:
                band.intensity = 1.0
        return ReferenceBandSet(
            bands=sorted(bands, key=lambda band: band.position),
            origin=str(record.metadata.get("origin") or "experimental"),
            extraction_method="manual/reference-editor",
        )

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        payload = self._payloads[candidate.key]
        profile = payload.get("profile") or {}
        spectrum = ReferenceSpectrum(
            x=[float(value) for value in profile.get("x") or []],
            y=[float(value) for value in profile.get("y") or []],
            kind=candidate.kind,
            name=candidate.name,
            source_path=str(candidate.metadata.get("path") or ""),
            record=candidate,
            band_set=self._band_set(candidate),
        )
        return spectrum

    def load_candidates(
        self,
        query: SourceQuery | None = None,
        *,
        observed: ReferenceSpectrum | None = None,
        observed_bands: list[SpectralBand] | None = None,
        limit: int = 80,
    ) -> list[CompoundCandidate]:
        query = query or SourceQuery()
        records = (
            self.search_by_bands(query, observed, limit=limit, observed_bands=observed_bands)
            if observed is not None and (self.store is not None or self.indexed_band_count())
            else self.search(query)
        )
        candidates: list[CompoundCandidate] = []
        for record in records:
            spectrum = self.load_spectrum(record)
            has_profile = bool(spectrum.x and spectrum.y)
            candidates.append(
                CompoundCandidate(
                    key=record.key,
                    source=record.source,
                    entry_id=record.entry_id,
                    name=record.name,
                    formula=record.formula,
                    kind=record.kind,
                    metadata=dict(record.metadata),
                    reference=spectrum if has_profile else None,
                    band_set=spectrum.band_set,
                )
            )
        return candidates


def write_editable_reference(path: str | Path, payload: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
