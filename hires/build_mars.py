"""Assemble the Mars 0.1875 deg (~11 km) grid.

Fine: terrain (MOLA, build_terrain.py), albedo (TES bolometric, USGS 7410 m mosaic).
From the Data team's 1-degree grid: ground temperatures and air swing (MCD v6 is ~200 km anyway,
bilinear), rock group, minerals, ground ice, craters (parent cell).
ATI = (1 - albedo) / ground day-night swing, as on Earth.
"""
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, bin_mean, load_1deg  # noqa: E402
from regrid import bilinear, parent  # noqa: E402

t0 = time.time()
G = load_1deg("mars")
T = np.load(OUT / "mars_terrain.npz")
alb = tifffile.imread(RAW / "mars" / "tes_albedo_7410m.tif").astype(np.float32)
alb[(alb < 0) | (alb > 1)] = np.nan
s, c = bin_mean("mars", alb, 90.0, -180.0, 0.125)
with np.errstate(all="ignore"):
    albedo = (s / c).astype(np.float32)
albedo = np.where(np.isfinite(albedo), albedo, bilinear("mars", G["albedo"]))

out = {k: T[k] for k in ("elevation_m", "slope_deg", "roughness_m", "relief_m")}
out["albedo"] = albedo
for col in ("surface_temp_swing_K", "surface_temp_min_K", "air_temp_swing_K", "air_temp_mean_K"):
    out[col] = bilinear("mars", G[col])
with np.errstate(all="ignore"):
    out["apparent_thermal_inertia"] = ((1 - albedo) / out["surface_temp_swing_K"]).astype(np.float32)
out["rock_group"] = parent("mars", G["rock_group"]).astype("U16")
out["mineral_groups"] = parent("mars", G["mineral_groups"]).astype("U80")
out["ground_ice_flag"] = parent("mars", G["ground_ice_flag"]).astype(np.float32)
out["crater_count_1deg"] = parent("mars", G["crater_count"]).astype(np.float32)
# 11 km rock (SIM 3292), ground ice (GRS >= 10 wt% or polar/ice unit), craters (Robbins) and thermal inertia (TES)
fc = OUT / "mars_classes.npz"
if fc.exists():
    F = np.load(fc)
    use = (F["rock_group"] != "") & (F["unit"] != "AHi")  # impact units keep the 1-degree group (Data team's rule)
    out["rock_group"] = np.where(use, F["rock_group"], out["rock_group"]).astype("U16")
    h2o = parent("mars", G["ground_ice_h2o_wt"]).astype(np.float32)
    out["ground_ice_flag"] = ((np.nan_to_num(h2o) >= 10) | (out["rock_group"] == "ice")).astype(np.float32)
    out["inside_crater"] = F["inside_crater"].astype(np.int8)
    ti = F["thermal_inertia"].astype(np.float64)
    ati = out["apparent_thermal_inertia"].astype(np.float64)
    pct = np.full(ti.shape, np.nan)
    ok = np.isfinite(ti)
    tab = np.sort(ti[ok])
    pct[ok] = np.searchsorted(tab, ti[ok], side="right") / len(tab)
    ok2 = ~ok & np.isfinite(ati)
    tab2 = np.sort(ati[np.isfinite(ati)])
    pct[ok2] = np.searchsorted(tab2, ati[ok2], side="right") / len(tab2)
    out["thermal_inertia"] = F["thermal_inertia"]
    out["ti_percentile"] = pct.astype(np.float32)  # TES thermal inertia where mapped, apparent thermal inertia elsewhere
np.savez_compressed(OUT / "mars_grid.npz", **out)
print("saved mars_grid.npz", round(time.time() - t0), "s")
