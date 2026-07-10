from __future__ import annotations

import pandas as pd
import pyreadr

from finder_core.data_sources import SourceQuery
from finder_core.models import SignalKind
from vibrational_finder.services.openspecy_source import OpenSpecyLibrarySource


def test_openspecy_source_indexes_cached_rds_metadata(tmp_path) -> None:
    frame = pd.DataFrame(
        {
            "library_id": ["lib-1", "lib-2"],
            "SpectrumIdentity": ["Polyethylene", "Polystyrene"],
            "SpectrumType": ["FTIR", "Raman"],
        }
    )
    pyreadr.write_rds(str(tmp_path / "medoid_derivative.rds"), frame)

    source = OpenSpecyLibrarySource(tmp_path)
    records = source.search(SourceQuery())

    assert len(records) == 2
    assert records[0].source == "OpenSpecy"
    assert {record.kind for record in records} == {SignalKind.FTIR, SignalKind.RAMAN}
    assert source.search(SourceQuery(text="polyethylene"))[0].entry_id == "lib-1"
    assert source.status_row()[1] == "Indexed"
