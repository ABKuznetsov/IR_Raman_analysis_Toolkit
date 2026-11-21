from __future__ import annotations

from dataclasses import dataclass, field
import json
from urllib.parse import urljoin

from vibrational_finder.services.remote_catalog_source import MAX_ENTRIES, _profile, catalog_url
from vibrational_finder.services.rest_library_source import (
    RestFieldMapping,
    _axis,
    _field,
    _record_formula,
    _record_id,
    _record_kind,
    _record_name,
    _records,
    _target,
)


MAX_PREVIEW_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_RECORDS = 25


@dataclass(frozen=True, slots=True)
class MappingRow:
    record: int | None
    field: str
    path: str
    level: str
    detail: str


@dataclass(slots=True)
class MappingPreview:
    rows: list[MappingRow] = field(default_factory=list)
    total_records: int = 0
    checked_records: int = 0
    invalid_records: int = 0
    unchecked_profiles: int = 0


def _parse_sample(text: str) -> tuple[object, MappingRow | None]:
    if not text.strip():
        return None, MappingRow(None, "JSON", "", "error", "Paste a JSON response first.")
    if len(text) > MAX_PREVIEW_BYTES or len(text.encode("utf-8", errors="surrogatepass")) > MAX_PREVIEW_BYTES:
        return None, MappingRow(None, "JSON", "", "error", "Paste a smaller sample (at most 2 MiB).")
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        detail = f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        return None, MappingRow(None, "JSON", "", "error", detail)
    except (ValueError, RecursionError) as exc:
        return None, MappingRow(None, "JSON", "", "error", f"Cannot parse JSON: {exc}")


def check_rest_profile(text: str, *, x_path: str, y_path: str) -> list[MappingRow]:
    """Validate X/Y in a pasted profile response, independently of any records or URL."""
    profile, error = _parse_sample(text)
    if error is not None:
        return [error]
    try:
        mapping = RestFieldMapping(x_path=x_path, y_path=y_path)
    except ValueError as exc:
        return [MappingRow(None, "Mapping", "", "error", str(exc))]
    return _profile_rows(None, profile, mapping)


def check_rest_mapping(text: str, mapping: RestFieldMapping, *, endpoint: str = "") -> MappingPreview:
    """Inspect a pasted response; never resolve a URL or touch the cache."""
    report = MappingPreview()
    page, error = _parse_sample(text)
    if error is not None:
        report.rows.append(error)
        return report

    try:
        endpoint = catalog_url(endpoint, allow_query=True) if endpoint.strip() else ""
    except ValueError as exc:
        report.rows.append(MappingRow(None, "Endpoint", "", "error", str(exc)))
        endpoint = ""
    try:
        records = _records(page, mapping)
    except ValueError as exc:
        report.rows.append(MappingRow(None, "Records array", mapping.records_path or "(root)", "error", str(exc)))
        return report
    report.total_records = len(records)
    array_path = mapping.records_path or "(root)"
    if len(records) > MAX_ENTRIES:
        detail = f"Found {len(records):,} records; the import limit is {MAX_ENTRIES:,}."
        report.rows.append(MappingRow(None, "Records array", array_path, "error", detail))
    else:
        report.rows.append(MappingRow(None, "Records array", array_path, "ok", f"{len(records):,} records found."))

    if mapping.next_path:
        next_link = _field(page, mapping.next_path)
        if next_link is None or next_link == "":
            report.rows.append(MappingRow(None, "Next page", mapping.next_path, "optional", "No next-page URL."))
        else:
            _link_row(report, None, "Next page", mapping.next_path, endpoint, next_link, next_page=True)

    seen: set[tuple[str, str]] = set()
    for index, record in enumerate(records[:MAX_PREVIEW_RECORDS], start=1):
        first_row = len(report.rows)
        if not isinstance(record, dict):
            report.rows.append(MappingRow(index, "Record", "", "error", "Expected a JSON object."))
        else:
            identifier = _value_row(report, index, "ID", mapping.id_path, _record_id, record, mapping)
            _value_row(report, index, "Name", mapping.name_path, _record_name, record, mapping)
            _value_row(report, index, "Formula", mapping.formula_path, _record_formula, record, mapping)
            kind = _value_row(report, index, "Type", mapping.kind_path or "(fixed)", _record_kind, record, mapping)
            if identifier is not None and kind is not None:
                key = identifier, kind
                if key in seen:
                    report.rows.append(MappingRow(index, "ID", mapping.id_path, "error", f"Duplicate {kind} ID: {identifier}."))
                seen.add(key)
            link = _field(record, mapping.profile_path) if mapping.profile_path else None
            if link is not None and link != "":
                valid = _link_row(report, index, "Profile link", mapping.profile_path, endpoint, link)
                report.unchecked_profiles += int(valid)
                for label, path in (("X", mapping.x_path), ("Y", mapping.y_path)):
                    report.rows.append(MappingRow(index, label, path, "unchecked", "The linked profile was not loaded."))
            else:
                if mapping.profile_path:
                    report.rows.append(MappingRow(index, "Profile link", mapping.profile_path, "optional", "Using arrays in this record."))
                report.rows.extend(_profile_rows(index, record, mapping))
        report.checked_records += 1
        report.invalid_records += any(row.level == "error" for row in report.rows[first_row:])
    return report


def _value_row(report, index, label, path, read, record, mapping) -> str | None:
    try:
        value = read(record, mapping)
    except ValueError as exc:
        report.rows.append(MappingRow(index, label, path, "error", str(exc)))
        return None
    report.rows.append(MappingRow(index, label, path, "ok" if value else "optional", value or "Not provided."))
    return value


def _link_row(report, index, label, path, endpoint, link, *, next_page=False) -> bool:
    try:
        if endpoint:
            url = _target(endpoint, link)
            if next_page and url == endpoint:
                raise ValueError("Next-page URL would create a pagination loop.")
        else:
            if not isinstance(link, str) or not link.strip():
                raise ValueError("Expected a URL string.")
            catalog_url(urljoin("https://offline.invalid/", link.strip()), allow_query=True)
    except ValueError as exc:
        report.rows.append(MappingRow(index, label, path, "error", str(exc)))
        return False
    detail = "Link found; not followed."
    if not endpoint:
        detail += " Add an endpoint to check the origin."
    report.rows.append(MappingRow(index, label, path, "unchecked", detail))
    return True


def _profile_rows(index: int | None, record: object, mapping: RestFieldMapping) -> list[MappingRow]:
    rows: list[MappingRow] = []
    coordinates = {}
    for label, path in (("X", mapping.x_path), ("Y", mapping.y_path)):
        try:
            values = _axis(record, path)
        except ValueError as exc:
            rows.append(MappingRow(index, label, path, "error", str(exc)))
        else:
            coordinates[label.lower()] = values
            rows.append(MappingRow(index, label, path, "ok", f"{len(values):,} points."))
    if len(coordinates) == 2:
        try:
            _profile(coordinates)
        except ValueError as exc:
            rows.append(MappingRow(index, "Profile", f"{mapping.x_path} / {mapping.y_path}", "error", str(exc)))
    return rows
