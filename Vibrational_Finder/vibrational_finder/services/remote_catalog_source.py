from __future__ import annotations

from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import ssl
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import parse_qsl, urljoin, urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, Request, build_opener

import certifi

from finder_core.cache import app_cache_dir
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind, SignalTrace
from vibrational_finder.band_detection import BandDetectionOptions, extract_reference_band_set
from vibrational_finder.models import CompoundCandidate, ReferenceSpectrum, SpectralBand
from vibrational_finder.preprocessing import preprocess_spectrum
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache
from vibrational_finder.services.research_raman_source import ResearchPackage
from vibrational_finder.services.staged_search import StagedReferenceSearchService


SCHEMA = "ir-raman-library/v1"
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024
MAX_ENTRIES = 2000
MAX_PROFILE_LINKS = 250
MAX_POINTS = 100_000


def catalog_url(value: str, *, allow_query: bool = False) -> str:
    url = value.strip()
    try:
        parts = urlsplit(url)
        if parts.port is not None and not 0 < parts.port < 65536:
            raise ValueError
        if (
            len(url) > 2048 or parts.scheme != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or (parts.query and not allow_query) or parts.fragment
            or any(char.isspace() or ord(char) <= 32 for char in url)
            or "\\" in url
        ):
            raise ValueError
        if allow_query and any(
            key.casefold() in {"key", "api_key", "apikey", "token", "access_token", "password", "secret"}
            for key, _ in parse_qsl(parts.query, keep_blank_values=True)
        ):
            raise ValueError
    except ValueError:
        detail = "credentials or fragment" if allow_query else "credentials, query, or fragment"
        raise ValueError(f"Enter a direct HTTPS URL without {detail}.") from None
    return parts._replace(netloc=parts.netloc.lower(), path=parts.path or "/").geturl()


def _origin(url: str) -> tuple[str, int]:
    parts = urlsplit(url)
    return parts.hostname or "", parts.port or 443


def url_library_name(url: str) -> str:
    return f"URL: {urlsplit(url).hostname} · {hashlib.sha256(url.encode()).hexdigest()[:12]}"


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Catalog URLs must serve data directly without redirects.")


def _open_https(url: str, context: ssl.SSLContext):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "IR-Raman-Phase-Finder"})
    return build_opener(HTTPSHandler(context=context), _NoRedirects()).open(request, timeout=20)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 200:
        raise ValueError(f"Catalog field '{field}' must be nonempty text (max 200 characters).")
    return value.strip()


def _profile(value: object) -> tuple[list[float], list[float]]:
    if not isinstance(value, dict):
        raise ValueError("Each profile must be a JSON object with x and y arrays.")
    x, y = value.get("x"), value.get("y")
    if not isinstance(x, list) or not isinstance(y, list) or not 3 <= len(x) == len(y) <= MAX_POINTS:
        raise ValueError(f"Profile x and y must contain 3–{MAX_POINTS:,} paired points.")
    try:
        if any(type(v) not in (int, float) or not math.isfinite(float(v)) for row in (x, y) for v in row):
            raise ValueError
    except (OverflowError, ValueError):
        raise ValueError("Profile coordinates must be finite numbers.") from None
    if x[0] > x[-1]:
        x, y = x[::-1], y[::-1]
    if any(a >= b for a, b in zip(x, x[1:])):
        raise ValueError("Profile x must be strictly monotonic in cm⁻¹.")
    return x, y


class RemoteCatalogSource:
    """Versioned JSON library with explicit HTTPS sync and entirely local matching."""

    band_recipe_version = "remote-catalog-scipy-v1"
    cache_namespace = "remote_libraries"
    package_label = "JSON catalog"
    allow_query = False

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = catalog_url(url, allow_query=self.allow_query)
        identifier = hashlib.sha256(self.url.encode()).hexdigest()
        self.cache_root = app_cache_dir() / self.cache_namespace / identifier
        self.snapshot_path = self.cache_root / "catalog.json"
        self.index_path = self.cache_root / "reference_index.sqlite"
        self.reference_cache: ReferenceSpectrumCache | None = None
        self.refresh_index()

    def available_libraries(self) -> list[ResearchPackage]:
        return [ResearchPackage("catalog", self.package_label, self.url, self.snapshot_path)]

    def _fetch_catalog(self, read):
        return read(self.url)

    def download_library(self, key: str | None = None) -> Path:
        if key not in (None, "catalog"):
            raise ValueError("Unknown remote catalog package.")
        context = ssl.create_default_context(cafile=certifi.where())
        remaining = MAX_DOWNLOAD_BYTES

        def read(url: str) -> object:
            nonlocal remaining
            with _open_https(url, context) as response:
                payload = response.read(remaining + 1)
            remaining -= len(payload)
            if remaining < 0:
                raise ValueError("Catalog and profiles exceed the 32 MiB download limit.")
            try:
                return json.loads(payload)
            except (ValueError, RecursionError) as exc:
                raise ValueError("Expected a JSON catalog or profile at the supplied URL.") from exc

        catalog = self._fetch_catalog(read)
        if not isinstance(catalog, dict) or catalog.get("schema") != SCHEMA:
            raise ValueError(f"Expected catalog schema '{SCHEMA}'.")
        title = _required_text(catalog.get("title"), "title")
        version = _required_text(catalog.get("version"), "version")
        license_name = _required_text(catalog.get("license"), "license")
        entries = catalog.get("entries")
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_ENTRIES:
            raise ValueError(f"Catalog must contain 1–{MAX_ENTRIES:,} entries.")
        normalized = []
        seen = set()
        links = 0
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Each catalog entry must be an object.")
            entry_id = _required_text(entry.get("id"), "id")
            name = _required_text(entry.get("name"), "name")
            kind = entry.get("kind")
            if kind not in ("raman", "ftir"):
                raise ValueError(f"Entry {entry_id}: kind must be 'raman' or 'ftir'.")
            if (entry_id, kind) in seen:
                raise ValueError(f"Duplicate {kind} entry ID: {entry_id}.")
            seen.add((entry_id, kind))
            formula = entry.get("formula", "")
            if not isinstance(formula, str) or len(formula) > 200:
                raise ValueError(f"Entry {entry_id}: formula must be text.")
            data = entry
            if "profile" in entry:
                if "x" in entry or "y" in entry:
                    raise ValueError(f"Entry {entry_id}: use either x/y or a profile link.")
                links += 1
                if links > MAX_PROFILE_LINKS:
                    raise ValueError(f"Catalog contains more than {MAX_PROFILE_LINKS} profile links.")
                link = catalog_url(urljoin(self.url, _required_text(entry["profile"], "profile")))
                if _origin(link) != _origin(self.url):
                    raise ValueError("Profile links must use the same origin as the catalog.")
                data = read(link)
            try:
                x, y = _profile(data)
            except ValueError as exc:
                raise ValueError(f"Entry {entry_id}: {exc}") from exc
            normalized.append({"id": entry_id, "name": name, "kind": kind, "formula": formula.strip(), "x": x, "y": y})

        self.cache_root.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=self.cache_root, suffix=".part", mode="w", encoding="utf-8", delete=False) as handle:
            partial = Path(handle.name)
        try:
            with partial.open("w", encoding="utf-8") as handle:
                json.dump({"title": title, "version": version, "license": license_name, "entries": normalized},
                          handle, separators=(",", ":"), allow_nan=False)
            partial.replace(self.snapshot_path)
        finally:
            partial.unlink(missing_ok=True)
        return self.snapshot_path

    def refresh_index(self) -> None:
        self.reference_cache = ReferenceSpectrumCache(self.cache_root) if self.index_path.is_file() else None

    def indexed_count(self) -> int:
        return self.reference_cache.indexed_count(source=self.name) if self.reference_cache else 0

    def status_row(self) -> list[str]:
        count = self.indexed_count()
        if count:
            with closing(sqlite3.connect(self.index_path)) as db:
                title, version, snapshot_mtime = db.execute("select * from catalog_revision").fetchone()
            pending = self.snapshot_path.is_file() and self.snapshot_path.stat().st_mtime_ns != snapshot_mtime
            state, detail = "Indexed", f"{title} · v{version}"
            if pending:
                detail += " · Update downloaded; build to switch version"
        elif self.snapshot_path.is_file():
            state, detail = "Downloaded", "Build line index to use this library in search"
        else:
            state, detail = "External", "Not downloaded; use Download / update"
        return [self.name, state, detail, str(count), "", self.url]

    def clear(self) -> None:
        self.snapshot_path.unlink(missing_ok=True)
        self.clear_band_index()

    def clear_band_index(self) -> None:
        self.index_path.unlink(missing_ok=True)
        self.refresh_index()

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        return self.reference_cache.search(query, sources=[self.name], limit=MAX_ENTRIES) if self.reference_cache else []

    def search_by_bands(
        self, query: SourceQuery, _observed: SignalTrace | None = None, *,
        observed_bands: list[SpectralBand] | None = None, limit: int = 80,
    ) -> list[CandidateRecord]:
        cache = self.reference_cache
        if cache is None:
            return []
        strongest = sorted(observed_bands or (), key=lambda band: band.intensity, reverse=True)[:24]
        records = cache.search_by_bands(
            query, [band.position for band in strongest], sources=[self.name],
            recipe_version=self.band_recipe_version, limit=limit,
        )
        return records or cache.search(query, sources=[self.name], limit=limit)

    def load_candidates(
        self, query: SourceQuery, *, observed: SignalTrace | None = None,
        observed_bands: list[SpectralBand] | None = None, limit: int = 80,
    ) -> list[CompoundCandidate]:
        records = self.search_by_bands(query, observed, observed_bands=observed_bands, limit=limit)
        return StagedReferenceSearchService([self]).load_candidates(records)

    def load_spectrum(self, candidate: CandidateRecord) -> ReferenceSpectrum:
        cache = self.reference_cache
        if cache is None or candidate.source != self.name:
            raise KeyError(candidate.key)
        with closing(sqlite3.connect(self.index_path)) as db:
            row = db.execute("select profile from catalog_profiles where key = ?", (candidate.key,)).fetchone()
        if row is None:
            raise KeyError(candidate.key)
        x, y = json.loads(row[0])
        return ReferenceSpectrum(x=x, y=y, kind=candidate.kind, name=candidate.name, record=candidate,
                                 band_set=cache.load_band_set(candidate.key, self.band_recipe_version))

    def build_band_index(self) -> tuple[int, int]:
        if not self.snapshot_path.is_file():
            raise FileNotFoundError("Download the catalog first using Download / update.")
        mtime = self.snapshot_path.stat().st_mtime_ns
        with self.snapshot_path.open(encoding="utf-8") as handle:
            snapshot = json.load(handle)
        with TemporaryDirectory(dir=self.cache_root, prefix="index-") as staging:
            cache = ReferenceSpectrumCache(staging)
            records = []
            band_sets = []
            with closing(sqlite3.connect(cache.index_path)) as db, db:
                db.execute("create table catalog_revision (title text, version text, snapshot_mtime integer)")
                db.execute("insert into catalog_revision values (?, ?, ?)", (snapshot["title"], snapshot["version"], mtime))
                db.execute("create table catalog_profiles (key text primary key, profile text not null)")
                for item in snapshot["entries"]:
                    kind = SignalKind(item["kind"])
                    record = CandidateRecord(
                        key=f"{self.name}:{item['id']}:{kind.value}", source=self.name, entry_id=item["id"],
                        name=item["name"], formula=item["formula"], kind=kind,
                        metadata={
                            "dataset_version": snapshot["version"], "library_title": snapshot["title"],
                            "license": snapshot["license"],
                        },
                    )
                    reference = ReferenceSpectrum(x=item["x"], y=item["y"], kind=kind)
                    bands = extract_reference_band_set(
                        preprocess_spectrum(reference), BandDetectionOptions(backend="scipy"), origin="experimental",
                    )
                    db.execute("insert into catalog_profiles values (?, ?)",
                               (record.key, json.dumps((reference.x, reference.y), separators=(",", ":"))))
                    records.append(record)
                    if bands.bands:
                        band_sets.append((record.key, bands))
            cache.upsert_records(records)
            cache.upsert_band_sets(band_sets, self.band_recipe_version)
            cache.index_path.replace(self.index_path)
        self.refresh_index()
        return len(records), 0
