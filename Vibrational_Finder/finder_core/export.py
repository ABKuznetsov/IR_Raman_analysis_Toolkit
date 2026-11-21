from __future__ import annotations

import csv
from pathlib import Path

from finder_core.models import SignalTrace


def write_match_table(path: str | Path, rows: list[dict[str, object]]) -> None:
    target = Path(path)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_spectrum_csv(path: str | Path, spectrum: SignalTrace) -> None:
    target = Path(path)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([f"wavenumber_{spectrum.x_unit}", f"intensity_{spectrum.y_unit}"])
        writer.writerows(zip(spectrum.x, spectrum.y))


def write_spectrum_jcamp(path: str | Path, spectrum: SignalTrace) -> None:
    target = Path(path)
    data_type = "RAMAN SPECTRUM" if spectrum.kind.value == "raman" else "INFRARED SPECTRUM"
    with target.open("w", newline="\n", encoding="ascii", errors="replace") as handle:
        handle.write(f"##TITLE={spectrum.name or target.stem}\n")
        handle.write("##JCAMP-DX=5.01\n")
        handle.write(f"##DATA TYPE={data_type}\n")
        handle.write("##XUNITS=1/CM\n")
        handle.write("##YUNITS=ARBITRARY UNITS\n")
        handle.write(f"##NPOINTS={min(len(spectrum.x), len(spectrum.y))}\n")
        handle.write("##XYDATA=(X++(Y..Y))\n")
        for x_value, y_value in zip(spectrum.x, spectrum.y):
            handle.write(f"{float(x_value):.10g}, {float(y_value):.10g}\n")
        handle.write("##END=\n")
