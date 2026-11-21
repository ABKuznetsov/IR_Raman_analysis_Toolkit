from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import cast

from finder_core.models import SignalKind, SignalTrace
from vibrational_finder.io.project_codec import decode_project_state, encode_project_state
from vibrational_finder.models import ObservedSpectrum, SpectralBand
from vibrational_finder.project_model import normalize_project_state, stable_spectrum_id
from vibrational_finder.project_state import ProjectUiState, VibrationalProjectState


PORTABLE_PROJECT_SUFFIX = ".irff"
PORTABLE_MANIFEST_NAME = "project.json"
PROJECT_FORMAT = "ir-raman-finder-project"
PROJECT_SCHEMA_VERSION = 1
MAX_ARCHIVE_MEMBERS = 10_000
MAX_MEMBER_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def _safe_member_stem(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return safe or "asset"


def _trace_payload(trace: SignalTrace) -> dict[str, object]:
    return {
        "x": [float(item) for item in trace.x],
        "y": [float(item) for item in trace.y],
        "kind": trace.kind.value,
        "name": trace.name,
        "source_path": trace.source_path,
        "x_unit": trace.x_unit,
        "y_unit": trace.y_unit,
    }


class _ZipAssetWriter:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive
        self.members_by_content: dict[tuple[str, str], str] = {}

    def store_trace(self, folder: str, key: str, trace: SignalTrace) -> str:
        payload = json.dumps(
            _trace_payload(trace),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        content_digest = hashlib.sha256(payload).hexdigest()
        content_key = (folder, content_digest)
        existing = self.members_by_content.get(content_key)
        if existing is not None:
            return existing
        key_digest = hashlib.sha256(str(key).encode("utf-8", errors="surrogatepass")).hexdigest()[:12]
        member = f"{folder}/{_safe_member_stem(str(key))}-{key_digest}.json"
        self.archive.writestr(member, payload)
        self.members_by_content[content_key] = member
        return member


class _ZipAssetReader:
    def __init__(self, archive: zipfile.ZipFile) -> None:
        self.archive = archive

    def load_trace(self, member: str, cls: type[SignalTrace]) -> SignalTrace:
        _validate_member_path(member, ("spectra/observed/", "spectra/processed/", "references/"))
        try:
            data = json.loads(self.archive.read(member).decode("utf-8-sig"))
        except KeyError as exc:
            raise ValueError(f"IRFF project is missing required asset: {member}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"IRFF trace asset must contain an object: {member}")
        try:
            kind = SignalKind(str(data.get("kind", SignalKind.UNKNOWN.value)))
            return cls(
                x=[float(item) for item in cast(list[object], data.get("x", []))],
                y=[float(item) for item in cast(list[object], data.get("y", []))],
                kind=kind,
                name=str(data.get("name", "")),
                source_path=str(data.get("source_path", "")),
                x_unit=str(data.get("x_unit", "cm-1")),
                y_unit=str(data.get("y_unit", "a.u.")),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"IRFF trace asset contains invalid values: {member}") from exc


def _validate_member_path(member: str, allowed_prefixes: tuple[str, ...]) -> PurePosixPath:
    raw_parts = member.split("/")
    member_path = PurePosixPath(member)
    if (
        not any(member.startswith(prefix) for prefix in allowed_prefixes)
        or "\\" in member
        or ":" in member
        or any(part in {"", ".", ".."} for part in raw_parts)
        or member_path.is_absolute()
        or not member_path.parts
    ):
        raise ValueError(f"Unsafe file path in IRFF project: {member}")
    return member_path


def _target_path(path: str | Path) -> Path:
    target = Path(path)
    if target.suffix.lower() != PORTABLE_PROJECT_SUFFIX:
        target = Path(f"{target}{PORTABLE_PROJECT_SUFFIX}")
    return target


def _validate_archive(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError(
            f"IRFF project contains too many members: {len(members)}; limit is {MAX_ARCHIVE_MEMBERS}."
        )
    names: set[str] = set()
    total_size = 0
    for info in members:
        if info.filename in names:
            raise ValueError(f"IRFF project contains duplicate archive member: {info.filename}")
        names.add(info.filename)
        if info.file_size > MAX_MEMBER_UNCOMPRESSED_BYTES:
            raise ValueError(
                f"IRFF project member exceeds the uncompressed size limit: {info.filename}"
            )
        total_size += info.file_size
        if total_size > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise ValueError("IRFF project exceeds the total uncompressed size limit.")


def save_project(state: VibrationalProjectState, path: str | Path) -> Path:
    target = _target_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.stem}.",
        suffix=".tmp",
        dir=target.parent,
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            writer = _ZipAssetWriter(archive)
            manifest = encode_project_state(state, writer)
            manifest["format"] = PROJECT_FORMAT
            manifest["schema_version"] = PROJECT_SCHEMA_VERSION
            archive.writestr(
                PORTABLE_MANIFEST_NAME,
                json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
            )
        with zipfile.ZipFile(temporary_path, mode="r") as archive:
            archive.getinfo(PORTABLE_MANIFEST_NAME)
            if archive.testzip() is not None:
                raise ValueError("IRFF project archive verification failed.")
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)
    return target


def load_project(path: str | Path) -> VibrationalProjectState:
    source = Path(path)
    if not zipfile.is_zipfile(source):
        return load_legacy_project(source)
    with zipfile.ZipFile(source, mode="r") as archive:
        _validate_archive(archive)
        try:
            manifest = json.loads(archive.read(PORTABLE_MANIFEST_NAME).decode("utf-8-sig"))
        except KeyError as exc:
            raise ValueError(f"IRFF project does not contain {PORTABLE_MANIFEST_NAME}.") from exc
        if not isinstance(manifest, dict):
            raise ValueError("IRFF project manifest must contain an object.")
        if manifest.get("format") != PROJECT_FORMAT:
            raise ValueError("This is not an IR/Raman Finder project.")
        version = manifest.get("schema_version")
        if version != PROJECT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported IRFF schema version: {version!r}.")
        return decode_project_state(manifest, _ZipAssetReader(archive))


def _legacy_observed(value: object, path: str) -> ObservedSpectrum:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object.")
    try:
        spectrum = ObservedSpectrum(
            x=[float(item) for item in cast(list[object], value.get("x", []))],
            y=[float(item) for item in cast(list[object], value.get("y", []))],
            kind=SignalKind(str(value.get("kind", SignalKind.UNKNOWN.value))),
            name=str(value.get("name", "")),
            source_path=str(value.get("source_path", "")),
            x_unit=str(value.get("x_unit", "cm-1")),
            y_unit=str(value.get("y_unit", "a.u.")),
        )
        spectrum.id = stable_spectrum_id("legacy-v1", path, spectrum.kind.value, spectrum.source_path)
        return spectrum
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} contains invalid spectrum values.") from exc


def _legacy_band(value: object, path: str) -> SpectralBand:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object.")
    assigned = value.get("assigned_candidate_keys", [])
    if not isinstance(assigned, list):
        raise ValueError(f"{path}.assigned_candidate_keys must be an array.")
    try:
        return SpectralBand(
            position=float(value.get("position", 0.0)),
            intensity=float(value.get("intensity", 0.0)),
            width=float(value.get("width", 0.0)),
            assigned_candidate_keys=[str(item) for item in assigned],
            prominence=float(value.get("prominence", 0.0)),
            mode=str(value.get("mode", "")),
            assignment=str(value.get("assignment", "")),
            symmetry=str(value.get("symmetry", "")),
            polarization=str(value.get("polarization", "")),
            orientation=str(value.get("orientation", "")),
            source_comment=str(value.get("source_comment", "")),
            confidence=float(value.get("confidence", 1.0)),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{path} contains invalid band values.") from exc


def load_legacy_project(path: str | Path) -> VibrationalProjectState:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("This is neither a valid IRFF nor a legacy IR/Raman project file.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Legacy IR/Raman project must contain an object.")
    if payload.get("format") != "ir-raman-phase-finder-project":
        raise ValueError("This is not a legacy IR/Raman Finder project.")
    if payload.get("version") != 1:
        raise ValueError(f"Unsupported legacy IR/Raman project version: {payload.get('version')!r}.")

    spectra = payload.get("spectra", {})
    if not isinstance(spectra, dict):
        raise ValueError("Legacy project spectra must be an object.")
    raw_raman = spectra.get("raman", [])
    raw_ftir = spectra.get("ftir", [])
    if not isinstance(raw_raman, list) or not isinstance(raw_ftir, list):
        raise ValueError("Legacy project spectrum collections must be arrays.")
    raman = [_legacy_observed(item, f"spectra.raman[{index}]") for index, item in enumerate(raw_raman)]
    ftir = [_legacy_observed(item, f"spectra.ftir[{index}]") for index, item in enumerate(raw_ftir)]

    raw_metadata = payload.get("sample_metadata", {})
    raw_bands = payload.get("sample_bands", {})
    raw_visible = payload.get("visible_observed_paths", [])
    display = payload.get("display", {})
    if not isinstance(raw_metadata, dict):
        raise ValueError("Legacy project sample_metadata must be an object.")
    if not isinstance(raw_bands, dict):
        raise ValueError("Legacy project sample_bands must be an object.")
    if not isinstance(raw_visible, list):
        raise ValueError("Legacy project visible_observed_paths must be an array.")
    if not isinstance(display, dict):
        raise ValueError("Legacy project display must be an object.")

    sample_metadata: dict[str, dict[str, str]] = {}
    for key, item in raw_metadata.items():
        if not isinstance(item, dict):
            raise ValueError(f"Legacy sample metadata for {key!r} must be an object.")
        sample_metadata[str(key)] = {str(field): str(field_value) for field, field_value in item.items()}
    sample_bands: dict[str, list[SpectralBand]] = {}
    for key, item in raw_bands.items():
        if not isinstance(item, list):
            raise ValueError(f"Legacy sample bands for {key!r} must be an array.")
        sample_bands[str(key)] = [
            _legacy_band(band, f"sample_bands[{key!r}][{index}]")
            for index, band in enumerate(item)
        ]

    originals = {
        spectrum.source_path: deepcopy(spectrum)
        for spectrum in [*raman, *ftir]
    }
    normalize = display.get("normalize", True)
    try:
        laser_nm = float(display.get("laser_nm", 532.0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Legacy project display.laser_nm must be numeric.") from exc
    state = VibrationalProjectState(
        active_spectrum_key=(
            str(payload["active_spectrum_key"])
            if payload.get("active_spectrum_key") is not None
            else None
        ),
        visible_observed_keys={str(item) for item in raw_visible},
        raman_spectra=raman,
        ftir_spectra=ftir,
        original_observed=originals,
        sample_metadata=sample_metadata,
        sample_bands=sample_bands,
        ui=ProjectUiState(
            display_mode=str(display.get("mode", "One")),
            normalization_mode="max" if bool(normalize) else "none",
            laser_nm=laser_nm,
        ),
    )
    return normalize_project_state(state)


def _extract_portable_member(
    archive: zipfile.ZipFile,
    member: str,
    root: Path,
    *,
    allowed_prefix: str,
) -> Path:
    member_path = _validate_member_path(member, (allowed_prefix,))
    resolved_root = root.resolve()
    target = resolved_root.joinpath(*member_path.parts).resolve()
    if target == resolved_root or resolved_root not in target.parents:
        raise ValueError(f"Unsafe file path in IRFF project: {member}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(member, mode="r") as source_stream, target.open("wb") as target_stream:
        while block := source_stream.read(1024 * 1024):
            target_stream.write(block)
    return target
