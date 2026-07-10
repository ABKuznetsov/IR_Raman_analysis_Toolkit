from __future__ import annotations

import zipfile

from finder_core.data_sources import SourceQuery
from finder_core.models import SignalKind
from vibrational_finder.services.rruff_source import RruffSource


def test_rruff_source_indexes_local_zip(tmp_path) -> None:
    archive_path = tmp_path / "fair_oriented.zip"
    member = "Quartz__R040031__Raman__514__fair_oriented.txt"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            member,
            "##NAMES=Quartz\n"
            "##RRUFFID=R040031\n"
            "##IDEAL CHEMISTRY=SiO_2_\n"
            "##RAMAN WAVELENGTH=514\n"
            "100 0\n110 1\n120 0\n",
        )

    source = RruffSource(tmp_path)
    records = source.search(SourceQuery(text="Quartz", kind=SignalKind.RAMAN))

    assert len(records) == 1
    assert records[0].source == "RRUFF"
    assert records[0].entry_id == "R040031"
    assert records[0].formula == "SiO2"
    assert records[0].metadata["laser_nm"] == "514"
    assert source.search(SourceQuery(formula="Si O", kind=SignalKind.RAMAN)) == records
    assert source.search(SourceQuery(formula="Ca O", kind=SignalKind.RAMAN)) == []

    spectrum = source.load_spectrum(records[0])
    assert spectrum.kind == SignalKind.RAMAN
    assert spectrum.x == [100.0, 110.0, 120.0]
    assert spectrum.y == [0.0, 1.0, 0.0]
