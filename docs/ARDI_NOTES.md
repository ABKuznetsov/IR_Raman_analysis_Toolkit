# ArDI Notes For IR/Raman Phase Finder

ArDI is a useful reference for the Raman/IR Finder workflow because it combines
interactive preprocessing, database search, database reading, and deconvolution in one
web interface.

Observed UI/workflow points from the public ArDI page and practical guides:

- Supported upload formats in the guide: `.txt`, `.csv`, `.ascii`, `.jdx`.
- Search page has separate modes:
  - Machine Learning Search.
  - ML Search Settings.
  - Simple Search.
  - Read Database.
  - Spectrum Preprocessing.
- Search databases are selected from `.h5` files, for example RRUFF-derived Raman
  databases and `raman-fmm.h5`.
- Result table columns visible in the interface:
  - Name.
  - Strunz.
  - ID.
  - Chemistry.
  - Elements.
  - Web.
  - Similarity.
  - lambda / excitation wavelength.
  - Type.
- Simple search uses a similarity threshold, result limit, optional excitation
  wavelength filter, table-restricted search, and normalization.
- Read Database/table filtering can reduce the search domain before matching. The
  guide gives examples of filtering by Strunz class and elements.
- Preprocessing controls include shift X, shift Y, scale Y, normalize, deglitch, cut,
  remove baseline, and reset.
- Host-mineral subtraction is an important workflow for inclusions: identify host,
  plot selected reference on the deconvolution view, align/scale it, and subtract.

Implementation implications for this project:

- Keep separate `Search`, `Preprocessing`, `Read database`, and later `Deconvolution`
  surfaces rather than hiding everything in one button.
- Add result metadata fields compatible with ArDI-style libraries: Strunz, chemistry,
  elements, web URL, excitation wavelength, and type/source quality.
- Add HDF5 import as a library source when a real sample `.h5` schema is available.
- Keep CSV/folder libraries as the open fallback so local lab spectra can be added
  without relying on ArDI access.
- Add host/reference subtraction as a Raman-specific workflow after preview/overlay is
  stable.
