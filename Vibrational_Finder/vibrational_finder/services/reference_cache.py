from __future__ import annotations

from pathlib import Path
import json
import math
from numbers import Real
import sqlite3
import time

from finder_core.chemistry import parse_formula_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.models import ReferenceBandSet, SpectralBand


class ReferenceSpectrumCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "reference_index.sqlite"
        self.root.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def upsert_records(self, records: list[CandidateRecord]) -> None:
        with self._connect() as connection:
            for record in records:
                self._upsert(connection, record)

    def clear_source(self, source: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "delete from reference_bands where reference_key in "
                "(select key from reference_spectra where source = ?)",
                (source,),
            )
            connection.execute("delete from reference_spectra where source = ?", (source,))

    def clear_archive(self, archive: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "delete from reference_bands where reference_key in "
                "(select key from reference_spectra where json_extract(metadata_json, '$.archive') = ?)",
                (archive,),
            )
            connection.execute(
                "delete from reference_spectra where json_extract(metadata_json, '$.archive') = ?",
                (archive,),
            )

    def delete_keys(self, keys: set[str] | list[str]) -> None:
        selected = [key for key in keys if key]
        if not selected:
            return
        placeholders = ", ".join("?" for _ in selected)
        with self._connect() as connection:
            connection.execute(f"delete from reference_bands where reference_key in ({placeholders})", selected)
            connection.execute(f"delete from reference_spectra where key in ({placeholders})", selected)

    def size_bytes(self) -> int:
        try:
            return self.index_path.stat().st_size
        except OSError:
            return 0

    def upsert_band_set(self, reference_key: str, band_set: ReferenceBandSet, recipe_version: str) -> None:
        with self._connect() as connection:
            self._upsert_band_set(connection, reference_key, band_set, recipe_version)

    def upsert_band_sets(
        self,
        items: list[tuple[str, ReferenceBandSet]],
        recipe_version: str,
    ) -> None:
        with self._connect() as connection:
            for reference_key, band_set in items:
                self._upsert_band_set(connection, reference_key, band_set, recipe_version)

    def _upsert_band_set(
        self,
        connection: sqlite3.Connection,
        reference_key: str,
        band_set: ReferenceBandSet,
        recipe_version: str,
    ) -> None:
        connection.execute("delete from reference_bands where reference_key = ?", (reference_key,))
        connection.executemany(
            """
            insert into reference_bands(
                reference_key, band_index, position, intensity, width, prominence,
                assignment, symmetry, confidence, origin, extraction_method,
                processing_json, recipe_version
            ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    reference_key,
                    index,
                    float(band.position),
                    float(band.intensity),
                    float(band.width),
                    float(band.prominence),
                    band.assignment,
                    band.symmetry,
                    float(band.confidence),
                    band_set.origin,
                    band_set.extraction_method,
                    json.dumps(band_set.processing_recipe, ensure_ascii=True, sort_keys=True),
                    recipe_version,
                )
                for index, band in enumerate(band_set.bands)
            ],
        )

    def load_band_set(self, reference_key: str, recipe_version: str = "") -> ReferenceBandSet | None:
        where = ["reference_key = ?"]
        params: list[object] = [reference_key]
        if recipe_version:
            where.append("recipe_version = ?")
            params.append(recipe_version)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                select position, intensity, width, prominence, assignment, symmetry,
                       confidence, origin, extraction_method, processing_json
                from reference_bands
                where {' and '.join(where)}
                order by band_index
                """,
                params,
            ).fetchall()
        if not rows:
            return None
        try:
            processing = json.loads(rows[0]["processing_json"] or "{}")
        except json.JSONDecodeError:
            processing = {}
        return ReferenceBandSet(
            bands=[
                SpectralBand(
                    position=float(row["position"]),
                    intensity=float(row["intensity"]),
                    width=float(row["width"]),
                    prominence=float(row["prominence"]),
                    assignment=row["assignment"],
                    symmetry=row["symmetry"],
                    confidence=float(row["confidence"]),
                )
                for row in rows
            ],
            origin=rows[0]["origin"],
            extraction_method=rows[0]["extraction_method"],
            processing_recipe=processing,
        )

    def load_band_sets(self, reference_keys: list[str], recipe_version: str = "") -> dict[str, ReferenceBandSet]:
        keys = list(dict.fromkeys(key for key in reference_keys if key))
        if not keys:
            return {}
        placeholders = ", ".join("?" for _ in keys)
        where = [f"reference_key in ({placeholders})"]
        params: list[object] = list(keys)
        if recipe_version:
            where.append("recipe_version = ?")
            params.append(recipe_version)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                select reference_key, position, intensity, width, prominence, assignment,
                       symmetry, confidence, origin, extraction_method, processing_json
                from reference_bands
                where {' and '.join(where)}
                order by reference_key, band_index
                """,
                params,
            ).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault(str(row["reference_key"]), []).append(row)
        result: dict[str, ReferenceBandSet] = {}
        for key, band_rows in grouped.items():
            try:
                processing = json.loads(band_rows[0]["processing_json"] or "{}")
            except json.JSONDecodeError:
                processing = {}
            result[key] = ReferenceBandSet(
                bands=[
                    SpectralBand(
                        position=float(row["position"]),
                        intensity=float(row["intensity"]),
                        width=float(row["width"]),
                        prominence=float(row["prominence"]),
                        assignment=row["assignment"],
                        symmetry=row["symmetry"],
                        confidence=float(row["confidence"]),
                    )
                    for row in band_rows
                ],
                origin=band_rows[0]["origin"],
                extraction_method=band_rows[0]["extraction_method"],
                processing_recipe=processing,
            )
        return result

    def indexed_band_reference_count(self, source: str = "", recipe_version: str = "") -> int:
        where = ["1 = 1"]
        params: list[object] = []
        if source:
            where.append("r.source = ?")
            params.append(source)
        if recipe_version:
            where.append("b.recipe_version = ?")
            params.append(recipe_version)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                select count(distinct b.reference_key)
                from reference_bands b
                join reference_spectra r on r.key = b.reference_key
                where {' and '.join(where)}
                """,
                params,
            ).fetchone()
        return int(row[0] if row else 0)

    def indexed_band_count(self, source: str = "", recipe_version: str = "") -> int:
        where = ["1 = 1"]
        params: list[object] = []
        if source:
            where.append("r.source = ?")
            params.append(source)
        if recipe_version:
            where.append("b.recipe_version = ?")
            params.append(recipe_version)
        with self._connect() as connection:
            row = connection.execute(
                f"""
                select count(*)
                from reference_bands b
                join reference_spectra r on r.key = b.reference_key
                where {' and '.join(where)}
                """,
                params,
            ).fetchone()
        return int(row[0] if row else 0)

    def indexed_band_keys(self, source: str = "", recipe_version: str = "") -> set[str]:
        where = ["1 = 1"]
        params: list[object] = []
        if source:
            where.append("r.source = ?")
            params.append(source)
        if recipe_version:
            where.append("b.recipe_version = ?")
            params.append(recipe_version)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                select distinct b.reference_key
                from reference_bands b
                join reference_spectra r on r.key = b.reference_key
                where {' and '.join(where)}
                """,
                params,
            ).fetchall()
        return {str(row[0]) for row in rows}

    def clear_band_index(self, source: str = "") -> None:
        with self._connect() as connection:
            if source:
                connection.execute(
                    "delete from reference_bands where reference_key in "
                    "(select key from reference_spectra where source = ?)",
                    (source,),
                )
            else:
                connection.execute("delete from reference_bands")

    def search_by_bands(
        self,
        query: SourceQuery,
        positions: list[float],
        *,
        tolerance_cm1: float = 20.0,
        sources: list[str] | None = None,
        recipe_version: str = "",
        limit: int = 200,
    ) -> list[CandidateRecord]:
        finite_positions = [
            float(position)
            for position in positions
            if isinstance(position, Real) and math.isfinite(float(position))
        ]
        if not finite_positions:
            return self.search(query, sources=sources, limit=limit)
        selected_positions = finite_positions[:80]
        where = ["1 = 1"]
        params: list[object] = []
        if query.kind != SignalKind.UNKNOWN:
            where.append("(r.kind = ? or r.kind = ?)")
            params.extend([query.kind.value, SignalKind.UNKNOWN.value])
        allowed_sources = [source for source in sources or [] if source]
        if allowed_sources:
            placeholders = ", ".join("?" for _ in allowed_sources)
            where.append(f"r.source in ({placeholders})")
            params.extend(allowed_sources)
        for element in sorted(parse_formula_elements(query.formula)):
            where.append("' ' || r.elements || ' ' like ?")
            params.append(f"% {element} %")
        text = query.text.strip().lower()
        if text:
            like_text = f"%{text}%"
            where.append(
                "(lower(r.entry_id) like ? or lower(r.name) like ? or "
                "lower(r.formula) like ? or lower(r.metadata_json) like ?)"
            )
            params.extend([like_text, like_text, like_text, like_text])
        if recipe_version:
            where.append("b.recipe_version = ?")
            params.append(recipe_version)
        query_band_sql = " union all ".join("select ? as query_index, ? as query_position" for _ in selected_positions)
        query_band_params: list[object] = []
        for index, position in enumerate(selected_positions):
            query_band_params.extend([index, position])
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                with query_bands as ({query_band_sql})
                select r.key, r.source, r.entry_id, r.name, r.formula, r.kind, r.metadata_json,
                       count(distinct q.query_index) as observed_hits,
                       count(distinct b.band_index) as band_hits,
                       min(abs(b.position - q.query_position)) as best_delta
                from reference_spectra r
                join reference_bands b on b.reference_key = r.key
                join query_bands q
                  on b.position between q.query_position - ? and q.query_position + ?
                where {' and '.join(where)}
                group by r.key
                order by observed_hits desc, band_hits desc, best_delta asc, r.updated_at desc
                limit ?
                """,
                (*query_band_params, tolerance_cm1, tolerance_cm1, *params, limit),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def indexed_count(self, kind: SignalKind | None = None, source: str = "") -> int:
        where = ["1 = 1"]
        params: list[object] = []
        if kind is not None and kind != SignalKind.UNKNOWN:
            where.append("kind = ?")
            params.append(kind.value)
        if source:
            where.append("source = ?")
            params.append(source)
        with self._connect() as connection:
            row = connection.execute(
                f"select count(*) from reference_spectra where {' and '.join(where)}",
                params,
            ).fetchone()
        return int(row[0] if row else 0)

    def search(self, query: SourceQuery, sources: list[str] | None = None, limit: int = 2000) -> list[CandidateRecord]:
        text = query.text.strip().lower()
        required = parse_formula_elements(query.formula)
        where = ["1 = 1"]
        params: list[object] = []
        if query.kind != SignalKind.UNKNOWN:
            where.append("(kind = ? or kind = ?)")
            params.extend([query.kind.value, SignalKind.UNKNOWN.value])
        allowed_sources = [source for source in sources or [] if source]
        if allowed_sources:
            placeholders = ", ".join("?" for _ in allowed_sources)
            where.append(f"source in ({placeholders})")
            params.extend(allowed_sources)
        for element in sorted(required):
            where.append("' ' || elements || ' ' like ?")
            params.append(f"% {element} %")
        if text:
            like_text = f"%{text}%"
            order_clause = (
                "case "
                "when lower(name) = ? then 0 "
                "when lower(entry_id) = ? then 1 "
                "when lower(formula) = ? then 2 "
                "when lower(name) like ? then 3 "
                "when lower(entry_id) like ? then 4 "
                "when lower(formula) like ? then 5 "
                "else 6 end, updated_at desc"
            )
            order_params: list[object] = [text, text, text, like_text, like_text, like_text]
            where.append(
                "("
                "lower(entry_id) like ? or "
                "lower(name) like ? or "
                "lower(formula) like ? or "
                "lower(source) like ? or "
                "lower(metadata_json) like ?"
                ")"
            )
            params.extend([like_text, like_text, like_text, like_text, like_text])
        else:
            order_clause = "updated_at desc"
            order_params = []
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                select key, source, entry_id, name, formula, kind, metadata_json
                from reference_spectra
                where {" and ".join(where)}
                order by {order_clause}
                limit ?
                """,
                (*params, *order_params, limit),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def _upsert(self, connection: sqlite3.Connection, record: CandidateRecord) -> None:
        metadata_json = json.dumps(record.metadata, ensure_ascii=True, sort_keys=True)
        elements = " ".join(sorted(parse_formula_elements(record.formula)))
        connection.execute(
            """
            insert into reference_spectra(
                key, source, entry_id, name, formula, kind, metadata_json, elements, updated_at
            )
            values(?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(key) do update set
                source = excluded.source,
                entry_id = excluded.entry_id,
                name = excluded.name,
                formula = excluded.formula,
                kind = excluded.kind,
                metadata_json = excluded.metadata_json,
                elements = excluded.elements,
                updated_at = excluded.updated_at
            """,
            (
                record.key,
                record.source,
                record.entry_id,
                record.name,
                record.formula,
                record.kind.value,
                metadata_json,
                elements,
                time.time(),
            ),
        )

    def _row_to_record(self, row: sqlite3.Row) -> CandidateRecord:
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except json.JSONDecodeError:
            metadata = {}
        return CandidateRecord(
            key=row["key"],
            source=row["source"],
            entry_id=row["entry_id"],
            name=row["name"],
            formula=row["formula"],
            kind=SignalKind(row["kind"]),
            metadata=metadata,
        )

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists reference_spectra (
                    key text primary key,
                    source text not null default '',
                    entry_id text not null default '',
                    name text not null default '',
                    formula text not null default '',
                    kind text not null default 'unknown',
                    metadata_json text not null default '{}',
                    elements text not null default '',
                    updated_at real not null
                )
                """
            )
            connection.execute("create index if not exists idx_reference_source on reference_spectra(source)")
            connection.execute("create index if not exists idx_reference_kind on reference_spectra(kind)")
            connection.execute("create index if not exists idx_reference_elements on reference_spectra(elements)")
            connection.execute(
                """
                create table if not exists reference_bands (
                    reference_key text not null,
                    band_index integer not null,
                    position real not null,
                    intensity real not null default 0,
                    width real not null default 0,
                    prominence real not null default 0,
                    assignment text not null default '',
                    symmetry text not null default '',
                    confidence real not null default 1,
                    origin text not null default 'experimental',
                    extraction_method text not null default '',
                    processing_json text not null default '{}',
                    recipe_version text not null default '',
                    primary key(reference_key, band_index)
                )
                """
            )
            connection.execute("create index if not exists idx_reference_bands_key on reference_bands(reference_key)")
            connection.execute("create index if not exists idx_reference_bands_position on reference_bands(position)")
            connection.execute("create index if not exists idx_reference_bands_recipe on reference_bands(recipe_version)")

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        return connection
