"""Aridity index (UNEP / FAO): yearly precipitation / yearly potential evapotranspiration (PET).

PET uses the Hargreaves equation (FAO-56, eq. 52), the same method as the
Global Aridity Index CMIP6 future projections (Trabucco & Zomer), because it
only needs monthly tmin, tmax and precipitation - exactly what WorldClim
provides for today AND for the CMIP6 projections. So today and the future are
computed with one identical method.

Classes (UNEP 1997): hyperarid < 0.05 <= arid < 0.20 <= semi_arid < 0.50
<= dry_subhumid < 0.65 <= humid.
"""
import numpy as np

DAYS = np.array([31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])
MID_DOY = np.cumsum(DAYS) - DAYS / 2
LAT = np.linspace(89.5, -89.5, 180)


def ra_mm_day(lat=None):
    """Extraterrestrial radiation (FAO-56 eq. 21) in mm/day, shape (12, n_lat). Default: the 1-degree rows."""
    phi = np.deg2rad(LAT if lat is None else np.asarray(lat, dtype=float))[None, :]
    j = MID_DOY[:, None]
    dr = 1 + 0.033 * np.cos(2 * np.pi * j / 365)
    delta = 0.409 * np.sin(2 * np.pi * j / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(delta), -1, 1))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(delta) + np.cos(phi) * np.cos(delta) * np.sin(ws))
    return 0.408 * ra


def aridity(tmin, tmax, prec, lat=None):
    """tmin, tmax in deg C, prec in mm; all (12, n_lat, n_lon). lat = row latitudes (default: the 1-degree
    grid 89.5 ... -89.5). Returns index and class arrays."""
    ra = ra_mm_day(lat)[:, :, None]
    tmean = (tmin + tmax) / 2
    pet_day = 0.0023 * ra * np.clip(tmean + 17.8, 0, None) * np.sqrt(np.clip(tmax - tmin, 0, None))
    pet = np.nansum(pet_day * DAYS[:, None, None], 0)
    p = np.nansum(prec, 0)
    ok = np.isfinite(tmin).all(0) & np.isfinite(prec).all(0) & (pet > 0)
    ai = np.where(ok, p / np.where(pet > 0, pet, 1), np.nan)
    cls = np.full(ai.shape, "", dtype=object)
    for lo, name in [(0, "hyperarid"), (0.05, "arid"), (0.20, "semi_arid"), (0.50, "dry_subhumid"), (0.65, "humid")]:
        cls[np.isfinite(ai) & (ai >= lo)] = name
    return ai, cls
