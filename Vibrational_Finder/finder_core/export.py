from __future__ import annotations

import csv
from pathlib import Path


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
