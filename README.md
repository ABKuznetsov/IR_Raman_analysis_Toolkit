# IR/Raman Phase Finder

Shared toolkit for two separate search-match tools: Raman Finder and FTIR Finder. The
project keeps the Finder mechanics separate from the spectroscopy domain so the XRD
Finder architecture can be reused without copying the XRD implementation.

## Architecture

```text
Vibrational_Finder/
  finder_core/             shared Finder contracts and utilities
  vibrational_finder/      Raman/FTIR models, preprocessing, matching, UI, CLI
```

The intended family pattern is:

```text
XRD Finder
IR/Raman Phase Finder
SEM Finder
Luminescence Finder
```

Each tool keeps the same user workflow:

```text
Experiment -> Database -> Candidates -> Preview -> Selected -> Explanation
```

Only the domain engine changes: XRD uses a pattern calculator, while Raman and FTIR use
reference spectrum matching.

## v1 workflows

```text
Raman spectrum
  -> preprocessing
  -> band detection
  -> Raman reference library search
  -> optional small x-shift alignment
  -> position + intensity + correlation scoring
  -> ranked compound candidates

FTIR spectrum
  -> preprocessing
  -> band detection
  -> FTIR reference library search
  -> optional small x-shift alignment
  -> position + intensity + correlation scoring
  -> ranked compound candidates
```

The first version compares against reference spectra. It does not calculate Raman/IR
from structures; DFT/phonon workflows belong in a later module.

## Local library format

Use a CSV manifest as a user reference library. It works like a local catalog: one row
points to one reference spectrum file. Raman and FTIR records are separate rows and can
be present independently:

```csv
source,entry_id,name,formula,kind,path,compound_key
User,quartz_demo,Quartz,SiO2,raman,quartz_raman.xy,User:quartz_demo
User,quartz_demo,Quartz,SiO2,ftir,quartz_ftir.xy,User:quartz_demo
```

The GUI can also load a whole folder as a user library. It scans supported spectrum
files recursively, infers Raman/FTIR from the path name, and extracts simple formulas
from file names such as `Ca2Al2SiO7.txt` or `CaWO4_2Mo.txt`.

Calculated DFT spectra can be loaded with the same folder workflow via `Load DFT`.
CIF folders can be loaded as a weak `CIF IR hints` source: the program extracts formula
metadata and creates approximate FTIR band hints for fallback/explanation use.
Reference records carry Raman geometry metadata:

```text
orientation: unoriented | oriented | calculated | unknown
polarization: unpolarized | polarized | calculated | unknown
```

## Data sources

See `docs/DATA_SOURCES.md`. The source interface is ready for RRUFF, SDBS,
OpenSpecy, SpectraBase, NIST, and a local user library. RRUFF and OpenSpecy are
implemented downloadable connectors; other online connectors are staged as external
sources so licensing, caching, and redistribution rules can be handled per source.
RRUFF uses the official downloadable ZIP archives. OpenSpecy uses official RDS
libraries from OSF and requires the optional Python RDS readers listed in
`pyproject.toml`.

Spectrum files can be loaded from common open Raman/IR exports:

```text
wavenumber_cm1 intensity
100 0.1
108 0.4
```

Supported directly: `.txt`, `.xy`, `.csv`, `.tsv`, `.dat`, `.asc`, `.ascii`, `.prn`,
`.jdx`, and `.dx`. Binary vendor formats such as `.spc`, `.spa`, and Bruker OPUS
numbered files are recognized by the file dialogs, but this build asks for a CSV,
TXT, or JCAMP-DX export until a reliable optional binary decoder is installed.

## CLI

Raman:

```bash
raman-finder --experiment sample_raman.xy --library library.csv
```

FTIR:

```bash
ftir-finder --experiment sample_ftir.xy --library library.csv
```

## GUI

```bash
ir-raman-phase-finder-gui
```

From the source tree on macOS:

```bash
./run_finder.command
```

## Launchers

The IR/Raman Phase Finder launchers use the shared Sci Python environment at
`%LOCALAPPDATA%\Sci\env` on Windows. This is intended to be shared with related
Finder tools instead of creating one environment per app.

IR/Raman user data, cache and matplotlib state are stored under
`%LOCALAPPDATA%\Sci\apps\ir_raman_analysis_toolkit`. Logs are stored under
`%LOCALAPPDATA%\Sci\logs\ir_raman_analysis_toolkit`.

macOS / Linux:

```bash
./setup_env.command
./run_finder.command
./run_finder.sh
```

Windows:

```bat
setup_env.bat
run_finder.bat
launch_ir_raman_phase_finder_silent.vbs
```

Examples:

```bash
./run_raman_example.command
./run_ftir_example.command
```

```bat
run_raman_example.bat
run_ftir_example.bat
```

The `examples/observed_gelenite_raman.txt` file is a real Raman spectrum with a
minor grossular impurity and is used as an importer/detection regression fixture.
Additional real Raman fixtures live in `examples/real_raman/`.

The project tree keeps experimental files separated:

```text
Project
  Raman spectra
  FTIR spectra
  User reference libraries
    library.csv
      Raman references
      FTIR references
```

Selecting a reference spectrum in the tree previews it on the plot. If an experimental
Raman or FTIR spectrum is active, `Search active` searches only references of the same
method.
