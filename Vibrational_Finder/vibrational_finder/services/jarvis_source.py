from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import shutil
import ssl
from urllib.request import HTTPSHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile

import certifi
import numpy as np

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind, SignalTrace
from vibrational_finder.band_detection import detect_bands
from vibrational_finder.models import CompoundCandidate, ReferenceBandSet, ReferenceSpectrum, SpectralBand
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache


JARVIS_METADATA_URL = "https://ndownloader.figshare.com/files/38521619"
JARVIS_XML_URL = "https://www.ctcms.nist.gov/~knc6/static/JARVIS-DFT/{jid}.xml"
JARVIS_BAND_RECIPE_VERSION = "jarvis-dft-modes-and-xml-lines-v1"


class _NonFiniteJsonStream:
    """Replace non-standard numeric literals while preserving streaming reads."""

    def __init__(self, source) -> None:
        self.source = source
        self.output = b""
        self.tail = b""
        self.eof = False

    def read(self, size: int = -1) -> bytes:
        if size == 0:
            return b""
        if size < 0:
            data = self.tail + self.source.read()
            self.tail = b""
            self.eof = True
            return self._sanitize(data)
        while len(self.output) < size and not self.eof:
            chunk = self.source.read(max(65536, size))
            if chunk:
                data = self.tail + chunk
                self.tail = data[-16:]
                self.output += self._sanitize(data[:-16])
            else:
                self.output += self._sanitize(self.tail)
                self.tail = b""
                self.eof = True
        result = self.output[:size]
        self.output = self.output[size:]
        return result

    def _sanitize(self, data: bytes) -> bytes:
        data = re.sub(rb"(?<![A-Za-z0-9_])NaN(?![A-Za-z0-9_])", b"null", data)
        data = re.sub(rb"(?<![A-Za-z0-9_])-?Infinity(?![A-Za-z0-9_])", b"null", data)
        return data


@dataclass(frozen=True, slots=True)
class JarvisArchiveInfo:
    path: Path

    @property
    def is_cached(self) -> bool:
        return self.path.exists()


class JarvisDftSource:
    """Local index and lazy spectrum cache for calculated JARVIS-DFT data."""

    name = "JARVIS-DFT"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / "jarvis_dft"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.archive = JarvisArchiveInfo(self.cache_root / "dft_3d.zip")
        self.xml_root = self.cache_root / "xml"
        self.xml_root.mkdir(parents=True, exist_ok=True)
        self.index_state_path = self.cache_root / "index_state.json"
        self.reference_cache = ReferenceSpectrumCache(self.cache_root)
        self.refresh_index()

    def download_metadata(self) -> Path:
        target = self.archive.path
        temporary = target.with_suffix(target.suffix + ".part")
        request = Request(JARVIS_METADATA_URL, headers={"User-Agent": "IR-Raman-Phase-Finder/0.1"})
        with self._opener().open(request, timeout=300) as response:
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        try:
            with zipfile.ZipFile(temporary) as archive:
                if not any(name.lower().endswith(".json") for name in archive.namelist()):
                    raise RuntimeError("Downloaded JARVIS archive contains no JSON metadata.")
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(target)
        self.refresh_index(force=True)
        return target

    def clear(self) -> None:
        self.archive.path.unlink(missing_ok=True)
        self.archive.path.with_suffix(self.archive.path.suffix + ".part").unlink(missing_ok=True)
        self.index_state_path.unlink(missing_ok=True)
        shutil.rmtree(self.xml_root, ignore_errors=True)
        self.xml_root.mkdir(parents=True, exist_ok=True)
        self.reference_cache.clear_source(self.name)

    def refresh_index(self, *, force: bool = False) -> None:
        if not self.archive.is_cached:
            self.reference_cache.clear_source(self.name)
            self.index_state_path.unlink(missing_ok=True)
            return
        if not force and self._index_is_current():
            return

        records: list[CandidateRecord] = []
        with zipfile.ZipFile(self.archive.path) as archive:
            json_members = [name for name in archive.namelist() if name.lower().endswith(".json")]
            if not json_members:
                raise RuntimeError("JARVIS metadata archive contains no JSON file.")
            with archive.open(json_members[0]) as handle:
                for item in self._stream_json_items(handle):
                    record = self._ftir_record(item)
                    if record is not None:
                        records.append(record)

        self.reference_cache.clear_source(self.name)
        self.reference_cache.upsert_records(records)
        for xml_path in self.xml_root.glob("JVASP-*.xml"):
            try:
                jid = xml_path.stem
                base = next(
                    iter(self.reference_cache.search(SourceQuery(text=jid, kind=SignalKind.FTIR), sources=[self.name], limit=1)),
                    None,
                )
                if base is not None:
                    self._index_cached_raman(base, xml_path)
            except Exception:
                continue
        self._write_index_state()

    def indexed_count(self, kind: SignalKind | None = None) -> int:
        return self.reference_cache.indexed_count(kind=kind, source=self.name)

    def status_row(self) -> list[str]:
        archive_size = self.archive.path.stat().st_size if self.archive.is_cached else 0
        ftir_count = self.indexed_count(SignalKind.FTIR)
        raman_count = self.indexed_count(SignalKind.RAMAN)
        xml_count = sum(1 for _ in self.xml_root.glob("JVASP-*.xml"))
        return [
            self.name,
            "Indexed" if ftir_count else "Empty",
            (
                f"{ftir_count} calculated FTIR, {raman_count} verified Raman; "
                f"{self.indexed_band_count()} line-indexed; {xml_count} XML cached"
            ),
            str(ftir_count + raman_count),
            f"{archive_size / (1024 * 1024):.1f} MB",
            str(self.cache_root),
        ]

    def search(self, query: SourceQuery, *, limit: int = 2000) -> list[CandidateRecord]:
        return self.reference_cache.search(query, sources=[self.name], limit=limit)

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        if candidate.source != self.name:
            raise ValueError(f"Not a JARVIS-DFT candidate: {candidate.key}")
        xml_path = self._xml_path(candidate.entry_id)
        if not xml_path.exists():
            self._download_xml(candidate.entry_id, xml_path)
        spectra = self._parse_xml_spectra(xml_path)
        self._index_cached_raman(candidate, xml_path, spectra=spectra)
        if candidate.kind not in spectra:
            raise ValueError(f"{candidate.entry_id} has no calculated {candidate.kind.value.upper()} intensities.")
        frequencies, intensities = spectra[candidate.kind]
        self._upsert_spectrum_band_set(candidate.key, frequencies, intensities, extraction_method="JARVIS XML intensities")
        x, y = self._broaden_lines(frequencies, intensities)
        return ReferenceSpectrum(
            x=x,
            y=y,
            kind=candidate.kind,
            name=candidate.name,
            source_path=str(xml_path),
            record=candidate,
            band_set=self.reference_cache.load_band_set(candidate.key, JARVIS_BAND_RECIPE_VERSION),
        )

    def load_candidates(
        self,
        query: SourceQuery | None = None,
        *,
        observed: SignalTrace | None = None,
        observed_bands: list[SpectralBand] | None = None,
        limit: int = 12,
    ) -> list[CompoundCandidate]:
        query = query or SourceQuery()
        if observed is not None and self.indexed_band_count() > 0:
            if observed_bands is None:
                observed_bands = detect_bands(observed)
            strongest_observed = sorted(observed_bands, key=lambda band: band.intensity, reverse=True)[:24]
            records = self.reference_cache.search_by_bands(
                query,
                [band.position for band in strongest_observed],
                tolerance_cm1=25.0,
                sources=[self.name],
                recipe_version=JARVIS_BAND_RECIPE_VERSION,
                limit=max(limit * 8, 120),
            )
            if len(records) < limit:
                selected_keys = {record.key for record in records}
                records.extend(record for record in self.search(query, limit=500) if record.key not in selected_keys)
        else:
            records = self.search(query, limit=500)
        if observed is not None and query.kind == SignalKind.FTIR and self.indexed_band_count() <= 0:
            records.sort(key=lambda record: self._mode_prefilter_score(record, observed), reverse=True)
        candidates: list[CompoundCandidate] = []
        for record in records[: max(1, limit)]:
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

    def build_band_index(self) -> tuple[int, int]:
        indexed_keys = self.reference_cache.indexed_band_keys(self.name, JARVIS_BAND_RECIPE_VERSION)
        indexed = 0
        skipped = 0

        for xml_path in self.xml_root.glob("JVASP-*.xml"):
            jid = xml_path.stem
            base = next(
                iter(self.reference_cache.search(SourceQuery(text=jid, kind=SignalKind.FTIR), sources=[self.name], limit=1)),
                None,
            )
            if base is None:
                continue
            try:
                spectra = self._parse_xml_spectra(xml_path)
                self._index_cached_raman(base, xml_path, spectra=spectra)
                for kind, (frequencies, intensities) in spectra.items():
                    key = f"{self.name}:{jid}:{kind.value}"
                    if key in indexed_keys:
                        continue
                    self._upsert_spectrum_band_set(key, frequencies, intensities, extraction_method="JARVIS XML intensities")
                    indexed += 1
            except Exception:
                skipped += 1

        records = self.reference_cache.search(SourceQuery(), sources=[self.name], limit=200000)
        pending: list[tuple[str, ReferenceBandSet]] = []
        indexed_keys = self.reference_cache.indexed_band_keys(self.name, JARVIS_BAND_RECIPE_VERSION)
        for record in records:
            if record.key in indexed_keys:
                continue
            modes = [mode for mode in self._number_list(str(record.metadata.get("modes_cm1", ""))) if mode > 0.0]
            if not modes:
                skipped += 1
                continue
            pending.append((record.key, self._band_set_from_lines(modes, [1.0] * len(modes), extraction_method="JARVIS metadata modes")))
            indexed += 1
            if len(pending) >= 500:
                self.reference_cache.upsert_band_sets(pending, JARVIS_BAND_RECIPE_VERSION)
                pending.clear()
        if pending:
            self.reference_cache.upsert_band_sets(pending, JARVIS_BAND_RECIPE_VERSION)
        return indexed, skipped

    def indexed_band_count(self) -> int:
        return self.reference_cache.indexed_band_reference_count(self.name, JARVIS_BAND_RECIPE_VERSION)

    def clear_band_index(self) -> None:
        self.reference_cache.clear_band_index(self.name)

    def _ftir_record(self, item: object) -> CandidateRecord | None:
        if not isinstance(item, dict) or self._is_missing(item.get("min_ir_mode")):
            return None
        jid = str(item.get("jid", "")).strip()
        if not re.fullmatch(r"JVASP-\d+", jid):
            return None
        formula = str(item.get("formula", "")).strip()
        modes = item.get("modes")
        mode_text = ""
        if isinstance(modes, list):
            mode_text = ",".join(f"{float(value):.4g}" for value in modes if self._is_number(value))
        return CandidateRecord(
            key=f"{self.name}:{jid}:ftir",
            source=self.name,
            entry_id=jid,
            name=formula or jid,
            formula=formula,
            kind=SignalKind.FTIR,
            metadata={
                "compound_key": f"{self.name}:{jid}",
                "quality": "calculated reference",
                "determination_method": "DFT/DFPT",
                "orientation": "calculated",
                "polarization": "calculated",
                "space_group": str(item.get("spg_symbol", "") or ""),
                "space_group_number": str(item.get("spg_number", "") or ""),
                "min_ir_mode_cm1": str(item.get("min_ir_mode", "") or ""),
                "max_ir_mode_cm1": str(item.get("max_ir_mode", "") or ""),
                "modes_cm1": mode_text,
                "reference_url": JARVIS_XML_URL.format(jid=jid),
                "license": "NIST/JARVIS data terms",
            },
        )

    def _index_cached_raman(
        self,
        base: CandidateRecord,
        xml_path: Path,
        *,
        spectra: dict[SignalKind, tuple[list[float], list[float]]] | None = None,
    ) -> None:
        spectra = spectra or self._parse_xml_spectra(xml_path)
        if SignalKind.RAMAN not in spectra:
            return
        metadata = dict(base.metadata)
        metadata.update(
            {
                "quality": "calculated reference",
                "determination_method": "DFT Raman activity",
                "reference_url": JARVIS_XML_URL.format(jid=base.entry_id),
                "path": str(xml_path),
            }
        )
        record = CandidateRecord(
            key=f"{self.name}:{base.entry_id}:raman",
            source=self.name,
            entry_id=base.entry_id,
            name=base.name,
            formula=base.formula,
            kind=SignalKind.RAMAN,
            metadata=metadata,
        )
        self.reference_cache.upsert_records([record])
        frequencies, intensities = spectra[SignalKind.RAMAN]
        self._upsert_spectrum_band_set(record.key, frequencies, intensities, extraction_method="JARVIS XML Raman activity")

    def _upsert_spectrum_band_set(
        self,
        reference_key: str,
        frequencies: list[float],
        intensities: list[float],
        *,
        extraction_method: str,
    ) -> None:
        band_set = self._band_set_from_lines(frequencies, intensities, extraction_method=extraction_method)
        if band_set.bands:
            self.reference_cache.upsert_band_set(reference_key, band_set, JARVIS_BAND_RECIPE_VERSION)

    def _band_set_from_lines(
        self,
        frequencies: list[float],
        intensities: list[float],
        *,
        extraction_method: str,
    ) -> ReferenceBandSet:
        rows = [
            (float(frequency), max(float(intensity), 0.0))
            for frequency, intensity in zip(frequencies, intensities, strict=False)
            if math.isfinite(float(frequency)) and math.isfinite(float(intensity)) and float(frequency) > 0.0
        ]
        scale = max((intensity for _frequency, intensity in rows), default=0.0)
        bands = [
            SpectralBand(
                position=frequency,
                intensity=(intensity / scale if scale > 0.0 else 1.0),
                width=10.0,
                prominence=(intensity / scale if scale > 0.0 else 1.0),
                confidence=1.0,
            )
            for frequency, intensity in sorted(rows)
        ]
        return ReferenceBandSet(
            bands=bands,
            origin="calculated",
            extraction_method=extraction_method,
            processing_recipe={
                "recipe": JARVIS_BAND_RECIPE_VERSION,
                "normalization": "max",
                "line_width_cm1": 10.0,
            },
        )

    def _download_xml(self, jid: str, target: Path) -> None:
        if not re.fullmatch(r"JVASP-\d+", jid):
            raise ValueError(f"Invalid JARVIS identifier: {jid}")
        temporary = target.with_suffix(target.suffix + ".part")
        request = Request(JARVIS_XML_URL.format(jid=jid), headers={"User-Agent": "IR-Raman-Phase-Finder/0.1"})
        with self._opener().open(request, timeout=120) as response:
            with temporary.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        try:
            ET.parse(temporary)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        temporary.replace(target)

    def _parse_xml_spectra(self, path: Path) -> dict[SignalKind, tuple[list[float], list[float]]]:
        root = ET.parse(path).getroot()
        spectra: dict[SignalKind, tuple[list[float], list[float]]] = {}
        ir_text = self._first_tag_text(root, "ir_intensity")
        if ";" in ir_text:
            frequencies_text, intensity_text = ir_text.strip(" '\"").split(";", 1)
            parsed = self._paired_numbers(frequencies_text, intensity_text)
            if parsed is not None:
                spectra[SignalKind.FTIR] = parsed

        for node in root.iter():
            if self._local_tag(node.tag) != "raman_dat":
                continue
            frequencies_text = self._first_tag_text(node, "frequencies")
            activity_text = self._first_tag_text(node, "activity")
            parsed = self._paired_numbers(frequencies_text, activity_text)
            if parsed is not None:
                spectra[SignalKind.RAMAN] = parsed
                break
        return spectra

    def _paired_numbers(self, x_text: str, y_text: str) -> tuple[list[float], list[float]] | None:
        x_values = self._number_list(x_text)
        y_values = self._number_list(y_text)
        rows = [
            (x, max(0.0, y))
            for x, y in zip(x_values, y_values)
            if math.isfinite(x) and math.isfinite(y) and x > 0.0
        ]
        if not rows or max(y for _, y in rows) <= 0.0:
            return None
        return [x for x, _ in rows], [y for _, y in rows]

    def _broaden_lines(
        self,
        frequencies: list[float],
        intensities: list[float],
        *,
        fwhm_cm1: float = 10.0,
    ) -> tuple[list[float], list[float]]:
        frequency_array = np.asarray(frequencies, dtype=float)
        intensity_array = np.asarray(intensities, dtype=float)
        lower = max(0.0, float(np.min(frequency_array)) - 80.0)
        upper = float(np.max(frequency_array)) + 80.0
        x = np.arange(math.floor(lower), math.ceil(upper) + 1.0, 1.0)
        sigma = max(fwhm_cm1 / 2.354820045, 0.25)
        y = np.zeros_like(x)
        for frequency, intensity in zip(frequency_array, intensity_array):
            y += intensity * np.exp(-0.5 * ((x - frequency) / sigma) ** 2)
        maximum = float(np.max(y))
        if maximum > 0.0:
            y /= maximum
        return x.tolist(), y.tolist()

    def _mode_prefilter_score(self, record: CandidateRecord, observed: SignalTrace) -> float:
        modes = self._number_list(record.metadata.get("modes_cm1", ""))
        modes = [mode for mode in modes if mode > 0.0]
        if not modes or len(observed.x) < 3:
            return 0.0
        y = np.asarray(observed.y, dtype=float)
        span = float(np.max(y) - np.min(y))
        normalized = ((y - float(np.min(y))) / span).tolist() if span > 0.0 else y.tolist()
        bands = sorted(
            detect_bands(SignalTrace(x=list(observed.x), y=normalized, kind=observed.kind)),
            key=lambda band: band.intensity,
            reverse=True,
        )[:12]
        return sum(
            max(0.0, 1.0 - min(abs(band.position - mode) for mode in modes) / 30.0) * max(band.intensity, 0.05)
            for band in bands
        )

    def _stream_json_items(self, handle):
        try:
            import ijson
        except ImportError:
            yield from json.load(handle)
            return
        yield from ijson.items(_NonFiniteJsonStream(handle), "item")

    def _index_is_current(self) -> bool:
        if self.indexed_count(SignalKind.FTIR) <= 0 or not self.index_state_path.exists():
            return False
        try:
            state = json.loads(self.index_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        stat = self.archive.path.stat()
        return state.get("size") == stat.st_size and state.get("mtime_ns") == stat.st_mtime_ns

    def _write_index_state(self) -> None:
        stat = self.archive.path.stat()
        self.index_state_path.write_text(
            json.dumps({"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}, indent=2),
            encoding="utf-8",
        )

    def _xml_path(self, jid: str) -> Path:
        if not re.fullmatch(r"JVASP-\d+", jid):
            raise ValueError(f"Invalid JARVIS identifier: {jid}")
        return self.xml_root / f"{jid}.xml"

    def _opener(self):
        context = ssl.create_default_context(cafile=certifi.where())
        return build_opener(HTTPSHandler(context=context))

    def _first_tag_text(self, root: ET.Element, tag: str) -> str:
        for node in root.iter():
            if self._local_tag(node.tag) == tag and node.text:
                return node.text.strip()
        return ""

    def _local_tag(self, tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    def _number_list(self, text: str) -> list[float]:
        values: list[float] = []
        for token in re.split(r"[,\s]+", text.strip(" '\"")):
            if not token:
                continue
            try:
                values.append(float(token))
            except ValueError:
                continue
        return values

    def _is_missing(self, value: object) -> bool:
        return value is None or str(value).strip().lower() in {"", "na", "none", "null"}

    def _is_number(self, value: object) -> bool:
        try:
            return math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
