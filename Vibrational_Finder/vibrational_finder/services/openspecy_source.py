from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import ssl
import urllib.request

from finder_core.cache import app_cache_dir
from finder_core.chemistry import formula_contains_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum


OPENSPECY_LIBRARIES = {
    "derivative": ("https://osf.io/download/2qbkt/", "derivative.rds"),
    "nobaseline": ("https://osf.io/download/jy7zk/", "nobaseline.rds"),
    "raw": ("https://osf.io/download/kzv3n/", "raw.rds"),
    "medoid_derivative": ("https://osf.io/download/2dmwu/", "medoid_derivative.rds"),
    "medoid_nobaseline": ("https://osf.io/download/8f3sg/", "medoid_nobaseline.rds"),
    "model_derivative": ("https://osf.io/download/s5bmh/", "model_derivative.rds"),
    "model_nobaseline": ("https://osf.io/download/v4abf/", "model_nobaseline.rds"),
}


@dataclass(frozen=True, slots=True)
class OpenSpecyLibraryInfo:
    key: str
    url: str
    filename: str
    path: Path

    @property
    def label(self) -> str:
        return self.key.replace("_", " ")

    @property
    def is_cached(self) -> bool:
        return self.path.exists()


class OpenSpecyLibrarySource:
    name = "OpenSpecy"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / "openspecy"
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._records: list[CandidateRecord] = []
        self._decoder_error = ""
        self._rds_cache: dict[str, dict] = {}
        self._ssl_context = self._create_ssl_context()
        self.refresh_index()

    def available_libraries(self) -> list[OpenSpecyLibraryInfo]:
        return [
            OpenSpecyLibraryInfo(
                key=key,
                url=url,
                filename=filename,
                path=self.cache_root / filename,
            )
            for key, (url, filename) in OPENSPECY_LIBRARIES.items()
        ]

    def cached_library_keys(self) -> list[str]:
        return [info.key for info in self.available_libraries() if info.is_cached]

    def download_library(self, key: str = "derivative") -> Path:
        libraries = {info.key: info for info in self.available_libraries()}
        if key not in libraries:
            raise ValueError(f"Unknown OpenSpecy library: {key}")
        info = libraries[key]
        info.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = info.path.with_suffix(info.path.suffix + ".part")
        request_kwargs = {"timeout": 120}
        if self._ssl_context is not None:
            request_kwargs["context"] = self._ssl_context
        with urllib.request.urlopen(info.url, **request_kwargs) as response:
            with tmp_path.open("wb") as handle:
                shutil.copyfileobj(response, handle)
        tmp_path.replace(info.path)
        self.refresh_index()
        return info.path

    def clear(self) -> None:
        for info in self.available_libraries():
            info.path.unlink(missing_ok=True)
            info.path.with_suffix(info.path.suffix + ".part").unlink(missing_ok=True)
        self._records = []
        self._decoder_error = ""
        self._rds_cache = {}

    def status_row(self) -> list[str]:
        cached = self.cached_library_keys()
        size = sum(info.path.stat().st_size for info in self.available_libraries() if info.path.exists())
        if self._records:
            status = "Indexed"
            detail = f"{len(self._records)} spectra; {', '.join(cached)}"
        elif cached:
            status = "Downloaded"
            suffix = f"; decoder missing: {self._decoder_error}" if self._decoder_error else "; not indexed"
            detail = f"{', '.join(cached)}{suffix}"
        else:
            status = "External"
            detail = "Open FTIR/Raman library; use Download / update to cache .rds files"
        return [self.name, status, f"{detail}; {size / (1024 * 1024):.1f} MB", str(self.cache_root)]

    def refresh_index(self) -> None:
        self._records = []
        self._decoder_error = ""
        self._rds_cache = {}
        cached = [info for info in self.available_libraries() if info.is_cached]
        if not cached:
            return
        for info in cached:
            try:
                self._records.extend(self._records_from_rds(info))
            except Exception as exc:
                self._decoder_error = str(exc)

    def _records_from_rds(self, info: OpenSpecyLibraryInfo) -> list[CandidateRecord]:
        result = self._load_rds(info.path)
        records: list[CandidateRecord] = []
        if self._is_openspecy_object(result):
            metadata = result["metadata"]
            columns = {str(column).lower(): column for column in metadata.columns}
            sample_column = _first_column(columns, ["sample_name", "col_id"])
            id_column = _first_column(columns, ["spectrumid", "library_id", "object_id", "id", "sample_name"])
            name_column = _first_column(columns, ["spectrum_identity", "spectrumidentity", "material", "sample_name"])
            formula_column = _first_column(columns, ["ideal_chemistry", "molform", "formula", "chemical_formula"])
            type_column = _first_column(columns, ["spectrum_type", "spectrumtype", "type"])
            class_column = _first_column(columns, ["material_class", "librarytype", "source_class"])
            source_column = _first_column(columns, ["organization", "source", "citation"])
            if sample_column is None or id_column is None or name_column is None:
                return records
            for index, row in metadata.iterrows():
                spectrum_type = _clean_value(row.get(type_column, "") if type_column is not None else "")
                kind = self._kind_from_text(spectrum_type)
                entry_id = _clean_value(row.get(id_column, f"{info.key}-{index}"))
                sample_name = _clean_value(row.get(sample_column, entry_id))
                name = _clean_value(row.get(name_column, entry_id)) or entry_id
                formula = _clean_value(row.get(formula_column, "") if formula_column is not None else "")
                material_class = _clean_value(row.get(class_column, "") if class_column is not None else "")
                source_text = _clean_value(row.get(source_column, "") if source_column is not None else "")
                records.append(
                    CandidateRecord(
                        key=f"OpenSpecy:{info.key}:{sample_name}:{kind.value}",
                        source=self.name,
                        entry_id=entry_id,
                        name=name,
                        formula=formula,
                        kind=kind,
                        metadata={
                            "library": info.key,
                            "sample_name": sample_name,
                            "material_class": material_class,
                            "description": source_text,
                            "path": str(info.path),
                            "quality": "OpenSpecy reference",
                        },
                    )
                )
            return records

        for object_name, frame in result.items():
            if not hasattr(frame, "iterrows"):
                continue
            records.extend(self._records_from_frame(info, object_name, frame))
        return records

    def _records_from_frame(self, info: OpenSpecyLibraryInfo, object_name: object, frame) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        columns = {str(column).lower(): column for column in frame.columns}
        id_column = _first_column(columns, ["library_id", "object_id", "id", "spectrumid"])
        name_column = _first_column(columns, ["spectrumidentity", "spectrum_identity", "sample_name", "name", "material"])
        formula_column = _first_column(columns, ["formula", "chemical_formula", "ideal_chemistry", "molform"])
        type_column = _first_column(columns, ["spectrumtype", "spectrum_type", "spectype", "type"])
        if id_column is None or name_column is None:
            return records
        for index, row in frame.iterrows():
            spectrum_type = _clean_value(row.get(type_column, "") if type_column is not None else "")
            kind = self._kind_from_text(spectrum_type)
            entry_id = _clean_value(row.get(id_column, f"{object_name}-{index}"))
            name = _clean_value(row.get(name_column, entry_id))
            formula = _clean_value(row.get(formula_column, "") if formula_column is not None else "")
            records.append(
                CandidateRecord(
                    key=f"OpenSpecy:{info.key}:{entry_id}:{kind.value}",
                    source=self.name,
                    entry_id=entry_id,
                    name=name,
                    formula=formula,
                    kind=kind,
                    metadata={
                        "library": info.key,
                        "object": str(object_name),
                        "sample_name": entry_id,
                        "path": str(info.path),
                        "quality": "OpenSpecy reference",
                    },
                )
            )
        return records

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        text = query.text.strip().lower()
        results = []
        for record in self._records:
            if query.kind != SignalKind.UNKNOWN and record.kind not in {query.kind, SignalKind.UNKNOWN}:
                continue
            haystack = " ".join([record.name, record.formula, record.entry_id, record.source]).lower()
            if text and text not in haystack:
                continue
            if query.formula and record.formula and not formula_contains_elements(record.formula, query.formula):
                continue
            results.append(record)
        return results

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        path = Path(candidate.metadata.get("path", ""))
        if not path.exists():
            raise FileNotFoundError(str(path))
        result = self._load_rds(path)
        if not self._is_openspecy_object(result):
            raise NotImplementedError("OpenSpecy RDS object does not expose wavenumber/spectra arrays.")
        sample_name = candidate.metadata.get("sample_name", "")
        spectra = result["spectra"]
        if sample_name not in spectra.columns:
            raise KeyError(f"OpenSpecy spectrum column not found: {sample_name}")
        x_values = list(result["wavenumber"])
        y_values = list(spectra[sample_name])
        clean_xy = [
            (float(x), float(y))
            for x, y in zip(x_values, y_values, strict=False)
            if _is_number(x) and _is_number(y)
        ]
        if not clean_xy:
            raise ValueError("OpenSpecy spectrum contains no numeric x/y values")
        x, y = zip(*clean_xy, strict=False)
        spectrum = ReferenceSpectrum(
            x=list(x),
            y=list(y),
            kind=candidate.kind,
            name=candidate.name,
            source_path=str(path),
            record=candidate,
        )
        return spectrum

    def load_candidates(self, query: SourceQuery | None = None) -> list[CompoundCandidate]:
        query = query or SourceQuery()
        candidates: list[CompoundCandidate] = []
        for record in self.search(query):
            try:
                reference = self.load_spectrum(record)
            except Exception:
                reference = None
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

    def _create_ssl_context(self):
        try:
            import certifi
        except Exception:
            return None
        return ssl.create_default_context(cafile=certifi.where())

    def _load_rds(self, path: Path) -> dict:
        cache_key = str(path)
        if cache_key in self._rds_cache:
            return self._rds_cache[cache_key]
        try:
            import rdata

            result = rdata.conversion.convert(rdata.parser.parse_file(path))
            if isinstance(result, dict):
                self._rds_cache[cache_key] = result
                return result
        except Exception:
            pass
        try:
            import pyreadr  # type: ignore[import-not-found]

            result = dict(pyreadr.read_r(str(path)))
            self._rds_cache[cache_key] = result
            return result
        except Exception as exc:
            raise ValueError(f"Could not read OpenSpecy RDS: {exc}") from exc

    def _is_openspecy_object(self, result: dict) -> bool:
        return all(key in result for key in ("wavenumber", "spectra", "metadata"))

    def _kind_from_text(self, text: str) -> SignalKind:
        lowered = text.lower()
        if "ftir" in lowered or lowered == "ir" or "infrared" in lowered:
            return SignalKind.FTIR
        if "raman" in lowered:
            return SignalKind.RAMAN
        return SignalKind.UNKNOWN


def _first_column(columns: dict[str, object], candidates: list[str]):
    for candidate in candidates:
        if candidate.lower() in columns:
            return columns[candidate.lower()]
    return None


def _clean_value(value: object) -> str:
    try:
        if value is None or value != value:
            return ""
    except Exception:
        pass
    text = str(value).strip()
    if text in {"<NA>", "nan", "NaN", "None"}:
        return ""
    return text


def _is_number(value: object) -> bool:
    try:
        number = float(value)
    except Exception:
        return False
    return number == number
