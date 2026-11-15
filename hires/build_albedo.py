"""Earth albedo for the 0.1 deg grid: mean of 12 mid-month days of the MODIS blue-sky (historical, with snow)
albedo climatology at 0.05 deg (Zenodo 6350821, 20-year MODIS), cell mean by pixel centre."""
import glob
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, bin_mean  # noqa: E402

files = sorted(glob.glob(str(RAW / "albedo" / "days" / "albedo_climatology_0.05CMG" / "*.nc")))
assert len(files) == 12, len(files)
acc = n = None
for f in files:
    with h5py.File(f, "r") as h:
        a = h["hist_alb_clim"][:].astype(np.float32)
        lat = h["latitude"][:]
        lon = h["longitude"][:]
    a = a.T  # (lat, lon)
    ok = (a >= 0) & (a <= 1000)
    v = np.where(ok, a * 0.001, 0)
    acc = v if acc is None else acc + v
    n = ok.astype(np.int16) if n is None else n + ok
print("lat", lat[0], lat[-1], "lon", lon[0], lon[-1])
with np.errstate(all="ignore"):
    mean = np.where(n >= 3, acc / n, np.nan)
if lat[0] < lat[-1]:
    mean = mean[::-1]
s, c = bin_mean("earth", mean, 90.0, -180.0, 0.05)
with np.errstate(all="ignore"):
    alb = (s / c).astype(np.float32)
np.savez_compressed(OUT / "earth_albedo.npz", albedo=alb)
print("saved; finite", int(np.isfinite(alb).sum()))
