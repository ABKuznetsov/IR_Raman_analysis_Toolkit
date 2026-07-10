from __future__ import annotations

from finder_core.data_sources import SourceQuery
from vibrational_finder.services.public_sources import NistWebBookSource, SpectraBaseSource, external_source_catalog


def test_external_source_catalog_contains_synthetic_and_computed_sources() -> None:
    catalog = external_source_catalog()

    assert "SDBS" in catalog
    assert "OpenSpecy" in catalog
    assert "JARVIS-DFT" in catalog
    assert "PhononDB" in catalog


def test_external_sources_build_search_urls() -> None:
    assert "Name=calcite" in NistWebBookSource().search_url(SourceQuery(text="calcite"))
    assert "Formula=CaCO3" in NistWebBookSource().search_url(SourceQuery(formula="CaCO3"))
    assert "query=calcium+carbonate" in SpectraBaseSource().search_url(SourceQuery(text="calcium carbonate"))
