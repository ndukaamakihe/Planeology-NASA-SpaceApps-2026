"""Earth ground temperature for the 0.1 deg grid from MODIS MOD11A2 1 km long-term
(OpenLandMap, Hengl 2018, 2000-2017 medians; Zenodo 1435938). Values K x 50; 87.37N..62S.

surface_temp_swing_K = annual day median - annual night median (cell mean)
surface_temp_min_K   = coldest monthly night median (min over months of the cell means)
"""
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, SHAPE, bin_mean  # noqa: E402

L = RAW / "lst"
PX, LAT0, LON0 = 1 / 120, 87.37, -180.0
ny, nx = SHAPE["earth"]
t0 = time.time()


def name(period, kind):
    return L / f"clm_lst_mod11a2.{period}.{kind}_1km_s0..0cm_2000..2017_v1.0.tif"


def cell_mean(arrays_fn):
    """Bin a per-pixel field (computed block by block by arrays_fn(r0, r1)) into cells."""
    tot = np.zeros((ny, nx)); cnt = np.zeros((ny, nx))
    rows = 17924
    for r0 in range(0, rows, 1024):
        r1 = min(rows, r0 + 1024)
        v = arrays_fn(r0, r1)
        s, c = bin_mean("earth", v, LAT0, LON0, PX, row_offset=r0)
        tot += s; cnt += c
    with np.errstate(all="ignore"):
        return (tot / cnt).astype(np.float32)


def k(a):
    a = np.asarray(a).astype(np.float32)
    a[a <= 0] = np.nan
    return a * 0.02


day = tifffile.imread(name("annual", "day_m"), out="memmap")
night = tifffile.imread(name("annual", "night_m"), out="memmap")
swing = cell_mean(lambda r0, r1: k(day[r0:r1]) - k(night[r0:r1]))
print("swing", round(time.time() - t0), "s", flush=True)
months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
tmin = None
for m in months:
    a = tifffile.imread(name(m, "night_m"), out="memmap")
    cm = cell_mean(lambda r0, r1: k(a[r0:r1]))
    tmin = cm if tmin is None else np.fmin(tmin, cm)
    del a
    print(" ", m, round(time.time() - t0), "s", flush=True)
np.savez_compressed(OUT / "earth_lst.npz", surface_temp_swing_K=swing, surface_temp_min_K=tmin)
print("saved", round(time.time() - t0), "s")
