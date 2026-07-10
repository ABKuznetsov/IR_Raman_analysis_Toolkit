from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import time

from finder_core.chemistry import parse_formula_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind


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
            connection.execute("delete from reference_spectra where source = ?", (source,))

    def clear_archive(self, archive: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "delete from reference_spectra where json_extract(metadata_json, '$.archive') = ?",
                (archive,),
            )

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

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.index_path)
        connection.row_factory = sqlite3.Row
        return connection
