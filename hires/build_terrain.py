"""P1 terrain for the ~11 km grid, same method on both planets.

DEM pixels ~0.93 km (Earth: WorldClim 2.1 30" SRTM-based; Mars: MOLA 463 m mosaic averaged 2x2
to 926 m). Each cell holds 12 x 12 pixels. Per cell: mean elevation, mean slope (from the
pixel grid), roughness = std of elevation, relief = max - min, land fraction.

usage: python -I build_terrain.py earth|mars
"""
import sys
import time

import numpy as np
import tifffile

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from hires_common import OUT, RAW, SHAPE, deg_m  # noqa: E402

planet = sys.argv[1]
t0 = time.time()
if planet == "earth":
    src = RAW / "worldclim" / "wc2.1_30s_elev" / "wc2.1_30s_elev.tif"
    dem = tifffile.imread(src, out="memmap")  # 21600 x 43200 int16, -32768 = ocean
    nodata, factor, ppd = -32768, 1, 120
else:
    src = RAW / "mars" / "mola_dem_463m.tif"
    dem = tifffile.imread(src, out="memmap")  # 23040 x 46080 int16 (128 ppd)
    nodata, factor, ppd = None, 2, 64
ny, nx = SHAPE[planet]
k = 12  # pixels per cell side
px_m = deg_m(planet) / ppd
print(planet, dem.shape, dem.dtype, "px", round(px_m, 1), "m", flush=True)

out = {n: np.full((ny, nx), np.nan, np.float32) for n in ("elevation_m", "slope_deg", "roughness_m", "relief_m", "land_frac")}


def rows(a, b):
    """DEM rows a..b at the working resolution (averaging factor x factor), float with NaN."""
    lo, hi = max(a, 0), min(b, ny * k)
    blk = np.asarray(dem[lo * factor:hi * factor]).astype(np.float32)
    if nodata is not None:
        blk[blk == nodata] = np.nan
    if factor > 1:
        blk = blk.reshape(hi - lo, factor, blk.shape[1] // factor, factor).mean(axis=(1, 3))
    return blk, lo


for i in range(ny):
    blk, lo = rows(i * k - 1, i * k + k + 1)
    lat_rows = 90 - (np.arange(blk.shape[0]) + lo + 0.5) / ppd
    dx = px_m * np.cos(np.radians(lat_rows))[:, None]
    gx = (np.roll(blk, -1, axis=1) - np.roll(blk, 1, axis=1)) / (2 * dx)
    gy = np.full_like(blk, np.nan)
    gy[1:-1] = (blk[:-2] - blk[2:]) / (2 * px_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    s = i * k - lo  # first row of this cell row inside the block
    z = blk[s:s + k].reshape(k, nx, k)
    sl = slope[s:s + k].reshape(k, nx, k)
    valid = np.isfinite(z).sum(axis=(0, 2))
    with np.errstate(all="ignore"):
        out["land_frac"][i] = valid / (k * k)
        out["elevation_m"][i] = np.nanmean(z, axis=(0, 2))
        out["roughness_m"][i] = np.nanstd(z, axis=(0, 2))
        out["relief_m"][i] = np.nanmax(z, axis=(0, 2)) - np.nanmin(z, axis=(0, 2))
        out["slope_deg"][i] = np.nanmean(sl, axis=(0, 2))
    if i % 200 == 0:
        print(" row", i, round(time.time() - t0), "s", flush=True)

np.savez_compressed(OUT / f"{planet}_terrain.npz", **out)
print("saved", OUT / f"{planet}_terrain.npz", round(time.time() - t0), "s")
