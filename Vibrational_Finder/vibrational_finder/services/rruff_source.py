from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import ssl
import urllib.request
import zipfile

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from finder_core.spectral_metadata import spectrum_geometry_metadata
from vibrational_finder.models import CompoundCandidate, ReferenceBandSet, ReferenceSpectrum, SpectralBand
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands, extract_reference_band_set
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache


RRUFF_RAMAN_ARCHIVES = {
    "excellent_unoriented": "https://www.rruff.net/zipped_data_files/raman/excellent_unoriented.zip",
    "excellent_oriented": "https://www.rruff.net/zipped_data_files/raman/excellent_oriented.zip",
    "fair_unoriented": "https://www.rruff.net/zipped_data_files/raman/fair_unoriented.zip",
    "fair_oriented": "https://www.rruff.net/zipped_data_files/raman/fair_oriented.zip",
    "poor_unoriented": "https://www.rruff.net/zipped_data_files/raman/poor_unoriented.zip",
    "unrated_unoriented": "https://www.rruff.net/zipped_data_files/raman/unrated_unoriented.zip",
    "unrated_oriented": "https://www.rruff.net/zipped_data_files/raman/unrated_oriented.zip",
    "lr_raman": "https://www.rruff.net/zipped_data_files/raman/LR-Raman.zip",
}

RRUFF_IR_ARCHIVES = {
    "raw": "https://www.rruff.net/zipped_data_files/infrared/RAW.zip",
}

RRUFF_BAND_RECIPE_VERSION = "arpls-savgol-ramanchada2-topo-normalized-v1"


@dataclass(slots=True)
class RruffArchiveInfo:
    key: str
    url: str
    kind: SignalKind
    path: Path

    @property
    def label(self) -> str:
        method = "Raman" if self.kind == SignalKind.RAMAN else "FTIR"
        return f"{method} {self.key.replace('_', ' ')}"

    @property
    def is_cached(self) -> bool:
        return self.path.exists()


class RruffSource:
    name = "RRUFF"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / "rruff"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.reference_cache = ReferenceSpectrumCache(self.cache_root)
        self._records: list[CandidateRecord] = []
        self._archive_by_record_key: dict[str, Path] = {}
        self.refresh_index()

    def available_archives(self) -> list[RruffArchiveInfo]:
        infos: list[RruffArchiveInfo] = []
        for key, url in RRUFF_RAMAN_ARCHIVES.items():
            infos.append(RruffArchiveInfo(key=key, url=url, kind=SignalKind.RAMAN, path=self.cache_root / f"{key}.zip"))
        for key, url in RRUFF_IR_ARCHIVES.items():
            infos.append(RruffArchiveInfo(key=f"ir_{key}", url=url, kind=SignalKind.FTIR, path=self.cache_root / f"ir_{key}.zip"))
        return infos

    def cached_archive_keys(self) -> list[str]:
        return [info.key for info in self.available_archives() if info.is_cached]

    def download_archive(self, key: str = "fair_oriented") -> Path:
        archives = {info.key: info for info in self.available_archives()}
        if key not in archives:
            raise ValueError(f"Unknown RRUFF archive: {key}")
        info = archives[key]
        target = info.path
        target.parent.mkdir(parents=True, exist_ok=True)
        request_kwargs = {"timeout": 60}
        context = self._ssl_context()
        if context is not None:
            request_kwargs["context"] = context
        tmp_path = target.with_suffix(target.suffix + ".part")
        with urllib.request.urlopen(info.url, **request_kwargs) as response:
            with tmp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        tmp_path.replace(target)
        self.refresh_index(force=True)
        return target

    def indexed_count(self, kind: SignalKind | None = None) -> int:
        if kind is None or kind == SignalKind.UNKNOWN:
            return len(self._records)
        return sum(1 for record in self._records if record.kind == kind)

    def status_row(self) -> list[str]:
        cached = self.cached_archive_keys()
        size = sum(info.path.stat().st_size for info in self.available_archives() if info.path.exists())
        return [
            "RRUFF",
            "Indexed" if self._records else "Empty",
            (
                f"{self.indexed_count(SignalKind.RAMAN)} Raman, "
                f"{self.indexed_count(SignalKind.FTIR)} FTIR; "
                f"{self.indexed_band_count()} line-indexed; "
                f"{', '.join(cached) if cached else 'no archives cached'}"
            ),
            str(self.indexed_count()),
            f"{size / (1024 * 1024):.1f} MB",
            str(self.cache_root),
        ]

    def _ssl_context(self):
        try:
            import certifi
        except Exception:
            return None
        return ssl.create_default_context(cafile=certifi.where())

    def refresh_index(self, *, force: bool = False) -> None:
        self._records = []
        self._archive_by_record_key = {}
        cached_archives = {info.path.stem: info.path for info in self.available_archives() if info.path.exists()}
        cached_records = self.reference_cache.search(SourceQuery(), sources=[self.name], limit=100000)
        indexed_archives = {str(record.metadata.get("archive", "")) for record in cached_records}
        indexed_archives.discard("")
        if not force and cached_records and indexed_archives == set(cached_archives):
            self._records = cached_records
            for record in cached_records:
                archive_key = str(record.metadata.get("archive", ""))
                if archive_key in cached_archives:
                    self._archive_by_record_key[record.key] = cached_archives[archive_key]
            return
        if not cached_archives:
            self.reference_cache.clear_source(self.name)
            return
        for removed_archive in indexed_archives - set(cached_archives):
            self.reference_cache.clear_archive(removed_archive)
        for archive_key, archive_path in cached_archives.items():
            info = next(info for info in self.available_archives() if info.path == archive_path)
            self._index_archive(info.path, info.kind)
        self.reference_cache.upsert_records(self._records)

    def _index_archive(self, archive_path: Path, kind: SignalKind) -> None:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                names = [name for name in archive.namelist() if self._looks_like_spectrum(name)]
                for name in names:
                    text = self._member_header_text(archive, name)
                    record = self._record_from_member(name, kind, archive_path.stem, text)
                    self._records.append(record)
                    self._archive_by_record_key[record.key] = archive_path
        except zipfile.BadZipFile:
            return

    def _looks_like_spectrum(self, name: str) -> bool:
        lower = name.lower()
        return not lower.endswith("/") and lower.endswith((".txt", ".csv", ".dat", ".xy", ".asc", ".tsv", ".jdx", ".dx"))

    def _record_from_member(
        self,
        member_name: str,
        kind: SignalKind,
        archive_key: str = "",
        header_text: str = "",
    ) -> CandidateRecord:
        stem = Path(member_name).stem
        parts = [part.strip() for part in re.split(r"__+", stem) if part.strip()]
        name = self._metadata_value(header_text, ["names", "name", "mineral"]) or (parts[0].replace("_", " ") if parts else stem.replace("_", " "))
        entry_id = self._metadata_value(header_text, ["rruffid", "rruff id"]) or next((part for part in parts if re.match(r"R\d+", part, re.IGNORECASE)), stem)
        formula = self._clean_rruff_formula(
            self._metadata_value(header_text, ["ideal chemistry", "chemistry", "measured chemistry"])
        )
        description = self._metadata_value(header_text, ["description", "locality", "status"]) or (
            " | ".join(parts[2:]) if len(parts) > 2 else stem
        )
        key = f"RRUFF:{entry_id}:{kind.value}:{member_name}"
        geometry = spectrum_geometry_metadata(f"{archive_key} {member_name}")
        laser_nm = self._metadata_value(header_text, ["raman wavelength", "laser wavelength"])
        return CandidateRecord(
            key=key,
            source="RRUFF",
            entry_id=entry_id,
            name=name,
            formula=formula,
            kind=kind,
            metadata={
                "member": member_name,
                "description": description,
                "path": member_name,
                "compound_key": f"RRUFF:{entry_id}",
                "archive": archive_key,
                "laser_nm": laser_nm,
                **geometry,
            },
        )

    def _member_header_text(self, archive: zipfile.ZipFile, member_name: str, byte_limit: int = 16000) -> str:
        try:
            with archive.open(member_name) as handle:
                return handle.read(byte_limit).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def _metadata_value(self, text: str, keys: list[str]) -> str:
        if not text:
            return ""
        wanted = {key.lower(): key for key in keys}
        for line in text.splitlines():
            cleaned = line.strip().lstrip("#;!/").strip()
            if not cleaned or "=" not in cleaned and ":" not in cleaned:
                continue
            separator = "=" if "=" in cleaned else ":"
            key, value = cleaned.split(separator, 1)
            normalized_key = key.strip().lower()
            if normalized_key in wanted:
                return value.strip()
        return ""

    def _clean_rruff_formula(self, formula: str) -> str:
        cleaned = formula.strip()
        if not cleaned:
            return ""
        cleaned = cleaned.replace("_", "")
        cleaned = re.sub(r"\s+", "", cleaned)
        return cleaned

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        return self.reference_cache.search(query, sources=[self.name])

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        archive_path = self._archive_by_record_key.get(candidate.key)
        member = candidate.metadata.get("member", "")
        if archive_path is None or not member:
            raise FileNotFoundError(f"RRUFF spectrum is not indexed: {candidate.key}")
        with zipfile.ZipFile(archive_path) as archive:
            text = archive.read(member).decode("utf-8", errors="ignore")
        x, y = self._parse_xy_text(text)
        spectrum = ReferenceSpectrum(
            x=x,
            y=y,
            kind=candidate.kind,
            name=candidate.name,
            source_path=f"{archive_path}:{member}",
            record=candidate,
            band_set=self.reference_cache.load_band_set(candidate.key, RRUFF_BAND_RECIPE_VERSION),
        )
        return spectrum

    def build_band_index(self) -> tuple[int, int]:
        from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum

        indexed_keys = self.reference_cache.indexed_band_keys(self.name, RRUFF_BAND_RECIPE_VERSION)
        indexed = 0
        skipped = 0
        pending = []
        records_by_archive: dict[Path, list[CandidateRecord]] = {}
        for record in self._records:
            if record.key not in indexed_keys and record.key in self._archive_by_record_key:
                records_by_archive.setdefault(self._archive_by_record_key[record.key], []).append(record)
        preprocessing_options = PreprocessingOptions(
            baseline_method="arpls",
            smoothing_window=7,
            smoothing_method="savgol",
            despike=True,
            normalize="max",
        )
        detection_options = BandDetectionOptions(
            min_prominence=0.04,
            min_distance_cm1=8.0,
            max_bands=80,
            backend="auto",
            fit_peaks=False,
        )
        for archive_path, records in records_by_archive.items():
            try:
                archive = zipfile.ZipFile(archive_path)
            except zipfile.BadZipFile:
                skipped += len(records)
                continue
            with archive:
                for record in records:
                    try:
                        member = record.metadata.get("member", "")
                        text = archive.read(member).decode("utf-8", errors="ignore")
                        x, y = self._parse_xy_text(text)
                        reference = ReferenceSpectrum(x=x, y=y, kind=record.kind, name=record.name, record=record)
                        processed = preprocess_spectrum(reference, preprocessing_options)
                        band_set = extract_reference_band_set(
                            processed,
                            detection_options,
                            origin="experimental",
                        )
                        band_set.processing_recipe.update(
                            {
                                "baseline_method": "arpls",
                                "smoothing_method": "savgol",
                                "smoothing_window": 7,
                                "despike": True,
                                "normalization": "max",
                            }
                        )
                        if not band_set.bands:
                            skipped += 1
                            continue
                        pending.append((record.key, band_set))
                        if len(pending) >= 100:
                            self.reference_cache.upsert_band_sets(pending, RRUFF_BAND_RECIPE_VERSION)
                            pending.clear()
                        indexed += 1
                    except Exception:
                        skipped += 1
        if pending:
            self.reference_cache.upsert_band_sets(pending, RRUFF_BAND_RECIPE_VERSION)
        return indexed, skipped

    def indexed_band_count(self) -> int:
        return self.reference_cache.indexed_band_reference_count(self.name, RRUFF_BAND_RECIPE_VERSION)

    def clear_band_index(self) -> None:
        self.reference_cache.clear_band_index(self.name)

    def load_candidates(
        self,
        query: SourceQuery | None = None,
        *,
        observed=None,
        observed_bands: list[SpectralBand] | None = None,
        limit: int = 80,
    ) -> list[CompoundCandidate]:
        query = query or SourceQuery()
        records: list[CandidateRecord]
        if observed is not None and self.indexed_band_count() > 0:
            if observed_bands is None:
                observed_bands = detect_bands(
                    observed,
                    BandDetectionOptions(min_prominence=0.04, max_bands=60, backend="auto", fit_peaks=False),
                )
            strongest_observed = sorted(observed_bands, key=lambda band: band.intensity, reverse=True)[:24]
            records = self.reference_cache.search_by_bands(
                query,
                [band.position for band in strongest_observed],
                tolerance_cm1=20.0,
                sources=[self.name],
                recipe_version=RRUFF_BAND_RECIPE_VERSION,
                limit=max(limit * 5, 300),
            )
            if len(records) < max(limit * 5, 300):
                selected_keys = {record.key for record in records}
                records.extend(
                    record
                    for record in self.search(query)
                    if record.key not in selected_keys
                )
                records = records[: max(limit * 5, 300)]
            band_sets = self.reference_cache.load_band_sets(
                [record.key for record in records],
                RRUFF_BAND_RECIPE_VERSION,
            )
            records.sort(
                key=lambda record: self._band_prefilter_score(
                    strongest_observed,
                    band_sets.get(record.key),
                ),
                reverse=True,
            )
            records = records[: min(limit, 40)]
        else:
            records = self.search(query)[:limit]
        loaded_spectra = self._load_spectra(records)
        candidates: list[CompoundCandidate] = []
        for record in records:
            reference = loaded_spectra.get(record.key)
            if reference is None:
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
                    reference=reference,
                    band_set=reference.band_set,
                )
            )
        return candidates

    def _load_spectra(self, records: list[CandidateRecord]) -> dict[str, ReferenceSpectrum]:
        band_sets = self.reference_cache.load_band_sets(
            [record.key for record in records],
            RRUFF_BAND_RECIPE_VERSION,
        )
        records_by_archive: dict[Path, list[CandidateRecord]] = {}
        for record in records:
            archive_path = self._archive_by_record_key.get(record.key)
            if archive_path is not None:
                records_by_archive.setdefault(archive_path, []).append(record)
        loaded: dict[str, ReferenceSpectrum] = {}
        for archive_path, archive_records in records_by_archive.items():
            try:
                archive = zipfile.ZipFile(archive_path)
            except zipfile.BadZipFile:
                continue
            with archive:
                for record in archive_records:
                    try:
                        member = record.metadata.get("member", "")
                        text = archive.read(member).decode("utf-8", errors="ignore")
                        x, y = self._parse_xy_text(text)
                    except Exception:
                        continue
                    loaded[record.key] = ReferenceSpectrum(
                        x=x,
                        y=y,
                        kind=record.kind,
                        name=record.name,
                        source_path=f"{archive_path}:{member}",
                        record=record,
                        band_set=band_sets.get(record.key),
                    )
        return loaded

    def _band_prefilter_score(
        self,
        observed_bands: list[SpectralBand],
        reference_band_set: ReferenceBandSet | None,
        tolerance_cm1: float = 20.0,
    ) -> float:
        if not observed_bands or reference_band_set is None or not reference_band_set.bands:
            return 0.0
        unused = set(range(len(reference_band_set.bands)))
        weighted_match = 0.0
        matched = 0
        total_weight = sum(max(float(band.intensity), 0.05) for band in observed_bands)
        for observed in observed_bands:
            best_index = None
            best_delta = tolerance_cm1
            for index in unused:
                delta = abs(float(observed.position) - float(reference_band_set.bands[index].position))
                if delta <= best_delta:
                    best_delta = delta
                    best_index = index
            if best_index is None:
                continue
            unused.remove(best_index)
            matched += 1
            weighted_match += max(float(observed.intensity), 0.05) * (1.0 - best_delta / tolerance_cm1)
        coverage = weighted_match / max(total_weight, 1.0e-9)
        precision = matched / max(len(reference_band_set.bands), 1)
        return 0.8 * coverage + 0.2 * precision

    def _parse_xy_text(self, text: str) -> tuple[list[float], list[float]]:
        rows: list[tuple[float, float]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(("#", ";", "//")):
                continue
            parts = line.replace(",", " ").replace("\t", " ").split()
            if len(parts) < 2:
                continue
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        if not rows:
            raise ValueError("No numeric x/y data found in RRUFF member")
        rows.sort(key=lambda item: item[0])
        return [row[0] for row in rows], [row[1] for row in rows]
