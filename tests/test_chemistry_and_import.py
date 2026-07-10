from __future__ import annotations

from pathlib import Path

import pytest

from finder_core.chemistry import formula_contains_elements, parse_formula_elements
from finder_core.data_sources import SourceQuery
from finder_core.models import SignalKind
from finder_core.spectral_metadata import infer_orientation, infer_polarization
from vibrational_finder.io import load_xy_spectrum
from vibrational_finder.band_detection import BandDetectionOptions, detect_bands
from vibrational_finder.preprocessing import PreprocessingOptions, preprocess_spectrum
from vibrational_finder.services import CifStructureSource, FolderLibrarySource, UserLibrarySource


REAL_RAMAN_EXAMPLES = [
    ("Ca2Al2SiO7.txt", 2953, 100.0, 1500.0, 625.9),
    ("CaMoO4_Na2MoO4.txt", 1834, 100.0, 1000.0, 878.7),
    ("CaWO4_2Mo.txt", 2953, 100.0, 1500.0, 911.0),
    ("Dy2AlTaO7.txt", 2278, 100.0, 1200.0, 415.9),
    ("Er2AlTaO7.txt", 2278, 100.0, 1200.0, 490.8),
]


def test_formula_element_filter_matches_real_formulas() -> None:
    assert parse_formula_elements("CaCO3") == {"Ca", "C", "O"}
    assert formula_contains_elements("SiO2", "Si O")
    assert formula_contains_elements("CaCO3", {"Ca", "C", "O"})
    assert not formula_contains_elements("SiO2", "Ca")


def test_orientation_and_polarization_metadata_inference() -> None:
    assert infer_orientation("excellent_unoriented.zip") == "unoriented"
    assert infer_orientation("sample_single_crystal_xx.txt") == "oriented"
    assert infer_polarization("sample_unpolarized.txt") == "unpolarized"
    assert infer_polarization("sample_xx.txt") == "polarized"


def test_user_library_formula_query_uses_elements_not_substrings() -> None:
    source = UserLibrarySource(Path("examples/library.csv"))
    records = source.search(SourceQuery(kind=SignalKind.RAMAN, formula="Si O"))
    assert [record.name for record in records] == ["Quartz"]


def test_folder_library_indexes_real_raman_folder() -> None:
    source = FolderLibrarySource(Path("examples/real_raman"))
    records = source.search(SourceQuery(kind=SignalKind.RAMAN, formula="Ca W O"))
    assert [record.entry_id for record in records] == ["CaWO4_2Mo"]
    assert records[0].formula == "CaWO4"


def test_dft_folder_library_indexes_calculated_dat_spectrum() -> None:
    source = FolderLibrarySource(Path("examples/real_raman"), library_type="dft", source_name="DFT examples")
    records = source.search(SourceQuery(kind=SignalKind.RAMAN, formula="Y Al Nb O"))
    assert [record.entry_id for record in records] == ["raman_Y2AlNbO7_dft"]
    assert records[0].metadata["orientation"] == "calculated"
    assert records[0].metadata["polarization"] == "calculated"
    spectrum = source.load_spectrum(records[0])
    assert spectrum.source_path.endswith("raman_Y2AlNbO7_dft.dat")
    assert min(spectrum.x) == pytest.approx(89.10683)
    assert max(spectrum.x) == pytest.approx(997.04528)


def test_cif_structure_source_creates_ftir_hint_candidate() -> None:
    source = CifStructureSource(Path("examples/cif"))
    records = source.search(SourceQuery(kind=SignalKind.FTIR, formula="Y Al Nb O"))
    assert [record.entry_id for record in records] == ["Y2AlNbO7"]
    assert records[0].formula == "Y2 Al Nb O7"
    assert records[0].metadata["orientation"] == "not applicable"
    spectrum = source.load_spectrum(records[0])
    assert spectrum.kind == SignalKind.FTIR
    assert len(spectrum.x) == 2400
    assert "Al-O" in spectrum.record.metadata["assignments"]


def test_load_jcamp_dx_peak_table(tmp_path: Path) -> None:
    path = tmp_path / "spectrum.jdx"
    path.write_text(
        "\n".join(
            [
                "##TITLE=demo",
                "##XUNITS=1/CM",
                "##YUNITS=ABSORBANCE",
                "##PEAK TABLE=(XY..XY)",
                "100, 0.2",
                "200, 0.8",
                "##END=",
            ]
        ),
        encoding="utf-8",
    )
    spectrum = load_xy_spectrum(path, kind=SignalKind.FTIR)
    assert spectrum.x == pytest.approx([100, 200])
    assert spectrum.y == pytest.approx([0.2, 0.8])


def test_load_real_gelenite_raman_example() -> None:
    spectrum = load_xy_spectrum(Path("examples/observed_gelenite_raman.txt"), kind=SignalKind.RAMAN)
    assert len(spectrum.x) == 2953
    assert min(spectrum.x) == pytest.approx(100.0)
    assert max(spectrum.x) == pytest.approx(1500.0)

    processed = preprocess_spectrum(spectrum, PreprocessingOptions(smoothing_window=9, normalize="max"))
    bands = detect_bands(processed, BandDetectionOptions(min_prominence=0.04, min_distance_cm1=10.0))
    strongest = max(bands, key=lambda band: band.intensity)
    assert strongest.position == pytest.approx(616.5, abs=0.6)


@pytest.mark.parametrize(("filename", "points", "x_min", "x_max", "strongest_cm1"), REAL_RAMAN_EXAMPLES)
def test_load_real_raman_examples(filename: str, points: int, x_min: float, x_max: float, strongest_cm1: float) -> None:
    spectrum = load_xy_spectrum(Path("examples/real_raman") / filename, kind=SignalKind.RAMAN)
    assert len(spectrum.x) == points
    assert min(spectrum.x) == pytest.approx(x_min)
    assert max(spectrum.x) == pytest.approx(x_max)

    processed = preprocess_spectrum(spectrum, PreprocessingOptions(smoothing_window=9, normalize="max"))
    bands = detect_bands(processed, BandDetectionOptions(min_prominence=0.04, min_distance_cm1=10.0))
    strongest = max(bands, key=lambda band: band.intensity)
    assert strongest.position == pytest.approx(strongest_cm1, abs=0.7)
