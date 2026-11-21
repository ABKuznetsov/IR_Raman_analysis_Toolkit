"""User-owned JSON reference library; the line index is not the source of truth."""
from __future__ import annotations

import json
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import uuid4

from finder_core.models import SignalKind
from vibrational_finder.models import spectrum_kind


_LIBRARY_FORMAT = "vibrational-user-library"
_LOCK = RLock()


def validate_reference_card(payload: object) -> dict:
    if not isinstance(payload, dict) or ("format" in payload and payload["format"] != "vibrational-reference"):
        raise ValueError("Expected a vibrational-reference JSON card.")
    metadata = payload.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        raise ValueError("Reference metadata must be a JSON object.")
    kind = payload.get("kind") or metadata.get("method")
    if not isinstance(kind, str) or spectrum_kind(kind) not in {SignalKind.RAMAN, SignalKind.FTIR}:
        raise ValueError("Set the reference kind to Raman or FTIR.")
    bands = payload.get("bands")
    if bands is None:
        bands = []
    if not isinstance(bands, list) or any(not isinstance(band, dict) for band in bands):
        raise ValueError("Reference bands must be a list of JSON objects.")
    has_bands = False
    for number, band in enumerate(bands, 1):
        if band.get("position_cm1") in (None, ""):
            continue
        for field in ("position_cm1", "intensity", "fwhm_cm1", "confidence_value"):
            value = band.get(field)
            if value in (None, ""):
                continue
            try:
                finite = not isinstance(value, bool) and isfinite(float(value))
            except (TypeError, ValueError, OverflowError):
                finite = False
            if not finite:
                raise ValueError(f"Band {number}: {field} must be a finite number.")
        has_bands = True
    profile = payload.get("profile")
    if profile is None:
        profile = {}
    if not isinstance(profile, dict):
        raise ValueError("The reference profile must contain x and y arrays.")
    x, y = profile.get("x", []), profile.get("y", [])
    if not isinstance(x, list) or not isinstance(y, list) or len(x) != len(y):
        raise ValueError("The reference profile must contain x and y arrays of equal length.")
    try:
        finite = all(not isinstance(value, bool) and isfinite(float(value)) for axis in (x, y) for value in axis)
    except (TypeError, ValueError, OverflowError):
        finite = False
    if not finite:
        raise ValueError("The reference profile must contain only finite numbers.")
    if not has_bands and len(x) < 2:
        raise ValueError("Add a spectrum or at least one valid band position.")
    return payload


def read_reference_card(path: Path) -> dict:
    return validate_reference_card(json.loads(path.read_text(encoding="utf-8-sig")))


def write_json_atomic(path: Path, payload: dict) -> None:
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        temporary.replace(path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class UserReferenceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "user_library.json"

    def _load(self) -> dict[str, dict]:
        try:
            document = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return {}
        if not isinstance(document, dict) or document.get("format") != _LIBRARY_FORMAT or document.get("version") != 1:
            raise ValueError("Unsupported user library JSON format.")
        entries = document.get("references")
        if not isinstance(entries, list):
            raise ValueError("The user library must contain a references list.")
        records: dict[str, dict] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
                raise ValueError("A user library entry has no valid ID.")
            if entry["id"] in records:
                raise ValueError(f"Duplicate user library ID: {entry['id']}")
            records[entry["id"]] = validate_reference_card(entry.get("payload"))
        return records

    def _write(self, records: dict[str, dict]) -> None:
        write_json_atomic(self.path, {
            "format": _LIBRARY_FORMAT, "version": 1,
            "references": [{"id": key, "payload": payload} for key, payload in records.items()],
        })

    def _collect(self) -> tuple[dict[str, dict], bool]:
        records = self._load()
        migrated = False
        for path in sorted(self.root.glob("*.vsref")):
            key = str(path.resolve())
            if key in records:
                continue
            try:
                records[key] = read_reference_card(path)
            except (OSError, ValueError):
                continue
            migrated = True
        return records, migrated

    def cards(self) -> dict[str, dict]:
        with _LOCK:
            records, migrated = self._collect()
            if migrated:
                self._write(records)
            return records

    def save(self, payload: dict, *, card_id: str | None = None) -> str:
        validate_reference_card(payload)
        with _LOCK:
            records, _ = self._collect()
            if card_id is not None and card_id not in records:
                raise ValueError("This reference no longer exists in the user library.")
            identifier = card_id or uuid4().hex
            records[identifier] = payload
            self._write(records)
            return identifier
