"""Browser data for the Analog Atlas explorer: every 11 km cell that is Mars-like dry land in at least one
year (today or any projection), packed as base64 typed arrays, plus the 1-degree climate changes per
projected year (the page rebuilds future values with the same bilinear delta method as the tool),
the Mars target values and the mission profiles.

usage: python -I export_web.py <out dir>
"""
import base64
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import planalogy_hires as H  # noqa: E402
from hires_common import GRID_1DEG, cell_of  # noqa: E402

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
KEYS = json.loads((H.TAB / "meta.json").read_text())["years"]  # now + 8 projections
S = H.static()
pools = {k: H.dry(H.climate(k))[0] for k in KEYS}
u = np.zeros(len(S["lat"]), bool)
for p in pools.values():
    u |= p
sel = np.nonzero(u)[0]
lat, lon = np.asarray(S["lat"])[sel], np.asarray(S["lon"])[sel]
r, c = cell_of("earth", lat, lon)


def q(a, scale, dtype, lo, hi, miss):
    a = np.asarray(a, np.float64)
    v = np.where(np.isfinite(a), np.clip(np.round(a * scale), lo, hi), miss)
    return v.astype(dtype)


now = H.climate("now")
cols = {
    "r": r.astype(np.uint16), "c": c.astype(np.uint16),
    "slope": q(np.asarray(S["slope_deg"])[sel], 100, np.uint16, 0, 65534, 65535),
    "rough": q(np.asarray(S["roughness_m"])[sel], 1, np.uint16, 0, 65534, 65535),
    "relief": q(np.asarray(S["relief_m"])[sel], 1, np.uint16, 0, 65534, 65535),
    "albedo": q(np.asarray(S["albedo"])[sel], 10000, np.uint16, 0, 65534, 65535),
    "ati": q(S["ati_percentile"][sel], 10000, np.uint16, 0, 65534, 65535),
    "ndvi": q(np.asarray(S["ndvi"])[sel], 1000, np.int16, -1000, 1000, -32768),
    "rock": np.asarray(S["rock_code"])[sel].astype(np.uint8),
    "minerals": np.asarray(S["minerals"])[sel].astype(np.uint8),
    "flags": ((np.asarray(S["inside_impact"])[sel] >= 0.5).astype(np.uint8)
              | ((np.asarray(S["ground_ice_flag"])[sel] >= 0.5).astype(np.uint8) << 1)
              | (np.asarray(S["mineral_known"])[sel].astype(np.uint8) << 2)),
    "elev": q(np.asarray(S["elevation_m"])[sel], 1, np.int16, -32000, 32000, -32768),
    "sswing": q(now["surface_temp_swing_K"][sel], 10, np.int16, -32000, 32000, -32768),
    "smin": q(now["surface_temp_min_K"][sel], 10, np.int16, -32000, 32000, -32768),
    "aswing": q(now["air_temp_swing_K"][sel], 10, np.int16, -32000, 32000, -32768),
    "tmean": q(now["air_temp_mean_K"][sel] - 273.15, 10, np.int16, -32000, 32000, -32768),
    "precip": q(now["precipitation_mm_yr"][sel], 1, np.int16, 0, 32000, -32768),
    "arid": q(now["aridity_index"][sel], 1000, np.int16, 0, 32000, -32768),
    "dry": sum((pools[k][sel].astype(np.uint16) << i) for i, k in enumerate(KEYS)).astype(np.uint16),
}
enc = lambda a: base64.b64encode(np.ascontiguousarray(a).astype(a.dtype.newbyteorder("<")).tobytes()).decode()
DT = {np.dtype(np.uint16): "u16", np.dtype(np.int16): "i16", np.dtype(np.uint8): "u8"}
cells = {"n": int(len(sel)), "keys": KEYS,
         "scale": {"slope": 100, "rough": 1, "relief": 1, "albedo": 10000, "ati": 10000, "ndvi": 1000, "elev": 1,
                   "sswing": 10, "smin": 10, "aswing": 10, "tmean": 10, "precip": 1, "arid": 1000},
         "cols": {k: {"t": DT[v.dtype], "b64": enc(v)} for k, v in cols.items()}}
(out / "cells.json").write_text(json.dumps(cells, separators=(",", ":")), encoding="utf-8")


def onedeg(path):
    names = ["air_temp_mean_K", "air_temp_min_K", "air_temp_swing_K", "precipitation_mm_yr", "aridity_index"]
    o = {k: np.full((180, 360), np.nan) for k in names}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            i, j = int(round(89.5 - float(row["lat"]))), int(round(float(row["lon"]) + 179.5))
            for k in names:
                v = row.get(k, "")
                if v not in ("", None):
                    o[k][i, j] = float(v)
    return o


now1 = onedeg(GRID_1DEG / "earth_1deg.csv")
deltas = {}
for k in KEYS[1:]:
    sc, y = k.split("_")
    f1 = onedeg(GRID_1DEG / sc / f"earth_1deg_{y}.csv")
    with np.errstate(all="ignore"):
        pr = np.where(now1["precipitation_mm_yr"] > 0, f1["precipitation_mm_yr"] / now1["precipitation_mm_yr"], 1.0)
        ar = np.where(now1["aridity_index"] > 0, f1["aridity_index"] / now1["aridity_index"], 1.0)
    deltas[k] = {
        "dTmean": enc(q(f1["air_temp_mean_K"] - now1["air_temp_mean_K"], 100, np.int16, -32000, 32000, -32768)),
        "dTmin": enc(q(f1["air_temp_min_K"] - now1["air_temp_min_K"], 100, np.int16, -32000, 32000, -32768)),
        "dAswing": enc(q(f1["air_temp_swing_K"] - now1["air_temp_swing_K"], 100, np.int16, -32000, 32000, -32768)),
        "rP": enc(q(np.clip(pr, 0, 10), 1000, np.int16, 0, 32000, -32768)),
        "rAI": enc(q(np.clip(ar, 0, 10), 1000, np.int16, 0, 32000, -32768)),
    }
(out / "deltas.json").write_text(json.dumps({"scale": {"d": 100, "r": 1000}, "keys": KEYS[1:], "years": deltas},
                                            separators=(",", ":")), encoding="utf-8")

# engine: features, mission profiles, Mars targets
man = H.manifest()
targets = {}
for key, (la, lo, label) in H.TARGET_POINTS.items():
    tv = H.target_values(la, lo)
    targets[key] = {"label": label, "cell": tv.pop("_cell"), "values": tv}
for key, (la, lo), label in (("oxia", (18.16, -24.33), "Oxia Planum, ESA Rosalind Franklin landing site"),
                             ("deuteronilus", (43.9, 24.4), "Deuteronilus Mensae (candidate ice landing region)")):
    tv = H.target_values(la, lo)
    targets[key] = {"label": label, "cell": tv.pop("_cell"), "values": tv}
engine = {"features": man["features"], "categories": man["categories"], "tau_scale": H.TAU_SCALE,
          "presets": [{k: p[k] for k in ("id", "name", "mission", "target", "category_weights", "feature_weights", "requirements")}
                      for p in man["presets"]],
          "targets": targets, "rocks": S["rocks"], "minerals": H.MINERALS}
(out / "engine.json").write_text(json.dumps(engine, ensure_ascii=False, indent=0), encoding="utf-8")
for f in ("cells.json", "deltas.json", "engine.json"):
    print(f, round((out / f).stat().st_size / 1e6, 2), "MB")
print("cells", len(sel))
