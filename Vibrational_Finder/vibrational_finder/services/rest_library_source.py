from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urljoin, urlsplit

from vibrational_finder.services.remote_catalog_source import (
    MAX_ENTRIES,
    MAX_PROFILE_LINKS,
    SCHEMA,
    RemoteCatalogSource,
    _origin,
    _required_text,
    catalog_url,
)


MAX_PAGES = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class RestFieldMapping:
    records_path: str = "results"
    next_path: str = ""
    id_path: str = "id"
    name_path: str = "name"
    formula_path: str = "formula"
    kind_path: str = ""
    default_kind: str = "raman"
    x_path: str = "x"
    y_path: str = "y"
    profile_path: str = ""

    def __post_init__(self) -> None:
        for field in fields(RestFieldMapping):
            value = getattr(self, field.name)
            if not isinstance(value, str) or len(value.strip()) > 200:
                raise ValueError(f"Invalid REST configuration field: {field.name}.")
            value = value.strip()
            if field.name.endswith("_path") and value and any(not part.strip() for part in value.split(".")):
                raise ValueError(f"Invalid dotted path: {field.name}.")
            object.__setattr__(self, field.name, value)
        if not all((self.id_path, self.name_path, self.x_path, self.y_path)):
            raise ValueError("Map the ID, name, x, and y fields before connecting.")
        if self.default_kind not in ("raman", "ftir"):
            raise ValueError("Choose Raman or FTIR as the fixed kind.")


@dataclass(frozen=True, slots=True)
class RestConnection(RestFieldMapping):
    url: str
    title: str = ""
    license: str = ""

    def __post_init__(self) -> None:
        RestFieldMapping.__post_init__(self)
        for name in ("url", "title", "license"):
            value = getattr(self, name)
            maximum = 2048 if name == "url" else 200
            if not isinstance(value, str) or len(value.strip()) > maximum:
                raise ValueError(f"Invalid REST configuration field: {name}.")
            object.__setattr__(self, name, value.strip())
        object.__setattr__(self, "url", catalog_url(self.url, allow_query=True))

    @property
    def source_name(self) -> str:
        return f"REST: {urlsplit(self.url).hostname} · {sha256(self.url.encode()).hexdigest()[:12]}"


def _field(data: object, path: str) -> object:
    if path:
        for component in path.split("."):
            if not isinstance(data, dict):
                return None
            data = data.get(component)
    return data


def _target(base: str, link: object) -> str:
    if not isinstance(link, str) or not link.strip():
        raise ValueError("REST profile and next-page links must be URL strings.")
    url = catalog_url(urljoin(base, link.strip()), allow_query=True)
    if _origin(url) != _origin(base):
        raise ValueError("REST profile and next-page links must use the same origin as the endpoint.")
    return url


def _kind(value: object) -> str:
    label = value.strip().lower().replace("-", "").replace(" ", "") if isinstance(value, str) else ""
    if label == "raman":
        return "raman"
    if label in {"ftir", "ir", "infrared"}:
        return "ftir"
    raise ValueError("Mapped spectrum type must say Raman or FTIR.")


def _records(page: object, mapping: RestFieldMapping) -> list:
    result = _field(page, mapping.records_path)
    if not isinstance(result, list):
        message = f"REST result '{mapping.records_path or '(root)'}' is not an array."
        if isinstance(page, dict) and page:
            keys = ", ".join(str(key)[:60] for key in list(page)[:8])
            message += f" Top-level keys: {keys}."
        raise ValueError(message)
    return result


def _record_id(record: object, mapping: RestFieldMapping) -> str:
    identifier = _field(record, mapping.id_path)
    if type(identifier) is int:
        identifier = str(identifier)
    try:
        return _required_text(identifier, "id")
    except ValueError as exc:
        raise ValueError(f"ID at '{mapping.id_path}' must be nonempty text or an integer (max 200 characters).") from exc


def _record_name(record: object, mapping: RestFieldMapping) -> str:
    try:
        return _required_text(_field(record, mapping.name_path), "name")
    except ValueError as exc:
        raise ValueError(f"Name at '{mapping.name_path}' must be nonempty text (max 200 characters).") from exc


def _record_formula(record: object, mapping: RestFieldMapping) -> str:
    formula = _field(record, mapping.formula_path) if mapping.formula_path else None
    if formula is None:
        return ""
    if not isinstance(formula, str) or len(formula) > 200:
        raise ValueError(f"Formula at '{mapping.formula_path}' must be text (max 200 characters).")
    return formula.strip()


def _record_kind(record: object, mapping: RestFieldMapping) -> str:
    return _kind(_field(record, mapping.kind_path)) if mapping.kind_path else mapping.default_kind


def _axis(profile: object, path: str) -> list:
    coordinate = _field(profile, path)
    if not isinstance(coordinate, list):
        raise ValueError(f"Expected an array at '{path}'.")
    return coordinate


class RestLibrarySource(RemoteCatalogSource):
    """Read existing REST JSON and store it using the shared local index."""

    cache_namespace = "rest_libraries"
    package_label = "REST snapshot"
    allow_query = True

    def __init__(self, name: str, config: RestConnection) -> None:
        self.config = config
        super().__init__(name, config.url)

    def _fetch_catalog(self, read):
        config = self.config
        url = self.url
        visited: set[str] = set()
        entries = []
        links = 0
        while url:
            if url in visited:
                raise ValueError("REST pagination loop detected.")
            if len(visited) >= MAX_PAGES:
                raise ValueError(f"REST API exceeds {MAX_PAGES} pages. Narrow the endpoint query.")
            visited.add(url)
            page = read(url)
            records = _records(page, config)
            if len(entries) + len(records) > MAX_ENTRIES:
                raise ValueError(f"REST API exceeds {MAX_ENTRIES:,} entries. Narrow the endpoint query.")
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("Each REST record must be an object.")
                identifier = _record_id(record, config)
                name = _record_name(record, config)
                formula = _record_formula(record, config)
                kind = _record_kind(record, config)
                profile = record
                link = _field(record, config.profile_path) if config.profile_path else None
                if link is not None and link != "":
                    links += 1
                    if links > MAX_PROFILE_LINKS:
                        raise ValueError(f"REST API exceeds {MAX_PROFILE_LINKS} linked profiles. Narrow the query.")
                    profile = read(_target(url, link))
                entries.append({
                    "id": identifier, "name": name, "formula": formula,
                    "kind": kind, "x": _axis(profile, config.x_path), "y": _axis(profile, config.y_path),
                })
            next_link = _field(page, config.next_path) if config.next_path else None
            url = _target(url, next_link) if next_link is not None and next_link != "" else ""
        return {
            "schema": SCHEMA, "title": config.title or urlsplit(self.url).hostname,
            "version": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "license": config.license or "Not specified", "entries": entries,
        }
