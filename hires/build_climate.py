"""Earth climate for the 0.1 deg grid from WorldClim 2.1 2.5' monthly normals (1970-2000).

air_temp_mean_K, air_temp_min_K (coldest month tmin), air_temp_max_K, air_temp_swing_K
(mean monthly tmax - tmin), precipitation_mm_yr, pet_mm_yr (Hargreaves) and aridity_index = P / PET
(UNEP), all aggregated to 0.1 deg by pixel centre.
"""
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, SHAPE  # noqa: E402

t0 = time.time()
W = RAW / "worldclim"
ny, nx = SHAPE["earth"]
PX = 2.5 / 60
DAYS = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MID_DOY = [15, 46, 74, 105, 135, 166, 196, 227, 258, 288, 319, 349]


def read(var, m):
    a = tifffile.imread(W / f"wc2.1_2.5m_{var}" / f"wc2.1_2.5m_{var}_{m:02d}.tif").astype(np.float32)
    a[a < -1000] = np.nan
    return a


def ra_mm_day(lat_deg, doy):
    """FAO-56 extraterrestrial radiation, as evaporation equivalent (mm/day)."""
    phi = np.radians(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    return 0.408 * np.maximum(ra, 0)


lat_px = 90 - (np.arange(4320) + 0.5) * PX
tmean_sum = None
for m in range(1, 13):
    tmin, tmax, tavg, prec = read("tmin", m), read("tmax", m), read("tavg", m), read("prec", m)
    ra = ra_mm_day(lat_px, MID_DOY[m - 1])[:, None]
    pet = 0.0023 * ra * (tavg + 17.8) * np.sqrt(np.maximum(tmax - tmin, 0)) * DAYS[m - 1]
    pet = np.maximum(pet, 0)
    if tmean_sum is None:
        tmean_sum, swing_sum, p_sum, pet_sum = tavg.copy(), tmax - tmin, prec.copy(), pet
        tmin_min, tmax_max = tmin.copy(), tmax.copy()
    else:
        tmean_sum += tavg
        swing_sum += tmax - tmin
        p_sum += prec
        pet_sum += pet
        tmin_min = np.fmin(tmin_min, tmin)
        tmax_max = np.fmax(tmax_max, tmax)
    print(" month", m, round(time.time() - t0), "s", flush=True)

fields = {
    "air_temp_mean_K": tmean_sum / 12 + 273.15,
    "air_temp_swing_K": swing_sum / 12,
    "air_temp_min_K": tmin_min + 273.15,
    "air_temp_max_K": tmax_max + 273.15,
    "precipitation_mm_yr": p_sum,
    "pet_mm_yr": pet_sum,
}
out = {}
from hires_common import bin_mean  # noqa: E402

for name, a in fields.items():
    s, c = bin_mean("earth", a, 90.0, -180.0, PX)
    with np.errstate(all="ignore"):
        out[name] = (s / c).astype(np.float32)
with np.errstate(all="ignore"):
    out["aridity_index"] = (out["precipitation_mm_yr"] / out["pet_mm_yr"]).astype(np.float32)
np.savez_compressed(OUT / "earth_climate.npz", **out)
print("saved", round(time.time() - t0), "s")
