"""Assemble the Earth 0.1 deg (~11 km) grid from the step outputs.

Fine (11 km or better sources): terrain (WorldClim 30" DEM), air temperature / precipitation / aridity
(WorldClim 2.5'), ground temperature (MODIS 1 km long-term; south of 62 S from the 1-degree grid),
albedo (MODIS blue-sky climatology 0.05 deg, if built; else 1-degree), NDVI (MODIS/AVHRR 5 km 2019,
mapped onto the 1-degree grid's NDVI scale), impact structures (centre within the rim).
From the 1-degree grid (parent cell): rock group, mineral groups, ground ice.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, centres, load_1deg  # noqa: E402
from regrid import bilinear, parent  # noqa: E402

t0 = time.time()
G = load_1deg("earth")
T = np.load(OUT / "earth_terrain.npz")
C = np.load(OUT / "earth_climate.npz")
L = np.load(OUT / "earth_lst.npz")
N = np.load(OUT / "earth_ndvi.npz")["ndvi"]

out = {k: T[k] for k in ("elevation_m", "slope_deg", "roughness_m", "relief_m")}
water = np.load(OUT / "earth_water.npz")["water_frac"]
out["is_land"] = ((T["land_frac"] >= 0.5) & (water < 0.5)).astype(np.int8)  # Natural Earth lakes are not land
out["water_frac"] = water
for k in ("air_temp_mean_K", "air_temp_min_K", "air_temp_max_K", "air_temp_swing_K", "precipitation_mm_yr", "aridity_index"):
    out[k] = C[k]
for k in ("surface_temp_swing_K", "surface_temp_min_K"):
    fine = L[k]
    out[k] = np.where(np.isfinite(fine), fine, bilinear("earth", G[k])).astype(np.float32)
alb_file = OUT / "earth_albedo.npz"
if alb_file.exists():
    a = np.load(alb_file)["albedo"]
    lat_c = centres("earth")[0][:, None]
    # poleward of 60 deg a 12-month mean is biased by polar night: keep the 1-degree albedo there
    use = np.isfinite(a) & (np.abs(lat_c) < 60)
    out["albedo"] = np.where(use, a, bilinear("earth", G["albedo"])).astype(np.float32)
    albedo_src = "MODIS blue-sky albedo climatology 0.05 deg (60S-60N); 1-degree grid poleward"
else:
    out["albedo"] = bilinear("earth", G["albedo"])
    albedo_src = "1-degree grid (bilinear)"
# NDVI on the 1-degree grid's scale. The 5 km product has gaps (water, snow, sparse high-latitude coverage):
# fill from neighbouring cells (3x3, then 5x5), then from the 1-degree grid; source code per cell:
# 0 own pixels, 1 neighbours, 2 one-degree grid, 3 none.
nd = np.where(np.isfinite(N), 0.865 * N + 0.010, np.nan).astype(np.float32)
src = np.where(np.isfinite(nd), 0, 3).astype(np.int8)
for rad, code in ((1, 1), (2, 1)):
    tot = np.zeros_like(nd, dtype=np.float64); cnt = np.zeros_like(nd, dtype=np.float64)
    for di in range(-rad, rad + 1):
        for dj in range(-rad, rad + 1):
            v = np.roll(np.roll(nd, di, axis=0), dj, axis=1)
            ok = np.isfinite(v)
            tot += np.where(ok, v, 0); cnt += ok
    with np.errstate(all="ignore"):
        fill = (tot / cnt).astype(np.float32)
    take = ~np.isfinite(nd) & np.isfinite(fill)
    nd[take] = fill[take]; src[take] = code
par = parent("earth", G["ndvi"]).astype(np.float32)
take = ~np.isfinite(nd) & np.isfinite(par)
nd[take] = par[take]; src[take] = 2
out["ndvi"] = nd
out["ndvi_source"] = src
with np.errstate(all="ignore"):
    out["apparent_thermal_inertia"] = ((1 - out["albedo"]) / out["surface_temp_swing_K"]).astype(np.float32)
# Coastal fine cells whose 1-degree parent is sea get the class of the nearest land parent (3x3, then 5x5),
# so coastal deserts (Atacama coast, Namib, Sechura) are not dropped for missing rock data.
def filled(a1, empty):
    a = a1.copy()
    for rad in (1, 2):
        miss = np.isin(a, empty) if a.dtype == object else ~np.isfinite(a)
        if not miss.any():
            break
        for di in range(-rad, rad + 1):
            for dj in range(-rad, rad + 1):
                src = np.roll(np.roll(a1, di, axis=0), dj, axis=1)
                ok = ~(np.isin(src, empty) if a.dtype == object else ~np.isfinite(src))
                take = miss & ok
                a[take] = src[take]
                miss &= ~take
    return a


rock1 = np.where(np.isin(G["rock_group"], ["water"]) & (G["is_land"] != 1), "", G["rock_group"]).astype(object)
out["rock_group"] = parent("earth", filled(rock1, [""])).astype("U16")
out["mineral_groups"] = parent("earth", filled(G["mineral_groups"], [""])).astype("U80")
ice1 = np.where(G["is_land"] == 1, G["ground_ice_flag"], np.nan)
out["ground_ice_flag"] = parent("earth", filled(ice1, None)).astype(np.float32)

# impact structures: centre of the cell inside the rim (radius at least half a cell)
imp = json.loads((RAW / "impacts" / "impact_structures.json").read_text(encoding="utf-8"))
imp.append({"name": "Kara-Kul", "lat": 39.0167, "lon": 73.45, "diameter_km": 52.0})
lat, lon = centres("earth")
flag = np.zeros(out["is_land"].shape, np.int8)
for s in imp:
    rad = max(s["diameter_km"] / 2, 5.6)
    dlat = rad / 111.2
    rows = np.where(np.abs(lat - s["lat"]) <= dlat)[0]
    if not len(rows):
        continue
    for r in rows:
        dlon = rad / (111.2 * max(np.cos(np.radians(lat[r])), 0.05))
        d = (lon - s["lon"] + 180) % 360 - 180
        cols = np.where(np.abs(d) <= dlon)[0]
        dk = np.hypot((lat[r] - s["lat"]) * 111.2, d[cols] * 111.2 * np.cos(np.radians(lat[r])))
        flag[r, cols[dk <= rad]] = 1
out["inside_impact"] = flag
np.savez_compressed(OUT / "earth_grid.npz", **out)
meta = {"albedo_source": albedo_src, "built_s": round(time.time() - t0), "land_cells": int(out["is_land"].sum()),
        "impact_cells": int(flag.sum())}
(OUT / "earth_grid_meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print(meta)
