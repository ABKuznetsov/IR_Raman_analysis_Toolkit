# IR/Raman Phase Finder

IR/Raman Phase Finder is a desktop application for Raman and FTIR spectroscopy: band detection, spectral library search, phase identification, and publication-ready figures.

**macOS:** [Download IR/Raman Phase Finder 1.1.0 (.pkg)](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/download/v1.1.0/IR_Raman_Phase_Finder_macOS_1.1.0.pkg) · [Release notes](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/tag/v1.1.0)

**Windows and Linux:** Version 1.1.0 is available from source. No installers for these platforms are included in this release.

## What you can do

- Import Raman and FTIR spectra and organize them into project series.
- Preprocess spectra, detect bands, and match references by band positions and chemical composition.
- Search local and downloadable reference libraries. Create and edit your own cards in **User Library** or import them using the [JSON reference template](reference_template.json).
- Compare spectra with reference lines, markers and vibrational assignments, and export PNG, JPEG, SVG or PDF figures.

## Installation

On macOS, run the PKG and open **IR Raman Phase Finder** from Applications. The first launch may need internet access to prepare the Python environment. After setup, the main window opens directly and checks for updates in the background.

To run from source with Python 3.11 or 3.12, create and activate a virtual environment, then run:

```sh
python -m pip install ".[formats]"
ir-raman-phase-finder-gui
```

Spectral databases are not bundled. Use **Manage databases** to download and index the sources you want, or connect your own library.

## Citation

If you use the program in research, cite **IR/Raman Phase Finder**, version 1.1.0, by Artem B. Kuznetsov (Institute of Geology and Mineralogy SB RAS), and link to the [release](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/tag/v1.1.0).

© 2026 Artem B. Kuznetsov · MIT License
