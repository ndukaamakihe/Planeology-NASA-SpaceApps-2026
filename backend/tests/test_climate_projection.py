"""Year slider with climate-only projection files, on a SYNTHETIC grid.

Projection files (earth_1deg_<year>.csv) carry only climate columns: air
temperatures, precipitation and the aridity index. They are merged onto the
present grid with the delta method, and the dry-land rule becomes Science's
aridity <= 0.20 (hyper-arid < 0.05 as the strict option).
"""

from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from analogue_engine import rank
from backend import engine_service as es
from backend import grid_data as g
from backend import web_export as we
from backend.tests.test_engine_service import _earth_rows, _mars_rows, _write

ROOT = Path(__file__).resolve().parents[2]
SCORING = ROOT / "web" / "app" / "js" / "scoring.js"
NODE = shutil.which("node")
PROJ_COLUMNS = ["lat", "lon", "air_temp_mean_K", "air_temp_min_K", "air_temp_max_K", "air_temp_swing_K",
                "precipitation_mm_yr", "aridity_index", "aridity_class"]


def _aridity(k: int, future: bool) -> float:
    if k < 10:
        return 0.06 if future and k < 5 else 0.03  # hyper-arid; 5 cells lose it in the future
    if k < 20:
        return 0.15  # arid
    return 0.18 if future else 0.35  # semi-arid today, arid in the future (entering)


def _projection_rows(future: bool):
    rows = []
    for k, base in enumerate(_earth_rows()):
        rows.append({
            "lat": base["lat"], "lon": base["lon"], "air_temp_mean_K": 290 + (3 if future else 0),
            "air_temp_min_K": 270 - k + (1.5 if future else 0), "air_temp_max_K": 305,
            "air_temp_swing_K": 12 + 0.1 * k + (2 if future else 0), "precipitation_mm_yr": 80,
            "aridity_index": _aridity(k, future), "aridity_class": "arid",
        })
    return rows


def _write_proj(path: Path, rows):
    with path.open("w", newline="", encoding="utf-8") as h:
        w = csv.DictWriter(h, fieldnames=PROJ_COLUMNS)
        w.writeheader()
        w.writerows(rows)


@pytest.fixture
def grid(tmp_path):
    d = tmp_path / "grid"
    d.mkdir()
    _write(d / "earth_1deg.csv", _earth_rows())
    _write(d / "mars_1deg.csv", _mars_rows())
    _write_proj(d / "earth_1deg_2020.csv", _projection_rows(future=False))  # reference: the model's present
    _write_proj(d / "earth_1deg_2050.csv", _projection_rows(future=True))
    return d


def _value(site, fid):
    return next(m["value"] for m in site["measurements"] if m["feature_id"] == fid)


def test_delta_method_reference_year_reproduces_today(grid):
    now = es.load_grid(str(grid))
    ref = es.load_grid(str(grid), "earth_1deg_2020.csv")
    fut = es.load_grid(str(grid), "earth_1deg_2050.csv")
    for key, r in now["earth"].items():
        for col in ("surface_temp_swing_K", "surface_temp_min_K"):
            assert g._num(ref["earth"][key], col) == g._num(r, col)  # exactly today's ground values
        assert g._num(fut["earth"][key], "surface_temp_swing_K") == pytest.approx(g._num(r, "surface_temp_swing_K") + 2)
        assert g._num(fut["earth"][key], "surface_temp_min_K") == pytest.approx(g._num(r, "surface_temp_min_K") + 1.5)
        assert fut["earth"][key]["elevation_m"] == r["elevation_m"]  # terrain is not projected
    assert g.PROJECTION_NOTE in now["limitations"] and fut["has_aridity"]


def test_dry_land_follows_aridity_and_the_year(grid):
    now = es.load_grid(str(grid))
    fut = es.load_grid(str(grid), "earth_1deg_2050.csv")
    assert len(now["earth_sites"]) == 20  # 5 semi-arid cells (aridity 0.35) are not dry land today
    assert len(fut["earth_sites"]) == 25  # ... and enter in 2050 (0.18 <= 0.20)
    hyper_now = sum(g.is_hyper_arid(r) for r in now["earth"].values())
    hyper_fut = sum(g.is_hyper_arid(r) for r in fut["earth"].values())
    assert (hyper_now, hyper_fut) == (10, 5)


def test_threshold_edges():
    row = {"is_land": "1.0", "rock_group": "sedimentary", "aridity_index": "0.2"}
    assert g.passes_earth_filter(row) and not g.is_hyper_arid(row)
    assert not g.passes_earth_filter({**row, "aridity_index": "0.2001"})
    assert g.is_hyper_arid({**row, "aridity_index": "0.0499"}) and not g.is_hyper_arid({**row, "aridity_index": "0.05"})
    assert not g.passes_earth_filter({**row, "rock_group": "water", "aridity_index": "0.01"})
    old = {"is_land": "1.0", "rock_group": "sedimentary", "precipitation_mm_yr": "100", "ndvi": "0.1"}
    assert g.passes_earth_filter(old) and not g.is_hyper_arid(old)  # no index: provisional rule, never hyper-arid


def test_cold_desert_and_bare_ground_rules():
    # Science: polar deserts count (mean air temperature < 0 degC, precipitation < 250 mm), NDVI must be < 0.2
    devon = {"is_land": "1.0", "rock_group": "sedimentary", "aridity_index": "1.13", "air_temp_mean_K": "255.6",
             "precipitation_mm_yr": "183.5", "ndvi": "0.155", "albedo": "0.42"}
    assert g.passes_earth_filter(devon) and g.is_cold_desert(devon) and not g.is_hyper_arid(devon)
    assert not g.passes_earth_filter({**devon, "precipitation_mm_yr": "250"})
    assert not g.passes_earth_filter({**devon, "air_temp_mean_K": "273.15"})
    assert not g.passes_earth_filter({**devon, "albedo": "0.78"})  # ice sheet with a rock type underneath
    assert not g.passes_earth_filter({**devon, "rock_group": "ice"})
    irrigated = {"is_land": "1.0", "rock_group": "sedimentary", "aridity_index": "0.18", "ndvi": "0.37",
                 "air_temp_mean_K": "284.2", "precipitation_mm_yr": "200"}
    assert not g.passes_earth_filter(irrigated)  # desert climate on paper, green crops
    assert g.passes_earth_filter({**irrigated, "ndvi": "0.199"}) and g.passes_earth_filter({**irrigated, "ndvi": ""})
    # aridity unknown but temperature known: only the cold branch can make it dry
    assert not g.passes_earth_filter({**irrigated, "aridity_index": "", "ndvi": "0.1"})


def test_cells_missing_from_a_projection_lose_only_climate_values():
    base = {(1.5, 1.5): {"elevation_m": "10", "surface_temp_swing_K": "20", "surface_temp_min_K": "250",
                         "precipitation_mm_yr": "90"}}
    out = g.project(base, {}, {})
    assert out[(1.5, 1.5)]["elevation_m"] == "10"
    assert out[(1.5, 1.5)]["surface_temp_swing_K"] == "" and out[(1.5, 1.5)]["aridity_index"] == ""


def test_projection_needs_a_reference(grid):
    with pytest.raises(ValueError, match="reference year"):
        g.build(grid, "earth_1deg_2050.csv", base_file="earth_1deg.csv")


def test_full_yearly_files_keep_the_old_behaviour(tmp_path):
    _write(tmp_path / "earth_1deg.csv", _earth_rows())
    _write(tmp_path / "mars_1deg.csv", _mars_rows())
    _write(tmp_path / "earth_1deg_2050.csv", _earth_rows(swing_shift=30))  # complete file, not a projection
    d = es.load_grid(str(tmp_path), "earth_1deg_2050.csv")
    assert not d["has_aridity"] and g.PROJECTION_NOTE not in d["limitations"]


def test_year_slider_runs_on_projections(grid):
    out = es.run_preset_over_years("thermal_environment", data_dir=grid, calibrate=False, cache_file=None)
    assert out["years"] == [2020, 2050]


def test_export_carries_aridity_only_when_present(grid, tmp_path):
    m = we.export(grid, tmp_path / "web", calibrate=False)
    assert m["years"] == ["now", 2020, 2050] and m["dry_land"]["has_aridity"]
    assert m["dry_land"]["max_aridity"] == 0.2 and m["dry_land"]["hyper_arid_below"] == 0.05
    earth = json.loads((tmp_path / "web" / "earth.json").read_text(encoding="utf-8"))
    year = json.loads((tmp_path / "web" / "earth_2050.json").read_text(encoding="utf-8"))
    extra = ["aridity_index", "cold_desert"]
    assert earth["columns"][-2:] == extra and year["columns"] == ["id"] + we.YEAR_COLUMNS + extra
    assert m["dry_land"]["max_ndvi"] == 0.2 and m["dry_land"]["cold_desert"]["max_precip_mm_yr"] == 250


RUNNER = r"""
const fs = require('fs'), path = require('path');
const S = require(process.argv[2]);
const dir = process.argv[3], job = JSON.parse(process.argv[4]);
const read = f => JSON.parse(fs.readFileSync(path.join(dir, f)));
const m = read('manifest.json'), base = read(m.files.earth.now), mars = read(m.files.mars);
const earth = job.year === 'now' ? base : S.earthForYear(base, read(m.files.earth[job.year]));
const t = S.marsCell(m, mars, -5.4, 137.8);
const p = m.presets.find(x => x.id === 'thermal_environment');
const r = S.scoreCells(m, earth, S.similarities(m, earth, t.values), {categoryWeights: p.category_weights,
  featureWeights: p.feature_weights, requirements: p.requirements, requiredFeatures: p.required_features,
  hyperArid: job.hyper});
process.stdout.write(JSON.stringify(r.ranked.map(x => [x.id, x.score])));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
@pytest.mark.parametrize("year,earth_file", [("now", None), ("2050", "earth_1deg_2050.csv")])
@pytest.mark.parametrize("hyper", [False, True])
def test_browser_matches_engine_per_year_and_filter(grid, tmp_path, year, earth_file, hyper):
    out = tmp_path / "web"
    we.export(grid, out, calibrate=False)
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    js = json.loads(subprocess.run([NODE, str(runner), str(SCORING), str(out), json.dumps({"year": year, "hyper": hyper})],
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    d = es.load_grid(str(grid), earth_file)
    keep = g.is_hyper_arid if hyper else g.passes_earth_filter
    sites = [g.cell_site("earth", d["earth"], k, d["earth_ati"], spec=d["earth_spec"], support=d["support"])
             for k, r in d["earth"].items() if keep(r)]
    preset = next(p for p in es.PRESETS if p["id"] == "thermal_environment")
    profile, _ = es.preset_profile("thermal_environment", grid, calibrate=False, cache_file=None)
    py = rank(es._target(preset, d), sites, profile, g.feature_definitions())
    assert [i for i, _ in js] == py.order() and len(js) > 0
    for (_, s_js), e in zip(js, py.ranked):
        assert s_js == pytest.approx(e.result.score_observed, abs=1e-12)
