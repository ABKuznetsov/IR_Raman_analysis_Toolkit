from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus

from finder_core.data_sources import SourceQuery
from finder_core.models import CandidateRecord, SignalTrace


@dataclass(frozen=True, slots=True)
class ExternalSourceInfo:
    key: str
    name: str
    homepage: str
    status: str
    details: str
    supports_direct_search: bool = False


class ExternalSearchSource:
    name = "External Search"
    homepage = ""

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        raise NotImplementedError(f"{self.name} is an external search link, not an automatic Finder source.")

    def load_spectrum(self, candidate: CandidateRecord) -> SignalTrace:
        raise NotImplementedError(f"{self.name} spectra must be downloaded manually and imported.")

    def search_url(self, query: SourceQuery) -> str:
        return self.homepage


class SdbsSource(ExternalSearchSource):
    name = "SDBS"
    homepage = "https://sdbs.db.aist.go.jp"

    def search_url(self, query: SourceQuery) -> str:
        return self.homepage


class SpectraBaseSource(ExternalSearchSource):
    name = "SpectraBase"
    homepage = "https://spectrabase.com"

    def search_url(self, query: SourceQuery) -> str:
        text = _query_text(query)
        return f"https://spectrabase.com/search?query={quote_plus(text)}" if text else self.homepage


class NistWebBookSource(ExternalSearchSource):
    name = "NIST Chemistry WebBook"
    homepage = "https://webbook.nist.gov/chemistry"

    def search_url(self, query: SourceQuery) -> str:
        text = _query_text(query)
        if not text:
            return self.homepage
        parameter = "Formula" if any(char.isdigit() for char in text) else "Name"
        return f"https://webbook.nist.gov/cgi/cbook.cgi?{parameter}={quote_plus(text)}&Units=SI"


def external_source_catalog() -> dict[str, ExternalSourceInfo]:
    return {
        "SDBS": ExternalSourceInfo(
            key="SDBS",
            name="SDBS",
            homepage=SdbsSource.homepage,
            status="External",
            details="Manual Raman/FTIR web search; AIST does not provide a digital bulk library.",
        ),
        "SpectraBase": ExternalSourceInfo(
            key="SpectraBase",
            name="SpectraBase",
            homepage=SpectraBaseSource.homepage,
            status="External",
            details="Manual public/subscription search; no redistributable bulk connector.",
            supports_direct_search=True,
        ),
        "NIST": ExternalSourceInfo(
            key="NIST",
            name="NIST",
            homepage=NistWebBookSource.homepage,
            status="External",
            details="Manual per-compound IR search with JCAMP-DX download; no bulk connector.",
            supports_direct_search=True,
        ),
    }


def external_source_by_key(key: str) -> ExternalSearchSource:
    sources: dict[str, ExternalSearchSource] = {
        "SDBS": SdbsSource(),
        "SpectraBase": SpectraBaseSource(),
        "NIST": NistWebBookSource(),
    }
    if key not in sources:
        raise KeyError(key)
    return sources[key]


def _query_text(query: SourceQuery) -> str:
    return query.text.strip() or query.formula.strip()
