from __future__ import annotations

from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalKind
from vibrational_finder.services.reference_cache import ReferenceSpectrumCache


def test_reference_cache_searches_text_kind_and_elements(tmp_path) -> None:
    cache = ReferenceSpectrumCache(tmp_path)
    quartz = CandidateRecord(
        key="RRUFF:R040031:raman:test",
        source="RRUFF",
        entry_id="R040031",
        name="Quartz",
        formula="SiO2",
        kind=SignalKind.RAMAN,
        metadata={"description": "Raman reference"},
    )
    calcite = CandidateRecord(
        key="RRUFF:R040070:ftir:test",
        source="RRUFF",
        entry_id="R040070",
        name="Calcite",
        formula="CaCO3",
        kind=SignalKind.FTIR,
        metadata={"description": "Infrared reference"},
    )
    cache.upsert_records([quartz, calcite])

    assert cache.indexed_count() == 2
    assert cache.indexed_count(SignalKind.RAMAN) == 1
    assert cache.search(SourceQuery(text="quart", kind=SignalKind.RAMAN)) == [quartz]
    assert cache.search(SourceQuery(formula="Si O", kind=SignalKind.RAMAN)) == [quartz]
    assert cache.search(SourceQuery(formula="Ca O", kind=SignalKind.RAMAN)) == []
    assert cache.search(SourceQuery(formula="Ca O", kind=SignalKind.FTIR)) == [calcite]


def test_reference_cache_ranks_name_matches_before_metadata_matches(tmp_path) -> None:
    cache = ReferenceSpectrumCache(tmp_path)
    metadata_match = CandidateRecord(
        key="RRUFF:R1:raman:test",
        source="RRUFF",
        entry_id="R1",
        name="Monazite",
        formula="GdPO4",
        kind=SignalKind.RAMAN,
        metadata={"locality": "Quartz vein"},
    )
    name_match = CandidateRecord(
        key="RRUFF:R2:raman:test",
        source="RRUFF",
        entry_id="R2",
        name="Quartz",
        formula="SiO2",
        kind=SignalKind.RAMAN,
        metadata={},
    )
    cache.upsert_records([metadata_match, name_match])

    assert cache.search(SourceQuery(text="Quartz", kind=SignalKind.RAMAN)) == [name_match, metadata_match]
