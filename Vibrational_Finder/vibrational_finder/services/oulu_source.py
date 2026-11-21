from __future__ import annotations

from ast import literal_eval
from collections.abc import Iterator
from hashlib import file_digest
from io import BufferedReader
import math
from pathlib import Path
import shutil
import ssl
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

import certifi

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind, SignalTrace
from vibrational_finder.models import CompoundCandidate, ReferenceBandSet, ReferenceSpectrum, SpectralBand
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache
from vibrational_finder.services.research_raman_source import ResearchPackage
from vibrational_finder.services.staged_search import StagedReferenceSearchService


OULU_ARCHIVE_NAME = "Computational_Raman_Database_v1.0.1.zip"
OULU_RECORD_URL = "https://archive.materialscloud.org/records/0m9r0-g3486"
OULU_ARCHIVE_URL = f"{OULU_RECORD_URL}/files/{OULU_ARCHIVE_NAME}?download=1"
OULU_ARCHIVE_MD5 = "e2aaea03df70fda95dbd970c60456882"


class OuluRamanSource:
    """An explicitly downloaded, locally indexed source of calculated Raman lines."""

    name = "Oulu CRD"
    band_recipe_version = "oulu-crd-1.0.1-active-raman-lines-v1"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / "oulu_crd"
        self.index_path = self.cache_root / "reference_index.sqlite"
        self.reference_cache: ReferenceSpectrumCache | None = None
        self.refresh_index()

    def available_archives(self) -> list[ResearchPackage]:
        return [
            ResearchPackage(
                "v1.0.1", "Calculated Raman v1.0.1 (145.7 MiB)", OULU_ARCHIVE_URL,
                self.cache_root / OULU_ARCHIVE_NAME,
            )
        ]

    def download_archive(self, key: str | None = None) -> Path:
        package = self.available_archives()[0]
        if key not in (None, package.key):
            raise ValueError(f"Unknown Oulu CRD package: {key}")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.cache_root, suffix=".part", delete=False) as handle:
            partial = Path(handle.name)
        try:
            request = Request(package.url, headers={"User-Agent": "IR-Raman-Phase-Finder"})
            context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(request, timeout=120, context=context) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
            with partial.open("rb") as handle:
                if file_digest(handle, "md5").hexdigest() != OULU_ARCHIVE_MD5:
                    raise ValueError("Oulu CRD download checksum does not match v1.0.1.")
            with ZipFile(partial) as archive:
                if "crd.json" not in archive.namelist():
                    raise ValueError("Oulu CRD archive is missing crd.json.")
            partial.replace(package.path)
        finally:
            partial.unlink(missing_ok=True)
        return package.path

    def refresh_index(self) -> None:
        self.reference_cache = ReferenceSpectrumCache(self.cache_root) if self.index_path.is_file() else None

    def indexed_count(self) -> int:
        return self.reference_cache.indexed_count(source=self.name) if self.reference_cache else 0

    def indexed_band_count(self) -> int:
        return self.indexed_count()

    def status_row(self) -> list[str]:
        count = self.indexed_count()
        if count:
            state, detail = "Indexed", f"{count:,} references indexed"
        elif self.available_archives()[0].is_cached:
            state, detail = "Downloaded", "Use Build line index to make references searchable"
        else:
            state, detail = "External", "Not downloaded; use Download / update"
        return [self.name, state, f"Calculated Raman lines • {detail} • CC BY 4.0", str(count), "", str(self.cache_root)]

    def clear(self) -> None:
        self.available_archives()[0].path.unlink(missing_ok=True)
        self.clear_band_index()

    def clear_band_index(self) -> None:
        self.index_path.unlink(missing_ok=True)
        self.refresh_index()

    def search(self, query: SourceQuery, *, limit: int = 2000) -> list[CandidateRecord]:
        cache = self.reference_cache
        return cache.search(query, sources=[self.name], limit=limit) if cache else []

    def search_by_bands(
        self,
        query: SourceQuery,
        _observed: SignalTrace | None = None,
        *,
        observed_bands: list[SpectralBand] | None = None,
        limit: int = 80,
    ) -> list[CandidateRecord]:
        cache = self.reference_cache
        if cache is None:
            return []
        strongest = sorted(observed_bands or (), key=lambda band: band.intensity, reverse=True)[:24]
        return cache.search_by_bands(
            query, [band.position for band in strongest], sources=[self.name],
            recipe_version=self.band_recipe_version, limit=limit,
        )

    def load_candidates(
        self,
        query: SourceQuery,
        *,
        observed: SignalTrace | None = None,
        observed_bands: list[SpectralBand] | None = None,
        limit: int = 80,
    ) -> list[CompoundCandidate]:
        records = self.search_by_bands(query, observed, observed_bands=observed_bands, limit=limit)
        return StagedReferenceSearchService([self]).load_candidates(records)

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        cache = self.reference_cache
        if cache is None or candidate.source != self.name:
            raise KeyError(candidate.key)
        bands = cache.load_band_set(candidate.key, self.band_recipe_version)
        if bands is None:
            raise KeyError(candidate.key)
        return ReferenceSpectrum(x=[], y=[], kind=candidate.kind, name=candidate.name, record=candidate, band_set=bands)

    def build_band_index(self) -> tuple[int, int]:
        package = self.available_archives()[0]
        if not package.is_cached:
            raise FileNotFoundError("Download Oulu CRD first using Download / update.")
        skipped = 0
        with TemporaryDirectory(dir=self.cache_root, prefix="index-") as staging:
            cache = ReferenceSpectrumCache(staging)
            records: list[CandidateRecord] = []
            sets: list[tuple[str, ReferenceBandSet]] = []
            for item in _archive_records(package.path):
                item_and_bands = self._parse_record(item)
                if item_and_bands is None:
                    skipped += 1
                    continue
                record, band_set = item_and_bands
                records.append(record)
                sets.append((record.key, band_set))
                if len(records) == 128:
                    cache.upsert_records(records)
                    cache.upsert_band_sets(sets, self.band_recipe_version)
                    records.clear()
                    sets.clear()
            if records:
                cache.upsert_records(records)
                cache.upsert_band_sets(sets, self.band_recipe_version)
            indexed = cache.indexed_count(source=self.name)
            if not indexed:
                raise ValueError("Oulu CRD contains no usable Raman-active modes.")
            cache.index_path.replace(self.index_path)
        self.refresh_index()
        return indexed, skipped

    def _parse_record(self, item: object) -> tuple[CandidateRecord, ReferenceBandSet] | None:
        if not isinstance(item, dict):
            return None
        # The distributed crd.json is an ASE JSON database, not a table
        # of flattened records. Also accept already-decoded flat entries.
        properties, data = item.get("key_value_pairs"), item.get("data")
        nested = isinstance(properties, dict) and isinstance(data, dict)
        if not nested:
            properties = data = item
        identifier = _text(properties.get("mpid"))
        formula = _text(data.get("chemical_formula"))
        positions = _frequencies(properties.get("frequencies_cm"))
        active = _array_values(data.get("Ramanactive"))
        if not identifier or not formula or positions is None or active is None:
            return None
        if len(positions) != len(active):
            return None
        if nested:
            labels = _ase_mode_labels(properties.get("IRlabels"), properties.get("IRbands"), len(positions))
        else:
            labels = properties.get("IRlabels")
            if not isinstance(labels, list) or len(labels) != len(positions):
                labels = [""] * len(positions)
        lines: dict[float, SpectralBand] = {}
        for position, flag, symmetry in zip(positions, active, labels, strict=True):
            if flag != 1 or isinstance(position, bool) or not isinstance(position, (int, float)):
                continue
            wavenumber = float(position)
            if math.isfinite(wavenumber) and wavenumber > 0:
                lines.setdefault(wavenumber, SpectralBand(position=wavenumber, intensity=1.0, symmetry=_text(symmetry)))
        if not lines:
            return None
        record = CandidateRecord(
            key=f"{self.name}:{identifier}", source=self.name, entry_id=identifier,
            name=formula, formula=formula, kind=SignalKind.RAMAN,
            metadata={
                "origin": "calculated", "dataset": "Oulu CRD v1.0.1", "license": "CC BY 4.0",
                "spacegroup": _text(properties.get("spacegroup")),
                "pointgroup": _text(properties.get("pointgroup")) or _text(data.get("pointgroup")),
                "materials_project_id": identifier, "reference_url": OULU_RECORD_URL,
                "doi": "10.1038/s41597-023-01988-5", "intensity": "unweighted markers, not measured",
            },
        )
        return record, ReferenceBandSet(
            bands=[lines[position] for position in sorted(lines)], origin="calculated",
            extraction_method="Oulu CRD Ramanactive + frequencies_cm",
            processing_recipe={"dataset_version": "1.0.1", "positions_only": True},
        )


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _array_values(value: object) -> list | None:
    if isinstance(value, list):
        return value
    if not isinstance(value, dict):
        return None
    array = value.get("__ndarray__")
    if not isinstance(array, list) or len(array) != 3:
        return None
    shape, _dtype, values = array
    if not isinstance(values, list) or shape != [len(values)]:
        return None
    return values


def _frequencies(value: object) -> list | None:
    if not isinstance(value, str):
        return _array_values(value)
    text = value.strip()
    if not (text.startswith("[") and text.endswith("]")):
        return None
    try:
        return [float(field) for field in text[1:-1].split()]
    except ValueError:
        return None


def _literal_list(value: object) -> list | None:
    if isinstance(value, str):
        if len(value) > 65536:
            return None
        try:
            value = literal_eval(value)
        except (ValueError, SyntaxError, RecursionError):
            return None
    return value if isinstance(value, list) else None


def _ase_mode_labels(raw_labels: object, raw_groups: object, mode_count: int) -> list[str]:
    labels, groups = _literal_list(raw_labels), _literal_list(raw_groups)
    blank = [""] * mode_count
    if labels is None or groups is None or len(labels) != len(groups):
        return blank
    by_mode = blank.copy()
    seen: set[int] = set()
    for label, group in zip(labels, groups, strict=True):
        if not isinstance(group, list) or not group:
            return blank
        for index in group:
            if type(index) is not int or not 0 <= index < mode_count or index in seen:
                return blank
            seen.add(index)
            by_mode[index] = _text(label)
    return by_mode if len(seen) == mode_count else blank


def _archive_records(path: Path) -> Iterator[object]:
    try:
        import ijson
    except ImportError as exc:
        raise RuntimeError("Oulu CRD indexing requires ijson (an IR/Raman Phase Finder dependency).") from exc
    try:
        with ZipFile(path) as archive, BufferedReader(archive.open("crd.json")) as handle:
            first = handle.peek().lstrip()[:1]
            if first == b"[":
                yield from ijson.items(handle, "item", use_float=True)
            elif first == b"{":
                for key, item in ijson.kvitems(handle, "", use_float=True):
                    if key not in {"ids", "nextid"}:
                        yield item
            else:
                raise ValueError("Unsupported Oulu CRD JSON structure.")
    except (BadZipFile, KeyError, ijson.JSONError) as exc:
        raise ValueError(f"Cannot read Oulu CRD archive: {exc}") from exc
