from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
import re
import shutil
import ssl
from urllib.parse import quote, urlencode
from urllib.request import HTTPCookieProcessor, HTTPSHandler, Request, build_opener
import zipfile

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands, extract_reference_band_set
from vibrational_finder.models import CompoundCandidate, ReferenceBandSet, ReferenceSpectrum, SpectralBand
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache


ROD_BASE_URL = "https://solsa.crystallography.net/rod"
ROD_SEARCH_URL = f"{ROD_BASE_URL}/result.php"
ROD_BAND_RECIPE_VERSION = "arpls-savgol-ramanchada2-topo-normalized-v1"


@dataclass(frozen=True, slots=True)
class RodArchiveInfo:
    path: Path

    @property
    def is_cached(self) -> bool:
        return self.path.exists()


class RodSource:
    """Download and index the CC0 Raman Open Database archive."""

    name = "ROD"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / "rod"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.archive = RodArchiveInfo(self.cache_root / "rod_all.zip")
        self.reference_cache = ReferenceSpectrumCache(self.cache_root)
        self._records: list[CandidateRecord] = []
        self._member_by_record_key: dict[str, str] = {}
        self.refresh_index()

    def download_archive(
        self,
        *,
        include_duplicates: bool = True,
        include_theoretical: bool = True,
        include_errors: bool = False,
    ) -> Path:
        payload = {"id": "%", "submit": "Search"}
        if include_duplicates:
            payload["include_duplicates"] = "1"
        if include_theoretical:
            payload["include_theoretical"] = "1"
        if include_errors:
            payload["include_errors"] = "1"

        opener = self._opener()
        request = Request(
            ROD_SEARCH_URL,
            data=urlencode(payload).encode("ascii"),
            headers={"User-Agent": "IR-Raman-Phase-Finder/0.1"},
        )
        with opener.open(request, timeout=120) as response:
            result_html = response.read().decode("utf-8", errors="replace")
        match = re.search(r"CODSESSION=([A-Za-z0-9]+)", result_html)
        if match is None:
            raise RuntimeError("ROD search did not return a downloadable result session.")

        archive_url = f"{ROD_SEARCH_URL}?format=zip&CODSESSION={quote(match.group(1))}"
        target = self.archive.path
        temporary = target.with_suffix(target.suffix + ".part")
        with opener.open(archive_url, timeout=300) as response:
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        try:
            with zipfile.ZipFile(temporary) as archive:
                if not any(name.lower().endswith(".rod") for name in archive.namelist()):
                    raise RuntimeError("Downloaded ROD archive contains no .rod spectra.")
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(target)
        self.refresh_index(force=True)
        return target

    def clear(self) -> None:
        self.archive.path.unlink(missing_ok=True)
        self.archive.path.with_suffix(self.archive.path.suffix + ".part").unlink(missing_ok=True)
        self.refresh_index()

    def refresh_index(self, *, force: bool = False) -> None:
        self._records = []
        self._member_by_record_key = {}
        if not self.archive.is_cached:
            self.reference_cache.clear_source(self.name)
            return
        cached_records = self.reference_cache.search(SourceQuery(), sources=[self.name], limit=100000)
        if not force and cached_records:
            self._records = cached_records
            self._member_by_record_key = {
                record.key: str(record.metadata.get("member", ""))
                for record in cached_records
                if record.metadata.get("member")
            }
            return
        try:
            with zipfile.ZipFile(self.archive.path) as archive:
                for member_name in archive.namelist():
                    if not member_name.lower().endswith(".rod"):
                        continue
                    try:
                        text = archive.read(member_name).decode("utf-8", errors="replace")
                        record = self._record_from_text(text, member_name)
                    except Exception:
                        continue
                    self._records.append(record)
                    self._member_by_record_key[record.key] = member_name
        except zipfile.BadZipFile:
            return
        self.reference_cache.clear_source(self.name)
        self.reference_cache.upsert_records(self._records)

    def indexed_count(self) -> int:
        return len(self._records)

    def status_row(self) -> list[str]:
        size = self.archive.path.stat().st_size if self.archive.is_cached else 0
        experimental = sum(1 for record in self._records if record.metadata.get("determination_method") != "theoretical")
        theoretical = len(self._records) - experimental
        line_indexed = self.indexed_band_count()
        return [
            self.name,
            "Indexed" if self._records else "Empty",
            f"{experimental} experimental, {theoretical} theoretical Raman; {line_indexed} line-indexed; CC0",
            str(len(self._records)),
            f"{size / (1024 * 1024):.1f} MB",
            str(self.cache_root),
        ]

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        return self.reference_cache.search(query, sources=[self.name])

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        member_name = self._member_by_record_key.get(candidate.key) or candidate.metadata.get("member", "")
        if not member_name or not self.archive.is_cached:
            raise FileNotFoundError(f"ROD spectrum is not indexed: {candidate.key}")
        with zipfile.ZipFile(self.archive.path) as archive:
            text = archive.read(member_name).decode("utf-8", errors="replace")
        x, y = self._spectrum_xy(text)
        return ReferenceSpectrum(
            x=x,
            y=y,
            kind=SignalKind.RAMAN,
            name=candidate.name,
            source_path=f"{self.archive.path}:{member_name}",
            record=candidate,
            band_set=self.reference_cache.load_band_set(candidate.key, ROD_BAND_RECIPE_VERSION),
        )

    def build_band_index(self) -> tuple[int, int]:
        from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum

        indexed_keys = self.reference_cache.indexed_band_keys(self.name, ROD_BAND_RECIPE_VERSION)
        indexed = 0
        skipped = 0
        pending: list[tuple[str, ReferenceBandSet]] = []
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
        for record in self._records:
            if record.key in indexed_keys:
                continue
            try:
                reference = self.load_spectrum(record)
                processed = preprocess_spectrum(reference, preprocessing_options)
                band_set = extract_reference_band_set(
                    processed,
                    detection_options,
                    origin=str(record.metadata.get("determination_method") or "experimental"),
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
                    self.reference_cache.upsert_band_sets(pending, ROD_BAND_RECIPE_VERSION)
                    pending.clear()
                indexed += 1
            except Exception:
                skipped += 1
        if pending:
            self.reference_cache.upsert_band_sets(pending, ROD_BAND_RECIPE_VERSION)
        return indexed, skipped

    def indexed_band_count(self) -> int:
        return self.reference_cache.indexed_band_reference_count(self.name, ROD_BAND_RECIPE_VERSION)

    def clear_band_index(self) -> None:
        self.reference_cache.clear_band_index(self.name)

    def load_candidates(
        self,
        query: SourceQuery | None = None,
        *,
        observed: ReferenceSpectrum | None = None,
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
                recipe_version=ROD_BAND_RECIPE_VERSION,
                limit=max(limit * 4, 200),
            )
            if len(records) < limit:
                selected_keys = {record.key for record in records}
                records.extend(record for record in self.search(query) if record.key not in selected_keys)
            records = records[:limit]
        else:
            records = self.search(query)[:limit]
        candidates: list[CompoundCandidate] = []
        for record in records:
            try:
                reference = self.load_spectrum(record)
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
                    reference=reference,
                    band_set=reference.band_set,
                )
            )
        return candidates

    def _record_from_text(self, text: str, member_name: str) -> CandidateRecord:
        entry_id = self._cif_value(text, "_rod_database.code") or self._cif_value(text, "_rod_database_code")
        if not entry_id:
            match = re.search(r"(?m)^data_([0-9]+)\s*$", text)
            entry_id = match.group(1) if match else Path(member_name).stem
        name = next(
            (
                value
                for value in (
                    self._cif_value(text, "_chemical_name_mineral"),
                    self._cif_value(text, "_chemical_name_common"),
                    self._cif_value(text, "_chemical_name_systematic"),
                )
                if value
            ),
            f"ROD {entry_id}",
        )
        formula = self._cif_value(text, "_chemical_formula_structural") or self._cif_value(text, "_chemical_formula_sum")
        method = self._cif_value(text, "_raman_determination_method").lower() or "experimental"
        direction = self._cif_value(text, "_raman_measurement_device.direction_polarization")
        if method == "theoretical":
            orientation = "calculated"
            polarization = "calculated"
            quality = "calculated reference"
        elif direction.lower() == "unoriented":
            orientation = "unoriented"
            polarization = "unknown"
            quality = "measured reference"
        elif direction:
            orientation = "oriented"
            polarization = direction
            quality = "measured reference"
        else:
            orientation = "unknown"
            polarization = "unknown"
            quality = "measured reference"

        description = self._cif_value(text, "_publ_section_title")
        key = f"ROD:{entry_id}:{member_name}"
        return CandidateRecord(
            key=key,
            source=self.name,
            entry_id=entry_id,
            name=name,
            formula=formula,
            kind=SignalKind.RAMAN,
            metadata={
                "member": member_name,
                "compound_key": f"ROD:{entry_id}",
                "description": description,
                "quality": quality,
                "determination_method": method,
                "orientation": orientation,
                "polarization": polarization,
                "laser_nm": self._cif_value(text, "_raman_measurement_device.excitation_laser_wavelength"),
                "resolution_cm1": self._cif_value(text, "_raman_measurement_device.resolution"),
                "space_group": self._cif_value(text, "_symmetry_space_group_name_H-M"),
                "cod_id": self._cif_value(text, "_cod_database_code"),
                "reference_url": f"{ROD_BASE_URL}/{entry_id}.html",
                "license": "CC0-1.0",
            },
        )

    def _spectrum_xy(self, text: str) -> tuple[list[float], list[float]]:
        lines = text.splitlines()
        for index, raw_line in enumerate(lines):
            if raw_line.strip() != "loop_":
                continue
            headers: list[str] = []
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].strip().startswith("_"):
                headers.append(lines[cursor].strip())
                cursor += 1
            try:
                x_column = headers.index("_raman_spectrum.raman_shift")
                y_column = headers.index("_raman_spectrum.intensity")
            except ValueError:
                continue
            rows: list[tuple[float, float]] = []
            while cursor < len(lines):
                line = lines[cursor].strip()
                if not line or line.startswith(("#", "loop_", "_", "data_")):
                    if rows or line.startswith(("loop_", "_", "data_")):
                        break
                    cursor += 1
                    continue
                values = line.split()
                if len(values) < len(headers):
                    break
                try:
                    rows.append((float(values[x_column]), float(values[y_column])))
                except ValueError:
                    break
                cursor += 1
            if rows:
                rows.sort(key=lambda item: item[0])
                return [item[0] for item in rows], [item[1] for item in rows]
        raise ValueError("ROD entry contains no Raman shift/intensity loop.")

    def _cif_value(self, text: str, tag: str) -> str:
        match = re.search(rf"(?m)^{re.escape(tag)}\s+(.+?)\s*$", text)
        if match is None:
            return ""
        value = match.group(1).strip()
        if value in {"?", "."}:
            return ""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value.strip()

    def _opener(self):
        context = ssl.create_default_context()
        try:
            import certifi

            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        return build_opener(HTTPCookieProcessor(CookieJar()), HTTPSHandler(context=context))
