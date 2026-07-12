from __future__ import annotations

import numpy as np

from finder_core.models import SignalKind


WAVENUMBERS_PER_EV = 8065.544005


def wavenumber_to_wavelength_nm(values) -> np.ndarray:
    wavenumbers = np.asarray(values, dtype=float)
    result = np.full_like(wavenumbers, np.nan, dtype=float)
    valid = np.isfinite(wavenumbers) & (wavenumbers > 0.0)
    result[valid] = 1.0e7 / wavenumbers[valid]
    return result


def raman_shift_to_scattered_wavelength_nm(values, laser_wavelength_nm: float) -> np.ndarray:
    shifts = np.asarray(values, dtype=float)
    result = np.full_like(shifts, np.nan, dtype=float)
    if not np.isfinite(laser_wavelength_nm) or laser_wavelength_nm <= 0.0:
        return result
    laser_wavenumber = 1.0e7 / float(laser_wavelength_nm)
    scattered_wavenumber = laser_wavenumber - shifts
    valid = np.isfinite(scattered_wavenumber) & (scattered_wavenumber > 0.0)
    result[valid] = 1.0e7 / scattered_wavenumber[valid]
    return result


def spectral_x_to_nm(values, kind: SignalKind, laser_wavelength_nm: float = 0.0) -> np.ndarray:
    if kind == SignalKind.RAMAN:
        return raman_shift_to_scattered_wavelength_nm(values, laser_wavelength_nm)
    return wavenumber_to_wavelength_nm(values)


def wavenumber_to_energy_ev(values) -> np.ndarray:
    return np.asarray(values, dtype=float) / WAVENUMBERS_PER_EV
