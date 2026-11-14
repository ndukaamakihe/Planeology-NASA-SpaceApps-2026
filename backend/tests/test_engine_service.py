"""Engine service on a tiny SYNTHETIC grid (no real data needed).

Run from the repository root:
    python -m pytest backend/tests -q
"""

from __future__ import annotations

import csv
import math
import json
from pathlib import Path

import pytest

from backend import engine_service as es
from backend.analog_presets import CELLS

COLUMNS = ["lat", "lon", "is_land", "elevation_m", "surface_temp_swing_K", "surface_temp_min_K",
           "apparent_thermal_inertia", "albedo", "rock_group", "crater_count", "ground_ice_flag",
           "precipitation_mm_yr", "ndvi", "slope_deg", "roughness_m", "relief_m", "air_temp_swing_K",
           "mineral_groups"]
MINERALS = ["basaltic|clays_hydrated", "felsic|clays_hydrated", "carbonates", "basaltic", "sulfates_salts|carbonates"]


def _earth_rows(swing_shift: float = 0.0):
    rows = []
    for i, lat in enumerate([20.5, 21.5, 22.5, 23.5, 24.5]):
        for j, lon in enumerate([10.5, 11.5, 12.5, 13.5, 14.5]):
            k = i * 5 + j
            rows.append({
                "lat": lat, "lon": lon, "is_land": "1.0", "elevation_m": 300 + 150 * ((i * j) % 4),
                "surface_temp_swing_K": 10 + k + (swing_shift if k == 12 else 0), "surface_temp_min_K": 250 - k,
                "apparent_thermal_inertia": 0.02 + 0.004 * k, "albedo": 0.15 + 0.01 * (k % 10),
                "rock_group": ["sedimentary", "volcanic", "ancient_crust"][k % 3],
                "crater_count": 1 if k % 7 == 0 else 0, "ground_ice_flag": 1 if k % 4 == 0 else 0,
                "precipitation_mm_yr": 100, "ndvi": 0.1,
                "slope_deg": 0.2 + 0.1 * k, "roughness_m": 40 + 10 * k, "relief_m": 200 + 50 * ((i * j) % 5),
                "air_temp_swing_K": 6 + 0.4 * k + (swing_shift if k == 12 else 0), "mineral_groups": MINERALS[k % 5],
            })
    return rows


def _mars_rows():
    rows = []
    for lat, lon in CELLS.values():  # targets are points: build the 3x3 block around their 1-degree cell
        lat0, lon0 = math.floor(lat) + 0.5, math.floor(lon) + 0.5
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                rows.append({
                    "lat": lat0 + dlat, "lon": lon0 + dlon, "is_land": "1.0", "elevation_m": -2500 + 400 * dlat,
                    "surface_temp_swing_K": 80, "surface_temp_min_K": 185, "apparent_thermal_inertia": 0.01,
                    "albedo": 0.2, "rock_group": "sedimentary", "crater_count": 5, "ground_ice_flag": 0,
                    "precipitation_mm_yr": "", "ndvi": "",
                    "slope_deg": 3.2, "roughness_m": 900 + 50 * dlat, "relief_m": 3900, "air_temp_swing_K": 44,
                    "mineral_groups": "basaltic|clays_hydrated",
                })
    return rows


def _write(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def grid(tmp_path):
    _write(tmp_path / "earth_1deg.csv", _earth_rows())
    _write(tmp_path / "mars_1deg.csv", _mars_rows())
    return tmp_path


def test_list_presets():
    ids = [p["id"] for p in es.list_presets()]
    assert ids == ["rover_navigation", "sample_science", "thermal_environment", "ice_prospecting"]


@pytest.mark.parametrize("preset", ["rover_navigation", "sample_science", "thermal_environment", "ice_prospecting"])
def test_run_preset_payload(grid, preset):
    out = es.run_preset(preset, data_dir=grid, top_n=5, calibrate=False, cache_file=None)
    assert out["counts"]["ranked"] == len(out["heatmap"]["rows"]) > 0
    positions = [s["position"] for s in out["sites"]]
    assert positions == sorted(positions) and len(out["sites"]) <= 5
    scores = [s["score_0_100"] for s in out["sites"]]
    assert scores == sorted(scores, reverse=True)
    assert all({"headline", "matches", "missing", "coverage_pct", "lat", "lon"} <= set(s) for s in out["sites"])
    assert out["map_data"]["type"] == "FeatureCollection"
    assert out["declared_limitations"]
    json.loads(json.dumps(out, allow_nan=False))


def test_ice_preset_only_ranks_sites_with_ice(grid):
    out = es.run_preset("ice_prospecting", data_dir=grid, top_n=50, calibrate=False, cache_file=None)
    with_ice = sum(1 for r in _earth_rows() if r["ground_ice_flag"] == 1)
    assert 0 < out["counts"]["ranked"] <= with_ice
    assert all(req["status"] == "satisfied" for s in out["sites"] for req in s["requirements"])


def test_calibration_without_known_analogs_keeps_science_weights(grid):
    out = es.run_preset("rover_navigation", data_dir=grid, top_n=3, calibrate=True, cache_file=None)
    assert out["calibration"]["verdict"] == "not_validated"
    assert out["calibration"]["weights_used"] == "science (start)"


def test_missing_data_folder_is_explained(tmp_path):
    with pytest.raises(es.DataNotFound) as e:
        es.run_preset("rover_navigation", data_dir=tmp_path / "nope", calibrate=False, cache_file=None)
    assert "data/grid_1deg" in str(e.value)


def test_year_slider(grid):
    msg = es.run_preset_over_years("rover_navigation", data_dir=grid, calibrate=False, cache_file=None)
    assert "at least two" in msg["message"]
    _write(grid / "earth_1deg_2030.csv", _earth_rows())
    _write(grid / "earth_1deg_2050.csv", _earth_rows(swing_shift=30))  # interior cell gets a bigger swing (synthetic)
    # thermal preset: temperature weighs enough for +30 K to move the score past the 2-point threshold
    out = es.run_preset_over_years("thermal_environment", data_dir=grid, calibrate=False, cache_file=None)
    assert out["years"] == [2030, 2050]
    gainers = {t["candidate_id"]: t for t in out["biggest_gainers"]}
    assert gainers["earth_+22.5_+012.5"]["status"] == "gaining"


def test_year_slider_reads_scenario_folders(grid):
    for scen, shift in (("ssp245", 5), ("ssp585", 15)):
        (grid / scen).mkdir()
        for year in (2050, 2090):
            _write(grid / scen / f"earth_1deg_{year}.csv", _earth_rows(swing_shift=shift))
    assert es.scenarios(grid) == ["ssp245", "ssp585"]
    assert es.yearly_files(grid, "ssp585") == [(2050, "ssp585/earth_1deg_2050.csv"), (2090, "ssp585/earth_1deg_2090.csv")]
    out = es.run_preset_over_years("thermal_environment", data_dir=grid, calibrate=False, cache_file=None,
                                   scenario="ssp585", include_baseline=True)
    assert out["years"] == [es.BASELINE_YEAR, 2050, 2090] and out["scenario"] == "ssp585"
