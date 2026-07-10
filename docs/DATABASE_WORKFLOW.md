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

Implementation direction:

- Add an `OpenSpecySource`.
- Download/cache the library through an OSF/API route or user-provided exported file.
- Convert OpenSpecy metadata into `CandidateRecord`.
- Treat it mainly as FTIR/Raman reference data for polymers, organics, and environmental
  samples.

## SDBS

SDBS is valuable for organic compounds and includes Raman and FTIR. It is a searchable
web database, but mass download is restricted by its terms. Use it as a cautious,
rate-limited connector or as a manual import/export workflow.

## Local Lab Libraries

These must remain first-class:

- CSV manifest library.
- Folder library.
- DFT calculated spectrum folder.
- CIF folder as weak IR band hints.

This is the most reliable path for custom materials, rare phases, and spectra measured
under the same lab conditions.
