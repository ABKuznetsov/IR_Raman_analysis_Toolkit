# Database Workflow

The Finder should work with spectral databases the same way XRD Finder works with
structure/reference sources: download or load a database, index it locally, then search
against the indexed records.

## RRUFF

RRUFF is the first priority because it exposes direct downloadable archives.

Official archive indexes:

- Raman: `https://www.rruff.net/zipped_data_files/raman/`
- Infrared: `https://www.rruff.net/zipped_data_files/infrared/`
- Chemistry/supporting files: `https://www.rruff.net/zipped_data_files/chemistry/`

Raman archive options:

- `excellent_unoriented.zip`
- `excellent_oriented.zip`
- `fair_unoriented.zip`
- `fair_oriented.zip`
- `poor_unoriented.zip`
- `unrated_unoriented.zip`
- `unrated_oriented.zip`
- `LR-Raman.zip`

For typical lab spectra in this project, prefer the unoriented archives. `fair_oriented`
is useful as a small smoke-test archive.

FTIR archive:

- `RAW.zip`

Chemistry/supporting files:

- `Reference_PDF.zip`
- `Microprobe_Data.zip`

Important implementation note: the spectral ZIP filenames contain mineral name and
RRUFF ID, but formula metadata is not always present in the spectrum file name. Element
filtering against RRUFF therefore needs either website metadata, a chemistry export, or
a local mineral formula table. Until that exists, element-filtered RRUFF search can miss
valid candidates even when the spectra are cached.

## OpenSpecy

OpenSpecy provides a Raman/(FT)IR package and reference-library workflow. Its public R
package documents:

```r
get_lib("derivative")
spec_lib <- load_lib("derivative")
```

The package README says the library is fetched from OSF and the package supports formats
such as `.asp`, `.csv`, `.jdx`, `.spc`, `.spa`, `.0`, and `.zip`.

Implemented workflow:

- Download/cache the selected RDS library through its OSF route.
- Convert OpenSpecy metadata into `CandidateRecord`.
- Load the shared wavenumber axis and spectrum matrix for local matching.
- Treat it mainly as FTIR/Raman reference data for polymers, organics, and environmental samples.

## Raman Open Database

ROD exposes an official server-side search and ZIP export. The connector searches ROD
IDs with the `%` wildcard, preserves the returned session cookie, downloads the ZIP,
and indexes every `.rod` file locally. This avoids crawling individual HTML pages.

ROD data are CC0. Experimental and theoretical records are both retained and marked in
the candidate metadata; entries reported as erroneous by ROD are excluded by default.

## JARVIS-DFT

JARVIS-DFT publishes a large `dft_3d` metadata archive on Figshare and per-material XML
records through NIST. The connector uses a two-stage cache:

1. Download and stream-index the official metadata ZIP.
2. Prefilter candidates by composition, text and Gamma-point modes.
3. Download XML only for a previewed entry or a short active-search candidate list.
4. Build a broadened reference spectrum from the calculated line intensities.

The source indexes calculated FTIR records immediately. A Raman record is indexed only
when its XML contains both `frequencies` and `activity` under `raman_dat`. This distinction
is important: a list of phonon frequencies alone is not a calculated Raman spectrum.

The archive contains non-standard JSON `NaN` values. The importer sanitizes those tokens
as a stream and uses `ijson`, so the roughly 209 MB uncompressed JSON file is never loaded
as one Python object during normal setup.

## Vendor Formats

The base reader handles text/CSV/JCAMP-DX without optional packages. Normal setup uses
the `formats` package extra, which installs `ramanchada2` and its SPC, Bruker OPUS,
Renishaw WDF, NGS and Princeton SPE readers. The adapter is loaded lazily so application
startup and basic text import do not pay the cost of importing the full scientific stack.

## SDBS

SDBS is valuable for organic compounds and includes Raman and FTIR. It is a searchable
web database, but its official FAQ says digital spectral data are not provided. It is
therefore an external browser link, not an automatic connector.

## NIST Chemistry WebBook and SpectraBase

NIST provides individual IR spectra in JCAMP-DX where available. Those files can be
downloaded manually and imported into a user library, but the application does not crawl
or mirror the WebBook. SpectraBase is likewise retained as a manual public/subscription
search link. Neither source appears as an automatic-search checkbox.

## Local Lab Libraries

These must remain first-class:

- CSV manifest library.
- Folder library.
- DFT calculated spectrum folder.
- CIF folder as weak IR band hints.

This is the most reliable path for custom materials, rare phases, and spectra measured
under the same lab conditions.
