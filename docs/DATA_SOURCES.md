# Data Sources

IR/Raman Phase Finder treats every database as the same kind of provider, but Raman and
FTIR searches stay separate by default:

```text
search(query) -> candidate records
load_spectrum(candidate) -> reference spectrum
```

The first implementation supports a local `User Library` manifest because it is stable,
offline, and useful for testing the matching engine. Public and commercial databases can
be added behind the same interface.

## Priority Sources

| Source | Raman | FTIR | Notes |
| --- | --- | --- | --- |
| RRUFF | yes | partial | Best first public mineral source; often links Raman, XRD, chemistry, and mineral metadata. |
| SDBS | yes | yes | Strong free source for molecular spectra. |
| OpenSpecy | yes | yes | Implemented downloadable RDS connector; especially useful for polymers/plastics and environmental spectra. |
| SpectraBase | yes | yes | Mixed public/commercial access; useful as an optional connector. |
| NIST Chemistry WebBook | partial | yes | Important IR source; access and redistribution rules must be handled carefully. |
| JARVIS-DFT | calculated | calculated/IR | Important synthetic/inorganic computed-materials source; has infrared intensities and phonon-related properties. |
| Materials Project | calculated | calculated | Later-stage source for computed structures/phonons where available. |
| PhononDB | derived | derived | Later-stage source; needs phonon/DFT-derived workflows. |
| NOMAD | mixed | mixed | Repository-style source for uploaded experimental and computational datasets. |

## Synthetic Materials Coverage

RRUFF is excellent for minerals, but it is not enough for synthetic materials. Use these
source classes for synthetic compounds:

| Class | Sources | Best use |
| --- | --- | --- |
| Synthetic molecules | SDBS, NIST Chemistry WebBook, SpectraBase | Organics, reagents, simple synthetic chemicals, IR/Raman lookup. |
| Polymers and plastics | OpenSpecy, SpectraBase | FTIR/Raman identification of polymeric and environmental materials. |
| Synthetic inorganic crystals | JARVIS-DFT, Materials Project, PhononDB, NOMAD | Oxides, ceramics, DFT/phonon-derived IR/Raman hints and user-computed spectra. |
| Local lab libraries | User Library, folder import, DFT folder import, CIF hints | The most important source for new compositions that do not exist in public databases. |

For the user workflow in this project, the highest-value synthetic path is:

```text
measured lab Raman/FTIR
DFT spectra from collaborators
CIF-derived weak IR hints
JARVIS/PhononDB/Materials Project metadata
```

Public synthetic sources should be treated as optional connectors with local caching,
because access rules and downloadable formats vary strongly between providers.

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

These sources are listed in the UI but left as planned connectors until their access
rules and stable machine-readable download routes are handled explicitly.

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
