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


class PlannedOnlineSource:
    name = "Planned Source"
    homepage = ""

    def search(self, query: SourceQuery) -> list[CandidateRecord]:
        raise NotImplementedError(f"{self.name} connector is planned but not implemented yet.")

    def load_spectrum(self, candidate: CandidateRecord) -> SignalTrace:
        raise NotImplementedError(f"{self.name} connector is planned but not implemented yet.")

    def search_url(self, query: SourceQuery) -> str:
        return self.homepage


class RruffSource(PlannedOnlineSource):
    name = "RRUFF"
    homepage = "https://rruff.info"


class SdbsSource(PlannedOnlineSource):
    name = "SDBS"
    homepage = "https://sdbs.db.aist.go.jp"

    def search_url(self, query: SourceQuery) -> str:
        return self.homepage


class OpenSpecySource(PlannedOnlineSource):
    name = "OpenSpecy"
    homepage = "https://www.openspecy.org"


class SpectraBaseSource(PlannedOnlineSource):
    name = "SpectraBase"
    homepage = "https://spectrabase.com"

    def search_url(self, query: SourceQuery) -> str:
        text = _query_text(query)
        return f"https://spectrabase.com/search?query={quote_plus(text)}" if text else self.homepage


class NistWebBookSource(PlannedOnlineSource):
    name = "NIST Chemistry WebBook"
    homepage = "https://webbook.nist.gov/chemistry"

    def search_url(self, query: SourceQuery) -> str:
        text = _query_text(query)
        if not text:
            return self.homepage
        parameter = "Formula" if any(char.isdigit() for char in text) else "Name"
        return f"https://webbook.nist.gov/cgi/cbook.cgi?{parameter}={quote_plus(text)}&Units=SI"


class JarvisDftSource(PlannedOnlineSource):
    name = "JARVIS-DFT"
    homepage = "https://jarvis.nist.gov/"

    def search_url(self, query: SourceQuery) -> str:
        return "https://jarvis.nist.gov/jarvisdft/"


class MaterialsProjectPhononSource(PlannedOnlineSource):
    name = "Materials Project phonons"
    homepage = "https://materialsproject.org/"


class PhononDbSource(PlannedOnlineSource):
    name = "PhononDB"
    homepage = "https://phonondb.mtl.kyoto-u.ac.jp/"


class NomadSource(PlannedOnlineSource):
    name = "NOMAD"
    homepage = "https://nomad-lab.eu/"

    def search_url(self, query: SourceQuery) -> str:
        return "https://nomad-lab.eu/prod/v1/gui/search/entries"


def external_source_catalog() -> dict[str, ExternalSourceInfo]:
    return {
        "SDBS": ExternalSourceInfo(
            key="SDBS",
            name="SDBS",
            homepage=SdbsSource.homepage,
            status="External",
            details="Synthetic organic chemicals; Raman and FTIR web search.",
        ),
        "OpenSpecy": ExternalSourceInfo(
            key="OpenSpecy",
            name="OpenSpecy",
            homepage=OpenSpecySource.homepage,
            status="External",
            details="Open FTIR/Raman workflow for polymers, plastics and environmental spectra.",
        ),
        "SpectraBase": ExternalSourceInfo(
            key="SpectraBase",
            name="SpectraBase",
            homepage=SpectraBaseSource.homepage,
            status="External",
            details="Wiley spectral database; public/subscription access.",
            supports_direct_search=True,
        ),
        "NIST": ExternalSourceInfo(
            key="NIST",
            name="NIST",
            homepage=NistWebBookSource.homepage,
            status="External",
            details="Chemistry WebBook IR/vibrational data; access rules apply.",
            supports_direct_search=True,
        ),
        "JARVIS-DFT": ExternalSourceInfo(
            key="JARVIS-DFT",
            name="JARVIS-DFT",
            homepage=JarvisDftSource.homepage,
            status="External",
            details="Computed inorganic materials; infrared intensities and phonon-related properties.",
        ),
        "Materials Project": ExternalSourceInfo(
            key="Materials Project",
            name="Materials Project",
            homepage=MaterialsProjectPhononSource.homepage,
            status="External",
            details="Computed material entries; future phonon/structure bridge.",
        ),
        "PhononDB": ExternalSourceInfo(
            key="PhononDB",
            name="PhononDB",
            homepage=PhononDbSource.homepage,
            status="External",
            details="Computed phonon database for inorganic crystals.",
        ),
        "NOMAD": ExternalSourceInfo(
            key="NOMAD",
            name="NOMAD",
            homepage=NomadSource.homepage,
            status="External",
            details="Materials science repository with APIs and uploaded datasets.",
        ),
    }


def external_source_by_key(key: str) -> PlannedOnlineSource:
    sources: dict[str, PlannedOnlineSource] = {
        "SDBS": SdbsSource(),
        "OpenSpecy": OpenSpecySource(),
        "SpectraBase": SpectraBaseSource(),
        "NIST": NistWebBookSource(),
        "JARVIS-DFT": JarvisDftSource(),
        "Materials Project": MaterialsProjectPhononSource(),
        "PhononDB": PhononDbSource(),
        "NOMAD": NomadSource(),
    }
    if key not in sources:
        raise KeyError(key)
    return sources[key]


def _query_text(query: SourceQuery) -> str:
    return query.text.strip() or query.formula.strip()
