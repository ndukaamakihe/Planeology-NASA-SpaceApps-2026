"""
Planalogy - NASA Space Apps Challenge 2026

Module: Web Export
Purpose: Export what a static web page needs to rank every Earth cell against
any Mars cell in the browser, for any weights, preset or year.

The browser reproduces the engine exactly for this grid:
  * per-feature similarity with the engine's comparators and the fixed scales
    listed in the manifest (clipped linear: s = 1 - min(1, |x - t| / tau);
    categorical / boolean: 1 if equal else 0);
  * score = sum_j w_j s_j / sum_j w_j with the engine's effective weights,
    requirements and ordering (web/app/js/scoring.js).
Derived features (regional relief over 3x3 cells, thermal-inertia percentile
within each planet) are computed here, once per planet table, exactly as in
backend/grid_data.py. Values are exported unrounded so the browser gives the
engine's numbers bit for bit; a test checks it under Node.js.

Any regular grid works (1 degree, 50 km, ...): the manifest carries each
planet's grid (step, origin, cell size in km) so the browser can find the
Mars cell under a click and draw cells of the right size.

Size. The artifact that hosts the app takes at most 16 MB. When the data
files would exceed SIZE_BUDGET (e.g. 50 km cells: ~100k Earth and ~90k Mars
cells), they are written gzip-compressed (.json.gz, about 4-5x smaller);
values are unchanged, so the bit-for-bit check still holds. The 1-degree
grid stays plain JSON.

Output (default web/app/data/planalogy/, read by the Planalogy web app):
  manifest.json              grid, features (comparator, tau), categories, targets, presets, years, files
  earth.json[.gz]            every Earth land cell: id, lat, lon, feature values, dry_bare flag
  earth_<year>.json[.gz]     per year: id + only the climate-dependent columns (YEAR_COLUMNS);
                             terrain, rock type and craters come from earth.json
  mars.json[.gz]             every Mars cell: lat, lon, feature values

    python -m backend.web_export [--data data/grid_1deg] [--out web/app/data/planalogy]
                                 [--no-calibration] [--gzip | --no-gzip]
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import Any

from analogue_engine import to_json

from backend import engine_service as es
from backend import grid_data as g
from backend.analog_presets import CELLS, PRESETS, analog_id, target_key

FEATURES = ["regional_relief_m", "surface_temp_swing_K", "surface_temp_min_K", "ati_percentile",
            "albedo", "rock_group", "inside_impact_structure", "ground_ice_flag"]
LABELS = {
    "regional_relief_m": "Regional relief", "surface_temp_swing_K": "Day–night ground temperature swing",
    "surface_temp_min_K": "Coldest ground temperature", "ati_percentile": "Thermal inertia (rank within planet)",
    "albedo": "Albedo", "rock_group": "Rock type", "inside_impact_structure": "Impact structure",
    "ground_ice_flag": "Ground ice",
}
CATEGORY_LABELS = {"terrain": "Terrain", "thermal": "Day–night temperature", "thermophysical": "Thermal inertia",
                   "optical": "Albedo", "geology": "Rock type", "craters": "Impact structure", "water": "Ground ice"}
# Columns that change with climate (Science: "Future Mars analogs under climate change").
# Yearly files carry only these, so each year adds about a third of the base size.
YEAR_COLUMNS = ["surface_temp_swing_K", "surface_temp_min_K", "ati_percentile", "ground_ice_flag", "dry_bare"]

TARGET_KEYS = {"Gale Crater (Curiosity)": "gale", "Jezero Crater (Perseverance)": "jezero",
               "Arcadia Planitia (approx.)": "arcadia"}
SIZE_BUDGET = 12_000_000  # bytes of uncompressed data files before switching to gzip (artifact limit: 16 MB)


def _feature_specs() -> list[dict[str, Any]]:
    defs = {d["id"]: d for d in g.feature_definitions()}
    out = []
    for f in FEATURES:
        d = defs[f]
        spec = {"id": f, "label": LABELS[f], "category": g.DIMENSION_OF[f], "kind": d["kind"],
                "comparator": d["comparator_id"], "unit": d["canonical_unit"]}
        if f in g.TAUS:
            spec["tau"] = g.TAUS[f][0]
        out.append(spec)
    return out


def _values(site: dict) -> list:
    vals = {m["feature_id"]: m["value"] for m in site["measurements"]}
    return [vals[f] for f in FEATURES]


def _site(planet: str, data: dict, key: tuple[float, float]) -> dict:
    return g.cell_site(planet, data[planet], key, data[f"{planet}_ati"],
                       spec=data[f"{planet}_spec"], support=data["support"])


def _earth_rows(data: dict) -> list[list]:
    """Every Earth land cell, with the dry/bare pre-filter as a flag (not a cut)."""
    rows = []
    for key, r in data["earth"].items():
        if r.get("is_land") != "1.0":
            continue
        site = _site("earth", data, key)
        rows.append([site["id"], key[0], key[1]] + _values(site) + [g.passes_earth_filter(r)])
    return rows


def _mars_rows(data: dict) -> list[list]:
    rows = []
    for key in data["mars"]:
        vals = _values(_site("mars", data, key))
        if any(v is not None for v in vals):
            rows.append([key[0], key[1]] + vals)
    return rows


def _encode(payload: dict) -> bytes:
    return json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _preset_entry(preset: dict, data_dir: Path, calibrate: bool, data: dict) -> dict[str, Any]:
    profile, info = es.preset_profile(preset["id"], data_dir, calibrate=calibrate)
    if not isinstance(profile, dict):
        from analogue_engine import profile_to_dict
        profile = profile_to_dict(profile)
    return {
        "id": preset["id"], "name": preset["name"], "mission": preset["mission"], "why": preset["why"],
        "target": TARGET_KEYS[preset["target"]],
        "category_weights": profile["dimension_weights"],
        "feature_weights": {f["feature_id"]: f["weight"] for f in profile["features"]},
        "requirements": [{"feature": c["feature_id"], "equals": c["value"], "id": c["id"]}
                         for c in profile.get("constraints", []) if c["type"] == "equals"],
        "required_features": profile.get("required_features", []),
        "weights_used": info.get("weights_used"), "verdict": info.get("verdict"),
        "verdict_reason": info.get("verdict_reason"),
        "known_analogs": [{"name": n, "id": analog_id(data, n)} for n in preset["known_analogs"]],
        "declared_limitations": profile.get("declared_limitations", []),
    }


def export(data_dir: Path, out_dir: Path, calibrate: bool = True, compress: bool | None = None) -> dict[str, Any]:
    """Write the app's data files. ``compress``: None = gzip only if over SIZE_BUDGET."""
    out_dir.mkdir(parents=True, exist_ok=True)
    years = [None] + es.yearly_files(data_dir)
    base = es.load_grid(str(data_dir))

    payloads: dict[str, dict] = {"mars": {"columns": ["lat", "lon"] + FEATURES, "rows": _mars_rows(base)}}
    full_cols = ["id", "lat", "lon"] + FEATURES + ["dry_bare"]
    earth_names: dict[str, str] = {}
    for item in years:
        if item is None:
            name, payload = "earth", {"columns": full_cols, "rows": _earth_rows(base)}
        else:
            year, fname = item
            rows = _earth_rows(es.load_grid(str(data_dir), fname))
            keep = [full_cols.index(c) for c in ["id"] + YEAR_COLUMNS]
            name, payload = f"earth_{year}", {"columns": ["id"] + YEAR_COLUMNS, "base": "earth.json",
                                              "rows": [[r[i] for i in keep] for r in rows]}
        payloads[name] = payload
        earth_names["now" if item is None else str(item[0])] = name

    blobs = {name: _encode(p) for name, p in payloads.items()}
    use_gzip = sum(len(b) for b in blobs.values()) > SIZE_BUDGET if compress is None else compress
    ext = ".json.gz" if use_gzip else ".json"
    written = set()
    for name, payload in payloads.items():
        if "base" in payload and use_gzip:  # yearly files name their (compressed) base file
            payload["base"] = "earth" + ext
            blobs[name] = _encode(payload)
        path = out_dir / (name + ext)
        path.write_bytes(gzip.compress(blobs[name], compresslevel=9, mtime=0) if use_gzip else blobs[name])
        written.add(path.name)
    for pattern in ("earth*.json", "earth*.json.gz", "mars*.json", "mars*.json.gz", "sims_*.json", "cells*.json"):
        for stale in out_dir.glob(pattern):
            if stale.name not in written:
                stale.unlink()
    files: dict[str, Any] = {"earth": {k: v + ext for k, v in earth_names.items()}, "mars": "mars" + ext}

    targets = []
    for n in CELLS:
        key = target_key(base, n)
        if key is None or key not in base["mars"]:
            raise ValueError(f"No Mars grid cell contains the target {n} {CELLS[n]}")
        targets.append({"key": TARGET_KEYS[n], "name": n, "lat": key[0], "lon": key[1],
                        "point": dict(zip(("lat", "lon"), CELLS[n])),
                        "values": dict(zip(FEATURES, _values(_site("mars", base, key))))})
    manifest = {
        "schema": "planalogy.web.v3",
        "model": "analogue_engine.adapted_gower@0.2.0",
        "data_mode": "real",
        "grid": {"earth": base["earth_spec"].as_dict(), "mars": base["mars_spec"].as_dict(),
                 "spatial_support": base["support"]},
        "features": _feature_specs(),
        "categories": [{"id": c, "label": l} for c, l in CATEGORY_LABELS.items()],
        "targets": targets,
        "presets": [_preset_entry(p, data_dir, calibrate, base) for p in PRESETS],
        "years": ["now"] + [y for y, _ in years[1:]],
        "year_columns": YEAR_COLUMNS,
        "files": files,
        "compression": "gzip" if use_gzip else "none",
        "dry_bare_rule": "precipitation < 500 mm/yr, NDVI < 0.2 (or unknown), not ice or water (provisional, Science)",
        "thresholds": {"strong_at_least": 75, "weak_at_most": 40},
        "common_limitations": base["limitations"],
    }
    (out_dir / "manifest.json").write_text(to_json(manifest) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str]) -> None:
    args = list(argv)
    data_dir, out_dir = es.GRID_DIR, es.PROJECT_ROOT / "web" / "app" / "data" / "planalogy"
    if "--data" in args:
        i = args.index("--data"); data_dir = Path(args[i + 1]); del args[i:i + 2]
    if "--out" in args:
        i = args.index("--out"); out_dir = Path(args[i + 1]); del args[i:i + 2]
    compress = True if "--gzip" in args else False if "--no-gzip" in args else None
    m = export(data_dir, out_dir, calibrate="--no-calibration" not in args, compress=compress)
    sizes = {p.name: p.stat().st_size for p in sorted(out_dir.glob("*.json*"))}
    grid = m["grid"]
    print(f"exported to {out_dir}: grid Earth {grid['earth']['lat_step']} deg / Mars {grid['mars']['lat_step']} deg "
          f"({grid['spatial_support']}), compression {m['compression']}; years {m['years']}; files {sizes}")


if __name__ == "__main__":
    main(sys.argv[1:])
