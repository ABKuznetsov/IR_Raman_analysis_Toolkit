# IR/Raman Analysis Toolkit

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/Status-Preview-orange.svg)

# Download IR/Raman Phase Finder

**Windows 10/11:** [Download `IR_Raman_analysis_Toolkit_Setup_0.1.0.exe`](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/download/v0.1.0/IR_Raman_analysis_Toolkit_Setup_0.1.0.exe) and run the installer.

**All releases:** [GitHub Releases](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases)

More detailed installation notes are below in [Installation](#installation).

# IR/Raman Phase Finder 0.1.0

Preview release focused on bringing the XRD Phase Finder workflow to Raman and FTIR
search-match work, with a shared Sci runtime, startup preview, downloadable source
caches and Windows installer support.

# Overview

**IR/Raman Phase Finder** is an open-source desktop tool for phase identification
from Raman and infrared spectra. It is built for everyday search-match work: load an
experimental spectrum, limit chemistry by elements, search local or downloadable
spectral sources, preview candidate spectra, inspect metadata and keep selected
matches in one project.

The project follows the same Finder application pattern as
[XRD Analysis Toolkit](https://github.com/ABKuznetsov/XRD_Analysis_Toolkit), but the
domain engine is vibrational spectroscopy rather than diffraction.

## What It Can Do

- import Raman and FTIR spectra from common text, CSV and JCAMP-DX style files
- load user spectral libraries from CSV manifests or folders
- search Raman and FTIR references separately against the active experiment
- use required, optional and excluded elements to gate candidate compounds
- download/cache supported public source data such as RRUFF and OpenSpecy
- preview reference spectra on the active plot before selecting them
- manage project trees with experiments, libraries, candidates and selected matches
- save user data, caches, settings and matplotlib state outside the installed program

## Data Sources

See [Data Sources](docs/DATA_SOURCES.md). The source interface is ready for RRUFF,
OpenSpecy, SDBS, SpectraBase, NIST and local user libraries. RRUFF and OpenSpecy have
downloadable connectors in this preview build; other sources are staged so licensing,
caching and redistribution rules can be handled per source.

Large third-party spectral databases are not bundled with the application. The
program provides tools for reading, indexing and caching data that the user is allowed
to access.

---

# Typical Workflow

```text
Load experimental Raman or FTIR spectrum
        |
        |
Preprocess and detect bands
        |
        |
Choose active reference sources
(RRUFF / OpenSpecy / local folder / CSV library / DFT spectra)
        |
        |
Restrict chemistry with the element table
        |
        |
Search candidate compounds
        |
        |
Preview reference spectra on the active plot
        |
        |
Select likely matches and inspect unexplained bands
```

---

# Interaction Guide

- **Element table**
  - Left click marks an element as required.
  - Right click marks an element as optional.
  - Clicking again removes that element from the gate.
- **Project tree**
  - The highlighted experiment is the active spectrum for search and preview.
  - Checkboxes control what is visible in the plot.
- **Candidate list**
  - Single click previews the candidate spectrum and metadata.
  - Double click adds a candidate to the selected match set.
- **Selected candidates**
  - Use selected matches to compare reference spectra against the experiment.
- **Plot**
  - Use normal mouse zoom and pan.
  - View settings are kept in the same style as the XRD Finder View tab.

---

# Installation

## Download

Latest release assets:

- Windows 10/11: [`IR_Raman_analysis_Toolkit_Setup_0.1.0.exe`](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases/download/v0.1.0/IR_Raman_analysis_Toolkit_Setup_0.1.0.exe)
- All releases: [GitHub Releases](https://github.com/ABKuznetsov/IR_Raman_analysis_Toolkit/releases)

## Requirements

Windows installer:

- Windows 10 or Windows 11, 64-bit recommended.
- Administrator rights for installation into the selected application folder.
- Internet access during first setup, because Python or Python packages may need to be downloaded.
- About 1 GB of free disk space for the shared scientific Python environment.

Source checkout:

- Python 3.11 or newer, below Python 3.13.
- `pip` and Python virtual environment support.
- Internet access for installing Python packages.

IR/Raman Phase Finder uses the shared per-user Sci runtime:

```text
%LOCALAPPDATA%\Sci\env
```

User data, downloaded sources, caches and settings are stored under:

```text
%LOCALAPPDATA%\Sci\apps\ir_raman_analysis_toolkit
```

Logs are stored under:

```text
%LOCALAPPDATA%\Sci\logs\ir_raman_analysis_toolkit
```

## Windows

Download and run:

```text
IR_Raman_analysis_Toolkit_Setup_0.1.0.exe
```

The installer:

- installs IR/Raman Phase Finder into the selected application folder
- creates Start Menu and optional Desktop shortcuts
- creates or reuses the shared `Sci` Python environment in user AppData
- installs required Python packages
- writes launcher commands into `%LOCALAPPDATA%\Sci\bin`
- adds an uninstall entry to Windows

If Python 3.11 is not already available, the setup script first tries `winget` and then
falls back to the official Python 3.11.9 installer from python.org.

## macOS / Linux

Source-checkout launchers are available:

```bash
./setup_env.command
./run_finder.command
./run_finder.sh
```

Examples:

```bash
./run_raman_example.command
./run_ftir_example.command
```

---

# Source Checkout Commands

Setup:

```text
setup_env.bat          # Windows
setup_env.command      # macOS
./setup_env.sh         # Linux
```

Graphical launchers:

```text
run_finder.bat
./run_finder.command
./run_finder.sh
```

Command-line launchers:

```text
run_finder_cli.bat
raman-finder --experiment sample_raman.xy --library library.csv
ftir-finder --experiment sample_ftir.xy --library library.csv
```

For normal interactive work, importing spectra and libraries from the application
window is preferred.

---

# Local Library Format

Use a CSV manifest as a user reference library. One row points to one reference
spectrum file. Raman and FTIR records are separate rows and can be present
independently:

```csv
source,entry_id,name,formula,kind,path,compound_key
User,quartz_demo,Quartz,SiO2,raman,quartz_raman.xy,User:quartz_demo
User,quartz_demo,Quartz,SiO2,ftir,quartz_ftir.xy,User:quartz_demo
```

The GUI can also load a whole folder as a user library. It scans supported spectrum
files recursively, infers Raman/FTIR from the path name and extracts simple formulas
from file names such as `Ca2Al2SiO7.txt` or `CaWO4_2Mo.txt`.

Supported directly: `.txt`, `.xy`, `.csv`, `.tsv`, `.dat`, `.asc`, `.ascii`, `.prn`,
`.jdx` and `.dx`. Binary vendor formats such as `.spc`, `.spa` and Bruker OPUS
numbered files are recognized by file dialogs, but this preview build asks for CSV,
TXT or JCAMP-DX export until a reliable optional binary decoder is installed.

---

# Repository Structure

```text
IR_Raman_analysis_Toolkit/
    README.md
    pyproject.toml
    setup_env.bat
    setup_env.command
    setup_env.sh

    docs/
        DATA_SOURCES.md
        DATABASE_WORKFLOW.md
        ARDI_NOTES.md

    toolkit/
        manifest.json
        setup_sci_env.bat
        launch_ir_raman_phase_finder_preview.ps1

    installer/
        IR_Raman_Phase_Finder.iss
        build_installer.bat
        clean_payload.bat

    Vibrational_Finder/
        app.json
        finder_core/
            Shared Finder contracts and utilities
        vibrational_finder/
            IR/Raman Phase Finder application source code

    examples/
        Demo Raman/FTIR spectra and library files

    tests/
        Import, matching and source-cache tests
```

Generated installer files such as `IR_Raman_analysis_Toolkit_Setup_0.1.0.exe` are
**not committed to the repository**; they are published separately as GitHub Releases
assets.

The root `IR_Raman_analysis_Toolkit` layout keeps shared toolkit files separate from
the `Vibrational_Finder` application folder. This leaves room for additional
IR/Raman-related programs later while preserving a clear application boundary.

---

# Scientific Background

The software combines standard vibrational spectroscopy search-match steps:

- spectral preprocessing
- baseline correction
- peak/band detection
- reference spectrum matching
- chemistry filtering by formula elements
- local and downloadable spectral libraries

Core open-source libraries used by the application:

- [NumPy](https://numpy.org/) and [SciPy](https://scipy.org/) for numerical work
- [pybaselines](https://pybaselines.readthedocs.io/) for baseline correction
- [pyqtgraph](https://www.pyqtgraph.org/) for interactive plotting
- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/) for the desktop interface
- [pyreadr](https://github.com/ofajardo/pyreadr) and [rdata](https://rdata.readthedocs.io/) for optional RDS library import paths

The current implementation is intended for **initial phase identification** and
**visual interpretation** of Raman and IR spectra. It is not intended to replace
full quantitative spectroscopic refinement workflows.

---

# Current Status

Current development stage: **0.1.0 public preview**.

The application is ready for practical source loading, reference search, candidate
preview and selected-match workflows on Windows. Next development work is focused on
improving source connectors, scoring, project persistence and packaged release
automation.

---

# License

MIT License

---

# Citation

If you use this software in scientific research, please cite this GitHub repository.

A dedicated software publication describing the Finder workflow for vibrational
spectroscopy is planned after the preview architecture stabilizes.

---

# Author

**Artem B. Kuznetsov**

Institute geology and mineralogy SB RAS

GitHub:
https://github.com/ABKuznetsov
