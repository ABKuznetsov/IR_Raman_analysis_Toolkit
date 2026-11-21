from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import shutil
import sqlite3
import ssl
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.request import urlopen

import certifi
import numpy as np

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.band_detection import BandDetectionOptions, extract_reference_band_set
from vibrational_finder.models import ReferenceSpectrum
from vibrational_finder.preprocessing import preprocess_spectrum
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache


@dataclass(frozen=True, slots=True)
class ResearchPackage:
    key: str
    label: str
    url: str
    path: Path

    @property
    def is_cached(self) -> bool:
        return self.path.is_file()


def _axis(columns: list[str]) -> tuple[list[int], list[float]]:
    values: list[tuple[float, int]] = []
    for i, column in enumerate(columns):
        try:
            value = float(column)
        except ValueError:
            continue
        if math.isfinite(value):
            values.append((value, i))
    values.sort()
    x = [value for value, _ in values]
    if len(x) < 3 or len(set(x)) != len(x):
        raise ValueError("The file must contain distinct numeric Raman-shift columns.")
    return [i for _, i in values], x


class _ResearchRamanSource:
    name: str
    package_key: str
    package_label: str
    url: str
    filename: str
    license_notice: str
    band_recipe_version = "research-scipy-max-v1"

    def __init__(self, cache_root: str | Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root is not None else app_cache_dir() / self.name.lower()
        self.index_path = self.cache_root / "reference_index.sqlite"
        self.reference_cache: ReferenceSpectrumCache | None = None
        self.refresh_index()

    def available_libraries(self) -> list[ResearchPackage]:
        return [ResearchPackage(self.package_key, self.package_label, self.url, self.cache_root / self.filename)]

    def download_library(self, key: str | None = None) -> Path:
        package = self.available_libraries()[0]
        if key is not None and key != package.key:
            raise ValueError(f"Unknown {self.name} package: {key}")
        self.cache_root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.cache_root, suffix=".part", delete=False) as handle:
            partial = Path(handle.name)
        try:
            context = ssl.create_default_context(cafile=certifi.where())
            with urlopen(package.url, timeout=120, context=context) as response, partial.open("wb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
                size = getattr(response, "headers", {}).get("Content-Length")
                if size is not None and handle.tell() != int(size):
                    raise OSError("Incomplete dataset download.")
            self._validate_download(partial)
            partial.replace(package.path)
        finally:
            partial.unlink(missing_ok=True)
        # Rebuilding the index is a separate, explicit operation.
        self.index_path.unlink(missing_ok=True)
        self.refresh_index()
        return package.path

    def refresh_index(self) -> None:
        self.reference_cache = ReferenceSpectrumCache(self.cache_root) if self.index_path.is_file() else None

    def clear(self) -> None:
        self.available_libraries()[0].path.unlink(missing_ok=True)
        self.index_path.unlink(missing_ok=True)
        self.refresh_index()

    def indexed_count(self) -> int:
        if self.reference_cache is None:
            return 0
        with closing(sqlite3.connect(self.index_path)) as db:
            return int(db.execute("select count(*) from research_profiles").fetchone()[0])

    def indexed_band_count(self) -> int:
        cache = self.reference_cache
        return cache.indexed_band_reference_count(self.name, self.band_recipe_version) if cache else 0

    def clear_band_index(self) -> None:
        if self.reference_cache is not None:
            self.reference_cache.clear_band_index(self.name)

    def status_row(self) -> list[str]:
        package = self.available_libraries()[0]
        count = self.indexed_count()
        if count:
            state, text = "Indexed", f"{self.indexed_band_count():,} line-indexed references"
        elif package.is_cached:
            state, text = "Downloaded", "Use Build line index to make references searchable"
        else:
            state, text = "External", "Not downloaded; use Download / update"
        return [self.name, state, f"{text} • {self.license_notice}", str(count), "", str(self.cache_root)]

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        return self.reference_cache.search(query, sources=[self.name]) if self.reference_cache else []

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        cache = self.reference_cache
        if cache is None:
            raise FileNotFoundError(f"{self.name} is not indexed")
        with closing(sqlite3.connect(self.index_path)) as db:
            row = db.execute(
                "select axis.data, profiles.data from research_axis axis cross join research_profiles profiles "
                "where profiles.key = ?", (candidate.key,),
            ).fetchone()
        if row is None:
            raise KeyError(candidate.key)
        return ReferenceSpectrum(
            x=np.frombuffer(row[0], dtype="<f8").tolist(), y=np.frombuffer(row[1], dtype="<f4").tolist(),
            kind=SignalKind.RAMAN, name=candidate.name, record=candidate,
            band_set=cache.load_band_set(candidate.key, self.band_recipe_version),
        )

    def build_band_index(self) -> tuple[int, int]:
        package = self.available_libraries()[0]
        if not package.is_cached:
            raise FileNotFoundError(f"Download {self.name} first using Download / update.")
        indexed = skipped = 0
        with TemporaryDirectory(dir=self.cache_root, prefix="index-") as staging:
            cache = ReferenceSpectrumCache(staging)
            with closing(sqlite3.connect(cache.index_path)) as db, db:
                db.execute("create table research_axis (data blob not null)")
                db.execute("create table research_profiles (key text primary key, data blob not null)")
            points: list[float] | None = None
            records = []
            profiles = []
            band_sets = []

            def flush() -> None:
                cache.upsert_records(records)
                cache.upsert_band_sets(band_sets, self.band_recipe_version)
                with closing(sqlite3.connect(cache.index_path)) as db, db:
                    db.executemany("insert into research_profiles values (?, ?)", profiles)
                records.clear()
                profiles.clear()
                band_sets.clear()

            for record, x, y in self._spectra(package.path):
                values = np.asarray(y, dtype="<f4")
                if values.shape != (len(x),) or not np.all(np.isfinite(values)) or np.ptp(values) <= 0:
                    skipped += 1
                    continue
                if points is None:
                    points = x
                    with closing(sqlite3.connect(cache.index_path)) as db, db:
                        db.execute("insert into research_axis values (?)", (np.asarray(x, dtype="<f8").tobytes(),))
                reference = ReferenceSpectrum(x=x, y=values.tolist(), kind=SignalKind.RAMAN)
                bands = extract_reference_band_set(
                    preprocess_spectrum(reference), BandDetectionOptions(backend="scipy"), origin="experimental",
                )
                records.append(record)
                profiles.append((record.key, values.tobytes()))
                if bands.bands:
                    band_sets.append((record.key, bands))
                    indexed += 1
                else:
                    skipped += 1
                if len(records) >= 128:
                    flush()
            if records:
                flush()
            if points is None:
                raise ValueError(f"{self.name} contains no usable single-component Raman references.")
            cache.index_path.replace(self.index_path)
        self.refresh_index()
        return indexed, skipped

    def _record(self, identifier: str, name: str, formula: str = "", **metadata: str) -> CandidateRecord:
        return CandidateRecord(
            key=f"{self.name}:{identifier}", source=self.name, entry_id=identifier, name=name,
            formula=formula, kind=SignalKind.RAMAN,
            metadata={"origin": "experimental", "dataset": self.package_key, **metadata},
        )

    def _validate_download(self, path: Path) -> None:
        raise NotImplementedError

    def _spectra(self, path: Path) -> Iterator[tuple[CandidateRecord, list[float], list[float]]]:
        raise NotImplementedError


class RamanBenchSource(_ResearchRamanSource):
    name = "RamanBench"
    package_key = "water_quality_ions"
    package_label = "Water quality ions — Mendeley v3 (5 MB)"
    url = (
        "https://data.mendeley.com/public-files/datasets/cxf3zxsc3k/files/"
        "c9ab7163-89c2-4d53-b658-ba4d2d65de6a/file_downloaded"
    )
    filename = "water_quality_ions_v3.csv"
    license_notice = "Luciani et al., 10.17632/cxf3zxsc3k.3 • CC BY 4.0"

    @staticmethod
    def _schema(header: list[str]) -> tuple[list[int], list[float]]:
        if not header or header[0].strip() != "Spectra ID" or [
            field.split()[0].lower() for field in header[-3:]
        ] != ["nitrate", "nitrite", "sulphate"]:
            raise ValueError("Unexpected Water quality ions CSV schema.")
        columns, x = _axis(header[1:-3])
        if len(columns) != len(header) - 4:
            raise ValueError("The Water quality ions CSV has non-numeric Raman-shift columns.")
        return columns, x

    def _validate_download(self, path: Path) -> None:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            self._schema(next(csv.reader(handle), []))

    def _spectra(self, path: Path) -> Iterator[tuple[CandidateRecord, list[float], list[float]]]:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, [])
            columns, x = self._schema(header)
            for row in reader:
                if not row:
                    continue
                if len(row) != len(header):
                    raise ValueError("Incomplete row in the Water quality ions CSV.")
                concentrations = [float(value) for value in row[-3:]]
                present = [i for i, value in enumerate(concentrations) if value > 0]
                if len(present) != 1 or any(not math.isfinite(v) or v < 0 for v in concentrations):
                    continue
                i = present[0]
                name, formula = (("Nitrate", "NO3"), ("Nitrite", "NO2"), ("Sulphate", "SO4"))[i]
                yield self._record(row[0], name, formula, concentration_mg_l=f"{concentrations[i]:g}"), x, [
                    float(row[j + 1]) for j in columns
                ]


# Categorical ID order from the RamanBench MLROD metadata, for integer-labelled exports.
_MLROD_LABELS = (
    "50% Forsterite / 50% Albite Mix", "50% Forsterite / 50% Augite Mix", "50% Quartz / 50% Albite Mix",
    "Amphibole - Hornblende", "Carbonate - Calcite", "Feldspar - Albite", "Feldspar - Anorthite",
    "Feldspar - Microcline", "Granite slab - 50% dust", "Mica - Biotite", "Mica - Muscovite",
    "Olivine - Forsterite", "Pyroxene - Augite", "Pyroxene - Enstatite", "Quartz", "Sulfate - Gypsum",
)
# Use nominal formulas only for well-defined minerals. Labels such as biotite and
# hornblende are mineral groups, not measured stoichiometries.
_MLROD_FORMULAS = {
    "Carbonate - Calcite": "CaCO3",
    "Feldspar - Albite": "NaAlSi3O8",
    "Feldspar - Anorthite": "CaAl2Si2O8",
    "Feldspar - Microcline": "KAlSi3O8",
    "Olivine - Forsterite": "Mg2SiO4",
    "Pyroxene - Enstatite": "MgSiO3",
    "Quartz": "SiO2",
    "Sulfate - Gypsum": "CaSO4·2H2O",
}


class MlrodSource(_ResearchRamanSource):
    name = "MLROD"
    package_key = "mlrod"
    package_label = "Minerals and mixtures — research mirror (1.45 GB)"
    url = (
        "https://huggingface.co/datasets/HTW-KI-Werkstatt/RamanBench/resolve/main/"
        "mlrod/data/train-00000-of-00001.parquet"
    )
    filename = "mlrod.parquet"
    license_notice = "Berlanga et al., 10.48667/yv5q-2606 • CC BY-NC"

    def _validate_download(self, path: Path) -> None:
        with path.open("rb") as handle:
            if handle.read(4) != b"PAR1" or path.stat().st_size < 12:
                raise ValueError("The MLROD download is not a Parquet file.")
            handle.seek(-4, 2)
            if handle.read(4) != b"PAR1":
                raise ValueError("The MLROD Parquet download is incomplete.")

    def _spectra(self, path: Path) -> Iterator[tuple[CandidateRecord, list[float], list[float]]]:
        try:
            from pyarrow.parquet import ParquetFile
        except ImportError as exc:
            raise RuntimeError(
                "MLROD indexing requires PyArrow. Install the project's [research] extra in the Python environment "
                "used to run IR/Raman Phase Finder."
            ) from exc
        parquet = ParquetFile(path)
        try:
            names = parquet.schema_arrow.names
            label_column = next((key for key in ("target", "label") if key in names), None)
            if label_column is None:
                raise ValueError("The MLROD Parquet file has no target or label column.")
            columns, x = _axis(names)
            spectrum_names = [names[i] for i in columns]
            offset = 0
            for batch in parquet.iter_batches(batch_size=512, columns=[label_column, *spectrum_names]):
                labels = batch.column(batch.schema.get_field_index(label_column)).to_pylist()
                spectra = np.column_stack([
                    batch.column(batch.schema.get_field_index(name)).to_numpy(zero_copy_only=False)
                    for name in spectrum_names
                ])
                for i, label in enumerate(labels):
                    label = str(label).strip()
                    if label.isdecimal() and int(label) < len(_MLROD_LABELS):
                        label = _MLROD_LABELS[int(label)]
                    if label not in _MLROD_LABELS or "%" in label:
                        continue
                    name = label.rsplit(" - ", 1)[-1]
                    yield self._record(str(offset + i), name, _MLROD_FORMULAS.get(label, ""), label=label), x, spectra[i].tolist()
                offset += len(labels)
        finally:
            parquet.close()
