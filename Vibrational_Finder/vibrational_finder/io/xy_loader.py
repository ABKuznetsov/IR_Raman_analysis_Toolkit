from __future__ import annotations

from pathlib import Path
from importlib.util import find_spec
import re
import zipfile
import xml.etree.ElementTree as ET

import numpy as np

from finder_core.models import SignalKind
from vibrational_finder.io.autodetect import guess_spectrum_metadata
from vibrational_finder.models import ObservedSpectrum, ReferenceSpectrum, spectrum_kind


TEXT_SPECTRUM_SUFFIXES = {".txt", ".xy", ".csv", ".tsv", ".dat", ".asc", ".ascii", ".prn", ".dpt", ".txtr"}
JCAMP_SUFFIXES = {".jdx", ".dx"}
SPREADSHEET_SUFFIXES = {".xlsx"}
OPTIONAL_RAMANCHADA_SUFFIXES = {".spc", ".sp", ".spa", ".0", ".1", ".2", ".wdf", ".ngs", ".rruf", ".spe", ".cha"}


def supported_spectrum_extensions() -> tuple[str, ...]:
    return tuple(sorted(TEXT_SPECTRUM_SUFFIXES | JCAMP_SUFFIXES | SPREADSHEET_SUFFIXES | OPTIONAL_RAMANCHADA_SUFFIXES))


def ramanchada2_available() -> bool:
    try:
        return find_spec("ramanchada2") is not None
    except (ImportError, ValueError):
        return False


def _clean_xy(x_values, y_values) -> tuple[list[float], list[float]]:
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) == 0:
        return [], []
    order = np.argsort(x)
    x = x[order]
    y = y[order]
    unique_x, inverse = np.unique(x, return_inverse=True)
    if len(unique_x) == len(x):
        return x.tolist(), y.tolist()
    summed_y = np.zeros(len(unique_x), dtype=float)
    counts = np.zeros(len(unique_x), dtype=float)
    np.add.at(summed_y, inverse, y)
    np.add.at(counts, inverse, 1.0)
    return unique_x.tolist(), (summed_y / np.maximum(counts, 1.0)).tolist()


def _read_xy_text(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    rows: list[tuple[float, float]] = []
    for raw_line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";", "//")):
            continue
        if line.startswith("##"):
            continue
        parts = re.split(r"[\s,;]+", line)
        if len(parts) < 2:
            continue
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"No numeric x/y data found in {source}")
    data = np.asarray(rows, dtype=float)
    return _clean_xy(data[:, 0], data[:, 1])


def _metadata_value(lines: list[str], key: str) -> str:
    prefix = f"##{key.upper()}="
    for line in lines:
        if line.upper().startswith(prefix):
            return line.split("=", 1)[1].strip()
    return ""


def _metadata_float(lines: list[str], key: str, default: float) -> float:
    value = _metadata_value(lines, key)
    try:
        return float(value)
    except ValueError:
        return default


def _read_jcamp_dx(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    lines = [line.strip() for line in source.read_text(encoding="utf-8", errors="ignore").splitlines()]
    x_factor = _metadata_float(lines, "XFACTOR", 1.0)
    y_factor = _metadata_float(lines, "YFACTOR", 1.0)
    delta_x = _metadata_float(lines, "DELTAX", 0.0)
    rows: list[tuple[float, float]] = []
    in_xydata = False
    in_peak_table = False

    for line in lines:
        upper = line.upper()
        if upper.startswith("##XYDATA="):
            in_xydata = True
            in_peak_table = False
            continue
        if upper.startswith("##PEAK TABLE=") or upper.startswith("##PEAKTABLE="):
            in_peak_table = True
            in_xydata = False
            continue
        if upper.startswith("##"):
            in_xydata = False
            in_peak_table = False
            continue
        if not line or line.startswith(("$$", "#", ";")):
            continue

        numbers = [float(value) for value in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][-+]?\d+)?", line)]
        if len(numbers) < 2:
            continue
        if in_xydata:
            x0 = numbers[0] * x_factor
            ys = [value * y_factor for value in numbers[1:]]
            step = delta_x if delta_x else 1.0
            rows.extend((x0 + index * step, y) for index, y in enumerate(ys))
        elif in_peak_table or len(numbers) == 2:
            rows.append((numbers[0] * x_factor, numbers[1] * y_factor))

    if not rows:
        raise ValueError(f"No JCAMP-DX x/y data found in {source}")
    data = np.asarray(rows, dtype=float)
    return _clean_xy(data[:, 0], data[:, 1])


def _read_ramanchada2(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    try:
        from ramanchada2.spectrum import from_local_file
    except Exception as exc:
        raise ValueError(
            f"Format {source.suffix or source.name!r} needs the optional ramanchada2 importer. "
            "Install the project with the 'formats' extra or export the spectrum as TXT/CSV/JCAMP-DX."
        ) from exc
    try:
        spectrum = from_local_file(str(source))
        x = np.asarray(spectrum.x, dtype=float)
        y = np.asarray(spectrum.y, dtype=float)
    except Exception as exc:
        raise ValueError(f"ramanchada2 could not decode {source.name}: {exc}") from exc
    finite = np.isfinite(x) & np.isfinite(y)
    x = x[finite]
    y = y[finite]
    if len(x) == 0:
        raise ValueError(f"No finite x/y values found in {source}")
    return _clean_xy(x, y)


def _xlsx_shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall(".//m:si", ns):
        parts = [node.text or "" for node in item.findall(".//m:t", ns)]
        values.append("".join(parts))
    return values


def _xlsx_cell_value(cell, shared_strings: list[str]) -> float | None:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    value_node = cell.find("m:v", ns)
    if value_node is None or value_node.text is None:
        return None
    text = value_node.text.strip()
    if cell.attrib.get("t") == "s":
        try:
            text = shared_strings[int(text)]
        except (IndexError, ValueError):
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_xlsx(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    rows: list[list[float]] = []
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    try:
        with zipfile.ZipFile(source) as zip_file:
            sheet_names = sorted(name for name in zip_file.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))
            if not sheet_names:
                raise ValueError(f"No worksheet found in {source}")
            shared_strings = _xlsx_shared_strings(zip_file)
            worksheet = ET.fromstring(zip_file.read(sheet_names[0]))
            for row in worksheet.findall(".//m:sheetData/m:row", ns):
                values = [
                    value
                    for cell in row.findall("m:c", ns)
                    for value in [_xlsx_cell_value(cell, shared_strings)]
                    if value is not None and np.isfinite(value)
                ]
                if len(values) >= 2:
                    rows.append(values)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"{source} is not a valid XLSX file") from exc
    if not rows:
        raise ValueError(f"No numeric x/y data found in {source}")
    column_count = max(len(row) for row in rows)
    best_pair: tuple[int, int] | None = None
    best_count = 0
    for x_column in range(column_count - 1):
        for y_column in range(x_column + 1, column_count):
            count = sum(len(row) > y_column for row in rows)
            if count > best_count:
                best_pair = (x_column, y_column)
                best_count = count
    if best_pair is None or best_count == 0:
        raise ValueError(f"No numeric x/y column pair found in {source}")
    x_column, y_column = best_pair
    data = np.asarray([(row[x_column], row[y_column]) for row in rows if len(row) > y_column], dtype=float)
    return _clean_xy(data[:, 0], data[:, 1])


def read_spectrum_xy(path: str | Path) -> tuple[list[float], list[float]]:
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix in SPREADSHEET_SUFFIXES:
        return _read_xlsx(source)
    if suffix in JCAMP_SUFFIXES:
        try:
            return _read_jcamp_dx(source)
        except ValueError:
            return _read_ramanchada2(source)
    if suffix in OPTIONAL_RAMANCHADA_SUFFIXES:
        return _read_ramanchada2(source)
    try:
        return _read_xy_text(source)
    except ValueError:
        if suffix in TEXT_SPECTRUM_SUFFIXES and ramanchada2_available():
            return _read_ramanchada2(source)
        raise


def load_xy_spectrum(
    path: str | Path,
    *,
    kind: str | SignalKind | None = None,
    name: str = "",
    reference: bool = False,
) -> ObservedSpectrum | ReferenceSpectrum:
    x, y = read_spectrum_xy(path)
    source = Path(path)
    resolved_kind = spectrum_kind(kind)
    guess = guess_spectrum_metadata(source, x=x, y=y, kind_hint=resolved_kind)
    if resolved_kind == SignalKind.UNKNOWN:
        resolved_kind = guess.kind
    kwargs = {
        "x": x,
        "y": y,
        "kind": resolved_kind,
        "name": name or source.stem,
        "source_path": str(source),
        "x_unit": guess.x_unit,
        "y_unit": guess.y_unit,
    }
    if reference:
        return ReferenceSpectrum(**kwargs)
    return ObservedSpectrum(**kwargs)
