"""Adapter for the Data team's 1x1 degree grid (earth_1deg.csv / mars_1deg.csv).

Turns grid cells into engine Sites following the Science team's P1-P10
analysis. This is data preparation specific to this dataset, so it lives
outside the engine core. Every derived quantity is computed the same way on
both planets and is documented here.

Features (Science decisions; weights and scales are PROVISIONAL):

* P1 terrain     slope_deg, roughness_m, relief_m: mean slope, standard
                 deviation of elevation and max - min elevation inside the cell,
                 computed by the Data team from a ~9-10 km DEM grid with the same
                 method on both planets (Earth WorldClim 5', Mars MOLA at 6 ppd).
                 Pure geometry, so the zero point cancels. regional_relief_m
                 (3x3 cells, about 300 km) is kept as a fallback for grids
                 without these columns.
* P2 thermal     surface_temp_swing_K (best Mars-like signal),
                 surface_temp_min_K (cold extremes only) and air_temp_swing_K
                 (air vs air, as Science asked: Earth mean monthly tmax - tmin,
                 Mars air T at 14h - 02h). air_temp_swing_K is also what climate
                 projections deliver, so the year slider changes the score.
* P3 thermophys. ati_percentile: apparent thermal inertia as its percentile
                 within its own planet (land cells), because Science says only
                 rankings are comparable. The percentile is computed once over
                 the whole planet table (a fixed dataset version), never over a
                 candidate list.
* P4 optical     albedo (same 0-1 scale on both planets).
* P7 mineralogy  mineral_groups: set of present mineral groups compared with
                 Jaccard, as Science suggested. PROXY on this grid: Earth from the
                 GLiM rock class, Mars from TES abundances (normalised, >= 20 %)
                 plus OMEGA/CRISM hydrated-mineral sites. Half weight until
                 Science replaces it with mineral lists from papers.
* P8 geology     rock_group (shared class names), half weight (overlaps P7).
                 Mars impact units take the most frequent group around them,
                 so Gale is sedimentary (rock_code keeps the original unit).
* P9 craters     inside_impact_structure: crater_count > 0 (yes/no, as Science
                 asked; density is ~0 everywhere on Earth).
* P10 water      ground_ice_flag (yes/no).
* P5, P6        not scored: P5 is a declared limitation, P6 has no Earth
                 dataset.

Earth pre-filter ("dry, bare land", PROVISIONAL thresholds): is_land = 1,
rock_group not ice/water, precipitation < 500 mm/yr, NDVI < 0.2 (or unknown).
"""

from __future__ import annotations

import bisect
import csv
from pathlib import Path
from typing import Any

PROTOCOL = {
    "required_metadata": ["method_id", "spatial_support"],
    "must_match": ["spatial_support"],
    "cross_body_comparable": True,
}
SUPPORT = "grid_1deg_v1"
MINERAL_GROUPS = ["basaltic", "felsic", "clays_hydrated", "sulfates_salts", "carbonates", "iron_oxides"]


def feature_definitions() -> list[dict[str, Any]]:
    def scalar(fid, dim, unit, text, comparator="clipped_linear_v1"):
        return {"id": fid, "dimension": dim, "definition": text, "canonical_unit": unit, "kind": "scalar",
                "comparator_id": comparator, "comparability_protocol": {"id": f"{fid}_grid1deg_v1", **PROTOCOL}}

    return [
        scalar("slope_deg", "terrain", "deg", "P1: mean slope inside the cell from a ~9-10 km DEM grid (Data team)."),
        scalar("roughness_m", "terrain", "m", "P1: standard deviation of elevation inside the cell (~9-10 km pixels)."),
        scalar("relief_m", "terrain", "m", "P1: max - min elevation inside the cell (~9-10 km pixels)."),
        scalar("regional_relief_m", "terrain", "m", "P1 fallback: max - min elevation over the 3x3 block of 1-degree cells (derived)."),
        scalar("surface_temp_swing_K", "thermal", "K", "P2: mean day minus night ground temperature (MODIS / MCD v6)."),
        scalar("surface_temp_min_K", "thermal", "K", "P2: coldest monthly/seasonal night ground temperature."),
        scalar("air_temp_swing_K", "thermal", "K", "P2: mean daily air temperature range (WorldClim tmax - tmin / MCD v6 14h - 02h)."),
        scalar("ati_percentile", "thermophysical", "1", "P3: percentile of apparent thermal inertia within its own planet."),
        scalar("albedo", "optical", "1", "P4: surface albedo, 0-1 (MODIS MCD43C3 / TES bolometric)."),
        {"id": "mineral_groups", "dimension": "mineralogy",
         "definition": "P7 proxy: present mineral groups (Earth: GLiM rock class; Mars: TES >= 20 % of non-dust minerals + hydrated sites).",
         "canonical_unit": "set", "kind": "set", "comparator_id": "jaccard_v1", "categories": MINERAL_GROUPS,
         "comparability_protocol": {"id": "mineral_groups_grid1deg_v1", **PROTOCOL}},
        {"id": "rock_group", "dimension": "geology", "definition": "P8: common rock group (GLiM grouped / SIM 3292 grouped).",
         "canonical_unit": "class", "kind": "categorical", "comparator_id": "categorical_match_v1",
         "categories": ["volcanic", "ancient_crust", "sedimentary", "evaporite_salt", "ice", "impact", "water"],
         "comparability_protocol": {"id": "rock_group_grid1deg_v1", **PROTOCOL}},
        {"id": "inside_impact_structure", "dimension": "craters", "definition": "P9: at least one impact crater centred in the cell.",
         "canonical_unit": "boolean", "kind": "boolean", "comparator_id": "boolean_match_v1",
         "comparability_protocol": {"id": "impact_grid1deg_v1", **PROTOCOL}},
        {"id": "ground_ice_flag", "dimension": "water", "definition": "P10: ground ice likely (permafrost/glacier on Earth; H2O >= 10 wt% or polar unit on Mars).",
         "canonical_unit": "boolean", "kind": "boolean", "comparator_id": "boolean_match_v1",
         "comparability_protocol": {"id": "ground_ice_grid1deg_v1", **PROTOCOL}},
    ]


TAUS = {  # PROVISIONAL scales, shared by all mission presets
    "slope_deg": (5, "deg"),
    "roughness_m": (1500, "m"),
    "relief_m": (4000, "m"),
    "air_temp_swing_K": (50, "K"),
    "regional_relief_m": (3000, "m"),
    "surface_temp_swing_K": (100, "K"),
    "surface_temp_min_K": (100, "K"),
    "ati_percentile": (0.5, "1"),
    "albedo": (0.2, "1"),
}
DIMENSION_OF = {
    "slope_deg": "terrain", "roughness_m": "terrain", "relief_m": "terrain", "air_temp_swing_K": "thermal",
    "mineral_groups": "mineralogy",
    "regional_relief_m": "terrain", "surface_temp_swing_K": "thermal", "surface_temp_min_K": "thermal",
    "ati_percentile": "thermophysical", "albedo": "optical", "rock_group": "geology",
    "inside_impact_structure": "craters", "ground_ice_flag": "water",
}
COMMON_LIMITATIONS = [
    "Pressure: every Earth site has roughly 80-150x Mars' air pressure (P5, not scored).",
    "Sunlight and UV: no comparable data; Mars has no ozone layer (P5, not scored).",
    "Dust: no Earth equivalent of the Martian dust layer (P6, not scored).",
    "Gravity and radiation are not reproduced on Earth.",
    "Resolution: 1-degree cells (about 110 km) are far coarser than rover-scale terrain.",
]


def make_profile(
    profile_id: str,
    target_id: str,
    dimension_weights: dict[str, float],
    feature_weights: dict[str, float],
    *,
    description: str,
    constraints: list[dict] | None = None,
    required: list[str] | None = None,
    extra_limitations: list[str] | None = None,
    version: str = "0.2.0",
) -> dict[str, Any]:
    """Build a profile over the grid features; scales come from TAUS."""
    features = []
    for fid, w in feature_weights.items():
        item = {"feature_id": fid, "weight": w}
        if fid in TAUS:
            item["tau"], item["tau_unit"] = TAUS[fid]
        features.append(item)
    dims = {DIMENSION_OF[f] for f in feature_weights}
    return {
        "id": profile_id, "version": version, "target_id": target_id, "calibration_status": "provisional",
        "description": description,
        "dimension_weights": {d: dimension_weights.get(d, 0) for d in sorted(dims)},
        "features": features, "required_features": required or [], "constraints": constraints or [],
        "declared_limitations": COMMON_LIMITATIONS + (extra_limitations or []),
    }


def profile(target_id: str, version: str = "0.1.0") -> dict[str, Any]:
    """Science-informed starting profile. Weights and scales are PROVISIONAL."""
    return {
        "id": "rover_navigation_science_v1", "version": version, "target_id": target_id,
        "calibration_status": "provisional",
        "description": "Weights follow the Science P1-P10 analysis (P8 half weight, P7 proxy half weight). Scales are wide enough that Earth's smaller swings do not all saturate.",
        "dimension_weights": {"terrain": 1, "thermal": 1, "thermophysical": 1, "optical": 1, "mineralogy": 0.5,
                              "geology": 0.5, "craters": 1, "water": 1},
        "features": [
            {"feature_id": "slope_deg", "weight": 1, "tau": 5, "tau_unit": "deg"},
            {"feature_id": "roughness_m", "weight": 1, "tau": 1500, "tau_unit": "m"},
            {"feature_id": "relief_m", "weight": 1, "tau": 4000, "tau_unit": "m"},
            {"feature_id": "surface_temp_swing_K", "weight": 2, "tau": 100, "tau_unit": "K"},
            {"feature_id": "surface_temp_min_K", "weight": 1, "tau": 100, "tau_unit": "K"},
            {"feature_id": "air_temp_swing_K", "weight": 1, "tau": 50, "tau_unit": "K"},
            {"feature_id": "mineral_groups", "weight": 1},
            {"feature_id": "ati_percentile", "weight": 1, "tau": 0.5, "tau_unit": "1"},
            {"feature_id": "albedo", "weight": 1, "tau": 0.2, "tau_unit": "1"},
            {"feature_id": "rock_group", "weight": 1},
            {"feature_id": "inside_impact_structure", "weight": 1},
            {"feature_id": "ground_ice_flag", "weight": 1},
        ],
        "required_features": [], "constraints": [],
        "declared_limitations": [
            "Pressure: every Earth site has roughly 80-150x Mars' air pressure (P5, not scored).",
            "Sunlight and UV: no comparable data; Mars has no ozone layer (P5, not scored).",
            "Dust: no Earth equivalent of the Martian dust layer (P6, not scored).",
            "Gravity and radiation are not reproduced on Earth.",
            "Resolution: 1-degree cells (about 110 km) are far coarser than rover-scale terrain.",
        ],
    }


def _num(row: dict, key: str) -> float | None:
    value = row.get(key, "")
    return float(value) if value not in ("", None) else None


def load_grid(path: Path) -> dict[tuple[float, float], dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {(float(r["lat"]), float(r["lon"])): r for r in csv.DictReader(handle)}


def _relief(grid: dict, lat: float, lon: float) -> float | None:
    values = []
    for dlat in (-1, 0, 1):
        for dlon in (-1, 0, 1):
            la = lat + dlat
            lo = ((lon + dlon + 180) % 360) - 180  # wrap longitude
            r = grid.get((la, lo))
            if r is not None and _num(r, "elevation_m") is not None:
                values.append(_num(r, "elevation_m"))
    return (max(values) - min(values)) if len(values) >= 5 else None


def _percentile_table(grid: dict, land_only: bool) -> list[float]:
    vals = [_num(r, "apparent_thermal_inertia") for r in grid.values()
            if (not land_only or r.get("is_land") == "1.0") and _num(r, "apparent_thermal_inertia") is not None]
    return sorted(vals)


def _percentile(table: list[float], x: float | None) -> float | None:
    if x is None or not table:
        return None
    return bisect.bisect_right(table, x) / len(table)


def passes_earth_filter(r: dict, max_precip: float = 500.0, max_ndvi: float = 0.2) -> bool:
    if r.get("is_land") != "1.0" or r.get("rock_group") in ("ice", "water", ""):
        return False
    precip, ndvi = _num(r, "precipitation_mm_yr"), _num(r, "ndvi")
    return precip is not None and precip < max_precip and (ndvi is None or ndvi < max_ndvi)


def cell_site(planet: str, grid: dict, key: tuple[float, float], ati_table: list[float], data_mode: str = "real") -> dict:
    lat, lon = key
    r = grid[key]
    crater = _num(r, "crater_count")
    ice = _num(r, "ground_ice_flag")
    minerals = r.get("mineral_groups") or ""
    values = {
        "slope_deg": _num(r, "slope_deg"),
        "roughness_m": _num(r, "roughness_m"),
        "relief_m": _num(r, "relief_m"),
        "regional_relief_m": _relief(grid, lat, lon),
        "surface_temp_swing_K": _num(r, "surface_temp_swing_K"),
        "surface_temp_min_K": _num(r, "surface_temp_min_K"),
        "air_temp_swing_K": _num(r, "air_temp_swing_K"),
        "mineral_groups": tuple(sorted(minerals.split("|"))) if minerals else None,
        "ati_percentile": _percentile(ati_table, _num(r, "apparent_thermal_inertia")),
        "albedo": _num(r, "albedo"),
        "rock_group": r.get("rock_group") or None,
        "inside_impact_structure": None if crater is None else crater > 0,
        "ground_ice_flag": None if ice is None else ice >= 0.5,
    }
    units = {d["id"]: d["canonical_unit"] for d in feature_definitions()}
    sid = f"{planet}_{lat:+05.1f}_{lon:+06.1f}"
    return {
        "id": sid, "body": planet, "data_mode": data_mode, "name": None, "area_ref": f"{planet}:lat={lat},lon={lon}",
        "measurements": [
            {"feature_id": f, "value": v, "status": "missing" if v is None else "valid", "unit": units[f],
             "method_id": f"data_team_{planet}_{f}", "spatial_support": SUPPORT,
             "source_ref": "Data team 1-degree grid (see parameters.csv)"}
            for f, v in values.items()
        ],
    }


def build(data_dir: Path, earth_file: str = "earth_1deg.csv") -> dict[str, Any]:
    """Load both grids. ``earth_file`` selects a yearly Earth file for the year slider."""
    earth, mars = load_grid(data_dir / earth_file), load_grid(data_dir / "mars_1deg.csv")
    earth_ati, mars_ati = _percentile_table(earth, land_only=True), _percentile_table(mars, land_only=False)
    earth_sites = [cell_site("earth", earth, k, earth_ati) for k, r in earth.items() if passes_earth_filter(r)]
    return {"earth": earth, "mars": mars, "earth_ati": earth_ati, "mars_ati": mars_ati, "earth_sites": earth_sites}
