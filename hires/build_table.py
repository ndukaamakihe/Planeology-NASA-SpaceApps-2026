"""Compact land-cell table for the search tool: one .npy per column (memory-mapped and shared by
every process), over Earth land cells only, with the climate of today and of every projected year.

Future years (delta method, as in the app): air temperatures and precipitation change by the Data team's
projected change (1-degree files, bilinear to 0.1 deg); ground swing moves with the air swing, ground
minimum with the air minimum; aridity scales with the 1-degree aridity ratio. NDVI, albedo, terrain,
rock and ice stay as today.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import GRID_1DEG, OUT, centres  # noqa: E402
from regrid import bilinear  # noqa: E402

TAB = OUT / "table"
TAB.mkdir(exist_ok=True)
E = dict(np.load(OUT / "earth_grid.npz"))
land = E["is_land"] > 0
r, c = np.nonzero(land)
lat, lon = centres("earth")
np.save(TAB / "lat.npy", lat[r].astype(np.float32))
np.save(TAB / "lon.npy", lon[c].astype(np.float32))
index = np.full(land.shape, -1, np.int32)
index[r, c] = np.arange(len(r), dtype=np.int32)
np.save(TAB / "index2d.npy", index)
STATIC = ["elevation_m", "slope_deg", "roughness_m", "relief_m", "albedo", "ndvi", "apparent_thermal_inertia",
          "ground_ice_flag", "inside_impact", "ndvi_source", "water_frac"]
for k in STATIC:
    np.save(TAB / f"{k}.npy", E[k][r, c].astype(np.float32))
ROCKS = ["", "volcanic", "ancient_crust", "sedimentary", "evaporite_salt", "ice", "impact", "water"]
MINERALS = ["basaltic", "felsic", "clays_hydrated", "sulfates_salts", "carbonates", "iron_oxides"]
rg = E["rock_group"][r, c]
code = np.zeros(len(r), np.int8)
for i, name in enumerate(ROCKS):
    code[rg == name] = i
np.save(TAB / "rock_code.npy", code)
mg = E["mineral_groups"][r, c]
mask = np.zeros(len(r), np.uint8)
for i, m in enumerate(MINERALS):
    mask |= (np.char.find(mg, m) >= 0).astype(np.uint8) << i
np.save(TAB / "mineral_mask.npy", mask)
np.save(TAB / "mineral_known.npy", (mg != "").astype(np.int8))
(TAB / "vocab.json").write_text(json.dumps({"rocks": ROCKS, "minerals": MINERALS}), encoding="utf-8")
CLIM = ["air_temp_mean_K", "air_temp_min_K", "air_temp_swing_K", "surface_temp_swing_K", "surface_temp_min_K",
        "precipitation_mm_yr", "aridity_index"]
for k in CLIM:
    np.save(TAB / f"now__{k}.npy", E[k][r, c].astype(np.float32))


def onedeg(path):
    cols = ["air_temp_mean_K", "air_temp_min_K", "air_temp_swing_K", "precipitation_mm_yr", "aridity_index"]
    out = {k: np.full((180, 360), np.nan) for k in cols}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            i, j = int(round(89.5 - float(row["lat"]))), int(round(float(row["lon"]) + 179.5))
            for k in cols:
                v = row.get(k, "")
                if v not in ("", None):
                    out[k][i, j] = float(v)
    return out


now1 = onedeg(GRID_1DEG / "earth_1deg.csv")
keys = []
for sc in ("ssp245", "ssp585"):
    for y in (2030, 2050, 2070, 2090):
        f1 = onedeg(GRID_1DEG / sc / f"earth_1deg_{y}.csv")
        key = f"{sc}_{y}"
        d = {}
        for k in ("air_temp_mean_K", "air_temp_min_K", "air_temp_swing_K"):
            d[k] = E[k] + bilinear("earth", f1[k] - now1[k])
        d["surface_temp_swing_K"] = E["surface_temp_swing_K"] + bilinear("earth", f1["air_temp_swing_K"] - now1["air_temp_swing_K"])
        d["surface_temp_min_K"] = E["surface_temp_min_K"] + bilinear("earth", f1["air_temp_min_K"] - now1["air_temp_min_K"])
        with np.errstate(all="ignore"):
            pr = np.where(now1["precipitation_mm_yr"] > 0, f1["precipitation_mm_yr"] / now1["precipitation_mm_yr"], 1.0)
            ar = np.where(now1["aridity_index"] > 0, f1["aridity_index"] / now1["aridity_index"], 1.0)
        d["precipitation_mm_yr"] = E["precipitation_mm_yr"] * bilinear("earth", np.clip(pr, 0, 10))
        d["aridity_index"] = E["aridity_index"] * bilinear("earth", np.clip(ar, 0, 10))
        for k in CLIM:
            np.save(TAB / f"{key}__{k}.npy", d[k][r, c].astype(np.float32))
        keys.append(key)
        print(key, flush=True)
(TAB / "meta.json").write_text(json.dumps({"cells": int(len(r)), "years": ["now"] + keys}, indent=1), encoding="utf-8")
print("cells", len(r))
