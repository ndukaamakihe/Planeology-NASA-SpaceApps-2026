"""
Planalogy - NASA Space Apps Challenge 2026

Module: Grid Data
Purpose: Adapter for the Data team's lat/lon grids (earth_1deg.csv / mars_1deg.csv,
or any other regular grid, e.g. 50 km cells: Earth 0.45 deg, Mars 0.84 deg).
(Generalised app copy of analogue_engine/examples/real_data/grid_1deg.py.)

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
                 (3x3 cells of the loaded grid: about 300 km at 1 deg, 150 km
                 with 50 km cells) is kept as a fallback for grids
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

Earth pre-filter ("dry land"): is_land = 1 and rock_group not ice/water, then
* with an aridity index (Science, Wojciech): aridity_index <= 0.20, i.e. UNEP
  "arid" + "hyper-arid"; semi-arid land has too much vegetation and water to
  look like Mars. Hyper-arid (< 0.05, e.g. Atacama) is the strictest option;
* without one (the present grid has none): PROVISIONAL precipitation
  < 500 mm/yr and NDVI < 0.2 (or unknown).

Climate projections (year slider). A yearly file earth_<grid>_<year>.csv may
hold only climate columns (no elevation_m): air temperatures, precipitation,
aridity. It is merged onto the base Earth grid cell by cell:
* ground temperatures by the DELTA METHOD: projections give AIR temperature,
  P2 compares GROUND temperature, so
      ground(year) = ground(today, MODIS) + [air(year) - air(reference)]
  where the reference is the earliest yearly file (the model's present), so
  the reference year reproduces today's ground values exactly;
* precipitation and aridity are replaced by the projected values;
* terrain, rock, craters, albedo, thermal inertia and ground ice keep their
  present values (no projection yet; declared as a limitation).

Resolution. Nothing here assumes 1-degree cells: the step and origin of each
planet's grid are read from the data (GridSpec), the relief uses the adjacent
cells of that grid, and points (targets, known analogs) are mapped to the
cell that contains them. Two grids are comparable when they use the same
degree step (the Data team's original "same grid on both planets") or the
same cell size in km (e.g. 50 km); anything else is refused, because the
engine requires the same spatial support on both sides. With the 1-degree
grid, cell ids and every value are exactly those of the original adapter.
"""

from __future__ import annotations

import bisect
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROTOCOL = {
    "required_metadata": ["method_id", "spatial_support"],
    "must_match": ["spatial_support"],
    "cross_body_comparable": True,
}
SUPPORT = "grid_1deg_v1"  # spatial support label of the original 1-degree grid
MINERAL_GROUPS = ["basaltic", "felsic", "clays_hydrated", "sulfates_salts", "carbonates", "iron_oxides"]
RADIUS_KM = {"earth": 6371.0, "mars": 3389.5}  # mean radii, for cell sizes in km
KEY_DECIMALS = 6  # cell keys are rounded so float noise never splits a cell


def _key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, KEY_DECIMALS), round(lon, KEY_DECIMALS))


def _wrap_lon(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def _fmt_deg(x: float) -> str:
    return f"{x:g}"


def cell_id(planet: str, lat: float, lon: float, decimals: int = 1) -> str:
    """Cell id: earth_+83.5_-077.5 (1 decimal, the original format) or earth_+12.825_-069.975."""
    return f"{planet}_{lat:+0{4 + decimals}.{decimals}f}_{lon:+0{5 + decimals}.{decimals}f}"


@dataclass(frozen=True)
class GridSpec:
    """A planet's regular lat/lon grid of cell centres, read from the data.

    lat0/lon0 are the southernmost/westernmost centres; each cell spans
    +/- half a step around its centre. ``decimals`` is the number of decimals
    needed to write every centre exactly (1 for the 1-degree grid).
    """

    planet: str
    lat_step: float
    lon_step: float
    lat0: float
    lon0: float
    n_lat: int
    n_lon: int
    decimals: int

    @classmethod
    def one_degree(cls, planet: str) -> "GridSpec":
        return cls(planet, 1.0, 1.0, -89.5, -179.5, 180, 360, 1)

    @property
    def is_1deg(self) -> bool:
        return self.lat_step == 1.0 and self.lon_step == 1.0

    @property
    def cell_km(self) -> float:
        """North-south size of a cell in km (east-west shrinks with latitude, alike on both planets)."""
        return math.radians(self.lat_step) * RADIUS_KM[self.planet]

    @property
    def wraps(self) -> bool:
        """True when the longitude cells tile the full 360 degrees."""
        return abs(self.n_lon * self.lon_step - 360.0) < 1e-6

    def centre(self, i: int, j: int) -> tuple[float, float]:
        return _key(self.lat0 + i * self.lat_step, self.lon0 + j * self.lon_step)

    def index(self, lat: float, lon: float) -> tuple[int, int] | None:
        """Row/column of the cell containing (lat, lon), or None outside the grid.

        Grids need not be global (the Mars grid has no rows south of 61.5 S):
        a point outside never snaps to the nearest edge cell.
        """
        fi = (lat - (self.lat0 - self.lat_step / 2)) / self.lat_step
        fj = (_wrap_lon(lon) - (self.lon0 - self.lon_step / 2)) / self.lon_step
        i, j = math.floor(fi + 1e-9), math.floor(fj + 1e-9)
        if i == self.n_lat and fi <= self.n_lat + 1e-9:  # on the outer edge (e.g. the pole)
            i -= 1
        j = j % self.n_lon if self.wraps else (j - 1 if j == self.n_lon and fj <= self.n_lon + 1e-9 else j)
        if not (0 <= i < self.n_lat and 0 <= j < self.n_lon):
            return None
        return i, j

    def containing(self, lat: float, lon: float) -> tuple[float, float] | None:
        """Key (centre) of the cell that contains a point, or None outside the grid."""
        ij = self.index(lat, lon)
        return None if ij is None else self.centre(*ij)

    def neighbour(self, lat: float, lon: float, di: int, dj: int) -> tuple[float, float]:
        return _key(lat + di * self.lat_step, _wrap_lon(lon + dj * self.lon_step))

    def cell_id(self, lat: float, lon: float) -> str:
        return cell_id(self.planet, lat, lon, self.decimals)

    def as_dict(self) -> dict[str, Any]:
        return {"lat_step": self.lat_step, "lon_step": self.lon_step, "lat0": self.lat0, "lon0": self.lon0,
                "n_lat": self.n_lat, "n_lon": self.n_lon, "decimals": self.decimals,
                "cell_km": round(self.cell_km, 1)}


def _step(values: list[float]) -> float:
    return round(min(b - a for a, b in zip(values, values[1:])), KEY_DECIMALS)


def _decimals(*numbers: float) -> int:
    for d in range(1, KEY_DECIMALS + 1):
        if all(abs(round(x, d) - x) < 1e-9 for x in numbers):
            return d
    return KEY_DECIMALS


def grid_spec(planet: str, grid: dict[tuple[float, float], Any]) -> GridSpec:
    """Detect step and origin from the cell centres; refuses irregular grids."""
    lats, lons = sorted({k[0] for k in grid}), sorted({k[1] for k in grid})
    if len(lats) < 2 or len(lons) < 2:
        raise ValueError(f"{planet} grid needs at least 2 distinct latitudes and longitudes to detect its step")
    lat_step, lon_step = _step(lats), _step(lons)
    for vals, step, name in ((lats, lat_step, "latitude"), (lons, lon_step, "longitude")):
        off = max(abs((v - vals[0]) / step - round((v - vals[0]) / step)) for v in vals)
        if off > 1e-4:
            raise ValueError(f"{planet} grid is not regular in {name} (step {step}): cell centres are off the lattice")
    n_lat = round((lats[-1] - lats[0]) / lat_step) + 1
    n_lon = round((lons[-1] - lons[0]) / lon_step) + 1
    return GridSpec(planet, lat_step, lon_step, lats[0], lons[0], n_lat, n_lon,
                    _decimals(lat_step, lon_step, lats[0], lons[0]))


def spatial_support(earth: GridSpec, mars: GridSpec) -> str:
    """Shared spatial-support label, or ValueError if the two grids are not comparable."""
    if earth.lat_step == mars.lat_step and earth.lon_step == mars.lon_step:
        return SUPPORT if earth.is_1deg else f"grid_{_fmt_deg(earth.lat_step)}deg_v1"
    ke, km = round(earth.cell_km / 10) * 10, round(mars.cell_km / 10) * 10
    if ke != km:
        raise ValueError(
            f"Earth cells ({_fmt_deg(earth.lat_step)} deg, about {earth.cell_km:.0f} km) and Mars cells "
            f"({_fmt_deg(mars.lat_step)} deg, about {mars.cell_km:.0f} km) are not comparable. Use the same degree "
            "step on both planets or the same size in km (50 km: Earth 0.45 deg, Mars 0.84 deg).")
    return f"grid_{ke}km_v1"


def resolution_note(earth: GridSpec, mars: GridSpec) -> str:
    if earth.is_1deg and mars.is_1deg:
        return COMMON_LIMITATIONS[-1]
    return (f"Resolution: cells of about {earth.cell_km:.0f} km on Earth ({_fmt_deg(earth.lat_step)} deg) and "
            f"{mars.cell_km:.0f} km on Mars ({_fmt_deg(mars.lat_step)} deg), far coarser than rover-scale terrain. "
            "Mars inputs coarser than the cells (climate-model temperatures, orbital hydrogen) repeat across "
            "neighbouring cells without adding detail.")


def limitations(earth: GridSpec, mars: GridSpec) -> list[str]:
    """Declared limitations for this pair of grids (identical to COMMON_LIMITATIONS at 1 degree)."""
    return COMMON_LIMITATIONS[:-1] + [resolution_note(earth, mars)]


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
    base_limitations: list[str] | None = None,
) -> dict[str, Any]:
    """Build a profile over the grid features; scales come from TAUS.

    ``base_limitations`` defaults to COMMON_LIMITATIONS (1-degree grid); pass
    ``limitations(earth_spec, mars_spec)`` for other resolutions.
    """
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
        "declared_limitations": list(base_limitations or COMMON_LIMITATIONS) + (extra_limitations or []),
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
        return {_key(float(r["lat"]), float(r["lon"])): r for r in csv.DictReader(handle)}


def _relief(grid: dict, lat: float, lon: float, spec: GridSpec | None = None) -> float | None:
    """max - min elevation over the cell and its 8 neighbours (at least 5 with data)."""
    spec = spec or GridSpec.one_degree("earth")
    values = []
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            r = grid.get(spec.neighbour(lat, lon, di, dj))
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


DRY_MAX_ARIDITY = 0.20  # Science: arid + hyper-arid (UNEP/IPCC classes)
HYPER_ARID_BELOW = 0.05  # Science: the most Mars-like land (e.g. Atacama)


DRY_LAND_RULE = "dry_v2"  # aridity or cold desert, NDVI < 0.2; bump when the rule changes (cache key)
MAX_NDVI = 0.2  # Science: below 0.2 is bare ground; removes irrigated valleys (NDVI is today's, not projected)
# Science (polar-desert definition): cold places barely evaporate, so the aridity index calls them wet
COLD_DESERT_MAX_TEMP_K = 273.15  # mean annual air temperature below 0 degC ...
COLD_DESERT_MAX_PRECIP = 250.0  # ... and precipitation below 250 mm/yr
# Provisional (ours, to confirm with Science): ice sheets that the geology map gives a rock type would
# pass the cold rule, so a cold cell must also be darker than snow/ice. Dry Valleys 0.51, Devon 0.42,
# ice sheet 0.7-0.8.
COLD_DESERT_MAX_ALBEDO = 0.6


def is_cold_desert(r: dict) -> bool:
    """Polar/cold desert climate on ice-free ground (the dry-land rule's second branch)."""
    temp, precip, albedo = _num(r, "air_temp_mean_K"), _num(r, "precipitation_mm_yr"), _num(r, "albedo")
    return (temp is not None and precip is not None and temp < COLD_DESERT_MAX_TEMP_K
            and precip < COLD_DESERT_MAX_PRECIP and (albedo is None or albedo < COLD_DESERT_MAX_ALBEDO))


def passes_earth_filter(r: dict, max_precip: float = 500.0, max_ndvi: float = MAX_NDVI,
                        max_aridity: float = DRY_MAX_ARIDITY) -> bool:
    """Dry land (Science): bare ground (NDVI < max_ndvi, or unknown), not ice or water, and either
    aridity index <= max_aridity or a cold desert (is_cold_desert). Without aridity index and air
    temperature, the provisional precipitation rule (< max_precip) applies."""
    if r.get("is_land") != "1.0" or r.get("rock_group") in ("ice", "water", ""):
        return False
    ndvi = _num(r, "ndvi")
    if ndvi is not None and ndvi >= max_ndvi:
        return False
    aridity = _num(r, "aridity_index")
    if aridity is None and _num(r, "air_temp_mean_K") is None:
        precip = _num(r, "precipitation_mm_yr")
        return precip is not None and precip < max_precip
    return (aridity is not None and aridity <= max_aridity) or is_cold_desert(r)


def is_hyper_arid(r: dict) -> bool:
    """Dry land with aridity index below HYPER_ARID_BELOW (False when the index is unknown)."""
    aridity = _num(r, "aridity_index")
    return passes_earth_filter(r) and aridity is not None and aridity < HYPER_ARID_BELOW


# ---------------------------------------------------------------- climate projections

# ground column <- air column whose projected CHANGE is added (delta method)
DELTA_COLUMNS = {"surface_temp_swing_K": "air_temp_swing_K", "surface_temp_min_K": "air_temp_min_K"}
# columns taken as projected
REPLACED_COLUMNS = ["precipitation_mm_yr", "aridity_index", "aridity_class"]
PROJECTION_NOTE = (
    "Future years: ground temperatures are today's values plus the projected change in air temperature "
    "(delta method); permafrost thaws where the mean annual air temperature rises above -1 degC; "
    "terrain, rock, craters, albedo, thermal inertia, glaciers and NDVI keep present values."
)
# Permafrost needs a mean annual air temperature below about -1 degC (simple threshold rule, provisional,
# to confirm with Science). Only cells whose ice comes from permafrost (probability >= 0.5) can thaw;
# glaciers and ice sheets keep their flag.
PERMAFROST_MAX_TEMP_K = 272.15
PERMAFROST_MIN_PROB = 0.5


def _is_projection_file(path: Path) -> bool:
    with path.open(newline="", encoding="utf-8") as handle:
        return "elevation_m" not in next(csv.reader(handle), [])


def is_projection(grid: dict) -> bool:
    """A climate-only file (no terrain columns) to be merged onto the base grid."""
    first = next(iter(grid.values()), {})
    return "elevation_m" not in first


def project(base: dict, proj: dict, ref: dict) -> dict:
    """Base Earth grid with a climate projection applied (see the module docstring).

    Cells the projection does not cover keep their terrain but lose the
    climate-dependent values (missing, never guessed).
    """
    out = {}
    for key, b in base.items():
        row = dict(b)
        p, r = proj.get(key), ref.get(key)
        for col in REPLACED_COLUMNS:
            if p is not None and col in p:
                row[col] = p[col]
            elif p is None:
                row[col] = ""
        for ground, air in DELTA_COLUMNS.items():
            g0, a1, a0 = _num(b, ground), _num(p or {}, air), _num(r or {}, air)
            if p is not None and air not in p:
                continue  # this projection does not change that column
            row[ground] = "" if None in (g0, a1, a0) else repr(g0 + (a1 - a0))
        out[key] = row
    return out


def thaws(base_row: dict, future_row: dict) -> bool:
    """Permafrost ice in base_row that the future climate of future_row thaws (see PERMAFROST_MAX_TEMP_K)."""
    ice, prob = _num(base_row, "ground_ice_flag"), _num(base_row, "permafrost_prob")
    t0, t1 = _num(base_row, "air_temp_mean_K"), _num(future_row, "air_temp_mean_K")
    if ice is None or ice < 0.5 or prob is None or prob < PERMAFROST_MIN_PROB or None in (t0, t1):
        return False
    return t0 < PERMAFROST_MAX_TEMP_K <= t1


def project_complete(base: dict, future: dict) -> dict:
    """A complete yearly grid (all columns, air climate projected, ground columns copied from today)
    made consistent with its climate: ground temperatures shift with the air (delta method against the
    present grid) and permafrost that the warming pushes above PERMAFROST_MAX_TEMP_K loses its ice flag.
    A file that brings its own ground values (different from today's) keeps them.
    Returns (grid, changed): changed is False when nothing had to be adjusted.
    """
    out, changed = {}, False
    for key, f in future.items():
        row, b = dict(f), base.get(key)
        if b is not None:
            for ground, air in DELTA_COLUMNS.items():
                g0, g1, a1, a0 = _num(b, ground), _num(f, ground), _num(f, air), _num(b, air)
                if g1 != g0 or None in (g0, a1, a0) or a1 == a0:
                    continue  # projected by the file itself, or no change in the air
                row[ground] = repr(g0 + (a1 - a0)); changed = True
            if thaws(b, f):
                row["ground_ice_flag"] = "0.0"; changed = True
        out[key] = row
    return out, changed


def with_reference_aridity(base: dict, ref: dict) -> dict:
    """Present grid + the reference file's aridity, so 'now' uses the same dry-land rule as the years."""
    out = {}
    for key, b in base.items():
        row, r = dict(b), ref.get(key)
        for col in ("aridity_index", "aridity_class"):
            if r is not None and col in r:
                row[col] = r[col]
        out[key] = row
    return out


def cell_site(
    planet: str,
    grid: dict,
    key: tuple[float, float],
    ati_table: list[float],
    data_mode: str = "real",
    *,
    spec: GridSpec | None = None,
    support: str = SUPPORT,
) -> dict:
    """Engine Site for one cell. Pass the grid's ``spec`` (from build()); detected here otherwise."""
    spec = spec or grid_spec(planet, grid)
    lat, lon = key
    r = grid[key]
    crater = _num(r, "crater_count")
    ice = _num(r, "ground_ice_flag")
    minerals = r.get("mineral_groups") or ""
    values = {
        "slope_deg": _num(r, "slope_deg"),
        "roughness_m": _num(r, "roughness_m"),
        "relief_m": _num(r, "relief_m"),
        "regional_relief_m": _relief(grid, lat, lon, spec),
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
    sid = spec.cell_id(lat, lon)
    return {
        "id": sid, "body": planet, "data_mode": data_mode, "name": None, "area_ref": f"{planet}:lat={lat},lon={lon}",
        "measurements": [
            {"feature_id": f, "value": v, "status": "missing" if v is None else "valid", "unit": units[f],
             "method_id": f"data_team_{planet}_{f}", "spatial_support": support,
             "source_ref": "Data team 1-degree grid (see parameters.csv)"}
            for f, v in values.items()
        ],
    }


def build(
    data_dir: Path,
    earth_file: str = "earth_1deg.csv",
    mars_file: str = "mars_1deg.csv",
    *,
    base_file: str | None = None,
    reference_file: str | None = None,
) -> dict[str, Any]:
    """Load both grids. ``earth_file`` selects a yearly Earth file for the year slider.

    For a climate-only yearly file, pass the present Earth file as
    ``base_file`` and the earliest yearly file as ``reference_file`` (delta
    method). For the present grid, ``reference_file`` adds that file's
    aridity so every year uses the same dry-land rule.
    Also returns each grid's GridSpec, the shared spatial-support label and
    the declared limitations for this resolution.
    """
    earth, mars = load_grid(data_dir / earth_file), load_grid(data_dir / mars_file)
    # the reference is read only when it is a climate-only file (complete yearly files need no merging)
    projected = reference_file is not None and _is_projection_file(data_dir / reference_file)
    ref = load_grid(data_dir / reference_file) if projected else None
    if base_file is not None and is_projection(earth):
        if ref is None:
            raise ValueError(f"{earth_file} holds only climate columns: it needs a reference year for the delta method")
        earth = project(load_grid(data_dir / base_file), earth, ref)
    elif base_file is not None and base_file != earth_file:
        earth, projected = project_complete(load_grid(data_dir / base_file), earth)
    elif projected:
        earth = with_reference_aridity(earth, ref)
    earth_spec, mars_spec = grid_spec("earth", earth), grid_spec("mars", mars)
    support = spatial_support(earth_spec, mars_spec)
    earth_ati, mars_ati = _percentile_table(earth, land_only=True), _percentile_table(mars, land_only=False)
    earth_sites = [cell_site("earth", earth, k, earth_ati, spec=earth_spec, support=support)
                   for k, r in earth.items() if passes_earth_filter(r)]
    return {"earth": earth, "mars": mars, "earth_ati": earth_ati, "mars_ati": mars_ati, "earth_sites": earth_sites,
            "earth_spec": earth_spec, "mars_spec": mars_spec, "support": support,
            "limitations": limitations(earth_spec, mars_spec) + ([PROJECTION_NOTE] if projected else []),
            "has_aridity": any(_num(r, "aridity_index") is not None for r in earth.values())}
