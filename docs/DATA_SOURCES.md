# Data Sources

IR/Raman Phase Finder treats every database as the same kind of provider, but Raman and
FTIR searches stay separate by default:

```text
search(query) -> candidate records
load_spectrum(candidate) -> reference spectrum
```

Only sources with a working local index and spectrum loader are shown as Finder databases.
Websites that cannot supply a legal, stable machine-readable library are shown separately
as external search links.

## Connected Sources

| Source | Raman | FTIR | Notes |
| --- | --- | --- | --- |
| RRUFF | yes | partial | Best first public mineral source; often links Raman, XRD, chemistry, and mineral metadata. |
| Raman Open Database (ROD) | yes | no | Implemented CC0 connector for experimental and theoretical Raman spectra. |
| OpenSpecy | yes | yes | Implemented downloadable RDS connector; especially useful for polymers/plastics and environmental spectra. |
| JARVIS-DFT | limited calculated | calculated IR | Implemented metadata/index connector with lazy XML spectrum caching. |

## External Search Links

| Source | Use | Why it is not a Finder database |
| --- | --- | --- |
| SDBS | Manual Raman/FTIR search for organic compounds | AIST explicitly states that it does not provide spectra as digital data. |
| NIST Chemistry WebBook | Manual per-compound IR search and JCAMP-DX download | Individual downloads exist, but there is no redistributable bulk library connector. |
| SpectraBase | Manual Raman/FTIR lookup | Public/subscription access; no open bulk dataset suitable for local indexing. |

Materials Project, PhononDB and NOMAD are not shown in the current database UI. They
provide structures, phonons or repository records, but not a stable ready-to-compare
Raman/FTIR reference library for this workflow.

## Synthetic Materials Coverage

RRUFF is excellent for minerals, but it is not enough for synthetic materials. Use these
source classes for synthetic compounds:

| Class | Sources | Best use |
| --- | --- | --- |
| Synthetic molecules | External SDBS, NIST and SpectraBase links | Manual lookup followed by importing an allowed downloaded spectrum. |
| Polymers and plastics | OpenSpecy; external SpectraBase link | Automatic OpenSpecy matching plus optional manual lookup. |
| Synthetic inorganic crystals | JARVIS-DFT and user-computed spectra | Calculated IR, verified calculated Raman activity, and local DFT results. |
| Local lab libraries | User Library, folder import, DFT folder import, CIF hints | The most important source for new compositions that do not exist in public databases. |

For the user workflow in this project, the highest-value synthetic path is:

```text
measured lab Raman/FTIR
DFT spectra from collaborators
CIF-derived weak IR hints
JARVIS-DFT calculated spectra
```

External search results become part of the Finder only after the user downloads an
allowed spectrum and imports it into the local library.

## v1 Policy

The v1 engine compares experimental spectra against reference spectra. It does not
calculate Raman or IR spectra from structure files.

## Connector Status

### RRUFF

RRUFF is the first online source to connect because it exposes downloadable ZIP archives
for Raman and infrared data. The connector downloads archives into the local cache,
indexes spectrum files inside the ZIP, then serves them through the same search and
load interface as a user library.

Initial GUI action:

```text
Databases -> RRUFF -> Update
```

Choose the archive in `RRUFF archive` before pressing `Update`. The available official
archives are exposed as:

```text
Raman excellent_unoriented
Raman excellent_oriented
Raman fair_unoriented
Raman fair_oriented
Raman poor_unoriented
Raman unrated_unoriented
Raman unrated_oriented
Raman lr_raman
FTIR ir_raw
```

For quick smoke tests, use `Raman fair_oriented`; it is small compared with the main
archives. For real unpolarized/unoriented laboratory Raman spectra, prefer
`Raman excellent_unoriented` or `Raman fair_unoriented`.

### SDBS, NIST, SpectraBase

These sources appear only under `External spectrum search`. They do not have checkboxes
under `Databases used for search` and are not included in automatic matching. NIST
per-compound JCAMP-DX files can be imported into a user library after manual download.

### Raman Open Database (ROD)

ROD is a CC0 source containing experimental and theoretical Raman records. The Finder
submits the official wildcard search, downloads the ZIP export returned by ROD, indexes
the embedded `.rod` CIF2 files, and keeps laser wavelength, resolution, determination
method, orientation/polarization, space group and COD links as candidate metadata.

```text
Databases -> Raman Open Database (CC0) -> Download / update
```

The verified archive contained 1133 entries at the time of implementation: 1131
experimental and 2 theoretical records. Duplicates remain separate because their
spectra and measurement conditions can differ.

### OpenSpecy

OpenSpecy publishes Raman/(FT)IR reference libraries as RDS files on OSF. The documented
R workflow uses `get_lib("derivative")` followed by `load_lib("derivative")`.
IR/Raman Phase Finder mirrors that approach with a Python connector:

```text
Databases -> OpenSpecy library -> medoid derivative
Databases -> OpenSpecy downloadable RDS library -> Download / update
```

The connector downloads the official RDS file, reads the OpenSpecy object with
`rdata`/`pyreadr`, maps `metadata` rows into `CandidateRecord`, and loads spectra from
the shared `wavenumber` array plus the `spectra` matrix. The verified
`medoid_derivative` library contains 4655 spectra in the tested local cache.

### JARVIS-DFT

JARVIS-DFT is the first implemented calculated-spectrum source for synthetic inorganic
materials. The connector downloads the official `dft_3d` Figshare archive, streams its
metadata into the local SQLite index, and retains entries that advertise calculated IR
modes.

```text
Databases -> JARVIS-DFT calculated spectra -> Download / update
```

The verified archive contains 75,993 material records and 4,809 records with calculated
IR data. Full line frequencies and intensities are stored in public per-material XML
records, so they are downloaded and cached only for shortlisted or previewed candidates.
This keeps the initial database update near 39 MB instead of downloading several
gigabytes of XML files.

Some XML records also contain non-resonant Raman frequencies and calculated activities.
The Finder adds a separate Raman candidate only after those arrays have been verified;
ordinary phonon frequencies are not mislabeled as a Raman spectrum. Calculated Raman
coverage is therefore smaller and grows locally as relevant JARVIS entries are opened.

## Project Organization

Raman and FTIR are stored as separate experimental branches because one method is often
available without the other:

```text
Project
  Raman spectra
  FTIR spectra
  User reference libraries
    library.csv
      Raman references
      FTIR references
```

Records can still share a `compound_key` when a database has both Raman and IR for the
same compound. That helps the compound card show availability without forcing a combined
search.

RRUFF is especially valuable because one compound entry can eventually connect:

```text
composition
Raman
IR
XRD
```
