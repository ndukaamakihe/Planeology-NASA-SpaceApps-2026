"""Data for the Planalogy app at 11 km (compact mode), next to a copy of the app.

Writes into <app>/data/planalogy/:
  manifest.json      the 1-degree manifest adapted: fine grids, scaled terrain tau, 11 km Mars targets, known
                     analogs as fine cell ids, "compact" block naming the files below
  cells.json         every Earth cell that is Mars-like dry land in some year (from export_web.py)
  deltas.json        1-degree climate changes per projected year (from export_web.py)
  mars_fine_a.json   Mars 0.1875 deg slope / roughness / relief (uint16, base64)
  mars_fine_b.json   Mars 0.1875 deg albedo / ATI percentile (uint16, base64)
  mars.json          the Data team's 1-degree Mars table (thermal, rock, minerals, ice, craters)

usage: python -I export_app.py <app dir> <dir with cells.json + deltas.json + engine.json>
"""
import base64
import json
import shutil
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import planalogy_hires as H  # noqa: E402
from hires_common import cell_of  # noqa: E402

app, web = Path(sys.argv[1]), Path(sys.argv[2])
D = app / "data" / "planalogy"
for f in D.glob("earth*.json"):
    f.unlink()
for f in ("cells.json", "deltas.json"):
    shutil.copy(web / f, D / f)
engine = json.loads((web / "engine.json").read_text(encoding="utf-8"))
m = json.loads((D / "manifest.json").read_text(encoding="utf-8"))

m["grid"] = {
    "earth": {"lat_step": 0.1, "lon_step": 0.1, "lat0": -89.95, "lon0": -179.95, "n_lat": 1800, "n_lon": 3600, "decimals": 2, "cell_km": 11.1},
    "mars": {"lat_step": 0.1875, "lon_step": 0.1875, "lat0": -89.90625, "lon0": -179.90625, "n_lat": 960, "n_lon": 1920, "decimals": 4, "cell_km": 11.1},
    "spatial_support": "grid_11km_v1",
}
for f in m["features"]:
    if f["id"] in H.TAU_SCALE:
        f["tau"] = round(f["tau"] * H.TAU_SCALE[f["id"]], 4)
        f["tau_note"] = "scaled for 11 km cells on ~0.93 km pixels (provisional)"
# targets: the rovers' landing sites at 11 km, plus ESA's Oxia Planum
TK = {"gale": "gale", "jezero": "jezero", "arcadia": "arcadia"}
new_targets = []
for t in m["targets"]:
    e = engine["targets"][TK[t["key"]]]
    vals = dict(e["values"])
    new_targets.append({**t, "lat": e["cell"][0], "lon": e["cell"][1], "point": {"lat": e["cell"][0], "lon": e["cell"][1]},
                        "name": t["name"], "values": vals, "note": e["label"]})
ox = engine["targets"]["oxia"]
new_targets.append({"key": "oxia", "name": "Oxia Planum (Rosalind Franklin)", "lat": ox["cell"][0], "lon": ox["cell"][1],
                    "point": {"lat": 18.16, "lon": -24.33}, "values": ox["values"], "note": ox["label"]})
m["targets"] = new_targets


def fine_id(lat, lon):
    r, c = cell_of("earth", lat, lon)
    return f"c{int(r)}_{int(c)}"


from backend_points import EARTH  # noqa: E402  (copied point list, see below)

TRAINED = json.loads((Path(__file__).parent / "presets_trained_11km.json").read_text(encoding="utf-8"))["presets"]
for p in m["presets"]:
    p["known_analogs"] = [{"name": k["name"], "id": fine_id(*EARTH[k["name"]])} for k in p["known_analogs"] if k["name"] in EARTH]
    t = TRAINED.get(p["id"])
    if t:  # mission weights trained on the 11 km grid (calibrate_soft.py), accepted by leave-one-out
        p.update(category_weights=t["category_weights"], feature_weights=t["feature_weights"], weights_used="calibrated",
                 verdict="accepted", verdict_reason=f"Trained at 11 km on {t['sites']} known analog areas; {t['validation']}")
m["files"] = {"earth": {"now": "cells.json"}, "mars": "mars.json"}
for sc in m.get("scenarios", []):
    sc["files"] = {str(y): f"compact:{sc['id']}_{y}" for y in sc["years"]}
m["compact"] = {"cells": "cells.json", "deltas": "deltas.json", "mars_fine": ["mars_fine_a.json", "mars_fine_b.json", "mars_fine_c.json"],
                "note": "Earth: only cells that are Mars-like dry land in at least one year (268,375 of 2.13 M land cells)."}
m["common_limitations"] = [x for x in m["common_limitations"] if not x.startswith("Resolution")] + [
    "Resolution: 11 km cells on both planets (Earth 0.1 deg, Mars 0.1875 deg). Rock type, minerals and ground ice still come "
    "from 1-degree data; Mars temperatures come from a ~200 km climate model.",
    "Only cells that are Mars-like dry land in some year are included, so 'dry land only' cannot be switched off at 11 km."]
m["resolution_note"] = "11 km grid built from WorldClim 2.1, MODIS (OpenLandMap), MOLA and TES; see the Analog Atlas for the method."
(D / "manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")

# Mars fine fields
M = H.mars()
if H.USE_TES_TI and "ti_percentile" in M:
    pct = M["ti_percentile"].astype(np.float64)
else:
    a = M["apparent_thermal_inertia"].astype(np.float64)
    tab = np.sort(a[np.isfinite(a)])
    pct = np.full(a.shape, np.nan)
    ok = np.isfinite(a)
    pct[ok] = np.searchsorted(tab, a[ok], side="right") / len(tab)


def q(x, s):
    x = np.asarray(x, np.float64)
    return np.where(np.isfinite(x), np.clip(np.round(x * s), 0, 65534), 65535).astype("<u2")


enc = lambda x: base64.b64encode(np.ascontiguousarray(x).tobytes()).decode()
fa = {"shape": [960, 1920], "scale": {"slope_deg": 100, "roughness_m": 1, "relief_m": 1},
      "cols": {"slope_deg": enc(q(M["slope_deg"], 100)), "roughness_m": enc(q(M["roughness_m"], 1)), "relief_m": enc(q(M["relief_m"], 1))}}
fb = {"shape": [960, 1920], "scale": {"albedo": 10000, "ati_percentile": 10000},
      "cols": {"albedo": enc(q(M["albedo"], 10000)), "ati_percentile": enc(q(pct, 10000))}}
(D / "mars_fine_a.json").write_text(json.dumps(fa, separators=(",", ":")), encoding="utf-8")
(D / "mars_fine_b.json").write_text(json.dumps(fb, separators=(",", ":")), encoding="utf-8")
# 11 km rock group, ground ice and crater flag for picked Mars points
ROCKS = ["", "volcanic", "ancient_crust", "sedimentary", "evaporite_salt", "ice", "impact", "water"]
rc = np.zeros(M["rock_group"].shape, "<u2")
for i, nm in enumerate(ROCKS):
    rc[M["rock_group"] == nm] = i
crat = (M["inside_crater"] if "inside_crater" in M else (M["crater_count_1deg"] > 0)).astype("<u2")
fc_ = {"shape": [960, 1920], "kinds": {"rock_group": "rock", "ground_ice_flag": "bool", "inside_impact_structure": "bool"},
       "rocks": ROCKS, "cols": {"rock_group": enc(rc), "ground_ice_flag": enc((M["ground_ice_flag"] >= 0.5).astype("<u2")),
                                "inside_impact_structure": enc(crat)}}
(D / "mars_fine_c.json").write_text(json.dumps(fc_, separators=(",", ":")), encoding="utf-8")
for f in sorted(D.iterdir()):
    print(f.name, round(f.stat().st_size / 1e6, 2), "MB")
