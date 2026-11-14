"""The browser (web/app/js/scoring.js) must reproduce the engine exactly.

Exports a small synthetic grid, then for each preset and for arbitrary Mars
cells: computes similarities and rankings with the Python engine, does the
same with scoring.js under Node.js, and compares them. Skipped without Node.
"""

from __future__ import annotations

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

RUNNER = r"""
const fs = require('fs'), path = require('path');
const S = require(process.argv[2]);
const dir = process.argv[3], job = JSON.parse(process.argv[4]);
const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json')));
const earth = JSON.parse(fs.readFileSync(path.join(dir, m.files.earth.now)));
const mars = JSON.parse(fs.readFileSync(path.join(dir, m.files.mars)));
const t = S.marsCell(m, mars, job.lat, job.lon);
const sims = S.similarities(m, earth, t.values);
const out = {cell: [t.lat, t.lon], sims: sims.by_id};
if (job.preset) {
  const p = m.presets.find(x => x.id === job.preset);
  const r = S.scoreCells(m, earth, sims, {categoryWeights: p.category_weights, featureWeights: p.feature_weights,
    requirements: p.requirements, requiredFeatures: p.required_features, onlyDryBare: job.onlyDryBare});
  out.ranked = r.ranked.map(x => [x.id, x.score]); out.partial = r.partial.length; out.excluded = r.excluded.length;
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.fixture
def exported(tmp_path):
    data = tmp_path / "grid"
    data.mkdir()
    rows = _earth_rows()
    rows[3]["precipitation_mm_yr"] = 900  # one wet cell: outside the dry/bare pre-filter
    _write(data / "earth_1deg.csv", rows)
    _write(data / "mars_1deg.csv", _mars_rows())
    out = tmp_path / "web"
    we.export(data, out, calibrate=False)
    return data, out


def _node(tmp_path, out, job):
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    res = subprocess.run([NODE, str(runner), str(SCORING), str(out), json.dumps(job)],
                         capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def _all_land_sites(data_dir: Path):
    d = es.load_grid(str(data_dir))
    return d, [g.cell_site("earth", d["earth"], k, d["earth_ati"]) for k, r in d["earth"].items() if r["is_land"] == "1.0"]


def test_manifest_and_files(exported):
    _, out = exported
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert [t["key"] for t in m["targets"]] == ["gale", "jezero", "arcadia"]
    assert len(m["presets"]) == 4 and m["years"] == ["now"]
    earth = json.loads((out / m["files"]["earth"]["now"]).read_text(encoding="utf-8"))
    assert len(earth["rows"]) == 25 and sum(1 for r in earth["rows"] if r[-1]) == 24  # all land, one not dry/bare
    assert all(f.get("tau") for f in m["features"] if f["comparator"] == "clipped_linear_v1")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
@pytest.mark.parametrize("preset_id", ["rover_navigation", "sample_science", "thermal_environment", "ice_prospecting"])
def test_js_ranking_matches_engine(exported, tmp_path, preset_id):
    data, out = exported
    preset = next(p for p in es.PRESETS if p["id"] == preset_id)
    lat, lon = es.CELLS[preset["target"]]
    js = _node(tmp_path, out, {"lat": lat, "lon": lon, "preset": preset_id, "onlyDryBare": True})

    built = es.load_grid(str(data))
    profile, _ = es.preset_profile(preset_id, data, calibrate=False, cache_file=None)
    py = rank(es._target(preset, built), built["earth_sites"], profile, g.feature_definitions())
    assert [i for i, _ in js["ranked"]] == py.order()
    for (_, s_js), e in zip(js["ranked"], py.ranked):
        # the engine sums with math.fsum (exactly rounded); JS sums naively: equal to ~1e-16
        assert s_js == pytest.approx(e.result.score_observed, abs=1e-12)
    assert js["partial"] == len(py.partial) and js["excluded"] == len(py.excluded)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
@pytest.mark.parametrize("point", [(-5.3, 137.9), (18.9, 77.2), (46.2, -167.9)])
def test_js_similarities_for_any_mars_point_match_engine(exported, tmp_path, point):
    """Any clicked point snaps to its 1° cell; every Earth land cell gets the engine's similarities."""
    data, out = exported
    js = _node(tmp_path, out, {"lat": point[0], "lon": point[1]})
    d, sites = _all_land_sites(data)
    target = g.cell_site("mars", d["mars"], tuple(js["cell"]), d["mars_ati"])
    profile = g.make_profile("all", target["id"], {c: 1 for c in set(g.DIMENSION_OF.values())},
                             {f: 1 for f in we.FEATURES}, description="all features")
    res = rank(target, sites, profile, g.feature_definitions())
    for r in [e.result for e in res.ranked] + list(res.partial) + list(res.excluded):
        by = {c.feature_id: c.similarity for c in r.components}
        assert js["sims"][r.candidate_id] == [by[f] for f in we.FEATURES]  # bit for bit


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_edge_mars_cell_reports_missing_target_values(tmp_path):
    """A target cell with an empty value gets no similarity for it in the browser (never 0).

    Terrain now comes from the grid's own columns (slope_deg, roughness_m, relief_m), so an edge
    cell is comparable; an empty slope value at the target must still give null.
    """
    data = tmp_path / "grid"
    data.mkdir()
    _write(data / "earth_1deg.csv", _earth_rows())
    mars = _mars_rows()
    for r in mars:
        if (r["lat"], r["lon"]) == (-4.5, 136.5):
            r["slope_deg"] = ""
    _write(data / "mars_1deg.csv", mars)
    out = tmp_path / "web"
    we.export(data, out, calibrate=False)
    js = _node(tmp_path, out, {"lat": -4.6, "lon": 136.6})
    assert js["cell"] == [-4.5, 136.5]
    i = we.FEATURES.index("slope_deg")
    assert all(v[i] is None for v in js["sims"].values())
    assert all(v[we.FEATURES.index("roughness_m")] is not None for v in js["sims"].values())


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_dry_bare_filter_is_a_switch(exported, tmp_path):
    _, out = exported
    on = _node(tmp_path, out, {"lat": -5.5, "lon": 137.5, "preset": "rover_navigation", "onlyDryBare": True})
    off = _node(tmp_path, out, {"lat": -5.5, "lon": 137.5, "preset": "rover_navigation", "onlyDryBare": False})
    assert len(off["ranked"]) + off["partial"] == len(on["ranked"]) + on["partial"] + 1


YEAR_RUNNER = r"""
const fs = require('fs'), path = require('path');
const S = require(process.argv[2]);
const dir = process.argv[3], year = process.argv[4];
const m = JSON.parse(fs.readFileSync(path.join(dir, 'manifest.json')));
const base = JSON.parse(fs.readFileSync(path.join(dir, m.files.earth.now)));
const yt = JSON.parse(fs.readFileSync(path.join(dir, m.files.earth[year])));
const earth = S.earthForYear(base, yt);
const mars = JSON.parse(fs.readFileSync(path.join(dir, m.files.mars)));
const t = S.marsCell(m, mars, -5.5, 137.5);
const p = m.presets.find(x => x.id === 'thermal_environment');
const r = S.scoreCells(m, earth, S.similarities(m, earth, t.values), {categoryWeights: p.category_weights,
  featureWeights: p.feature_weights, requirements: p.requirements, requiredFeatures: p.required_features});
process.stdout.write(JSON.stringify({ranked: r.ranked.map(x => [x.id, x.score]), cols: yt.columns}));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_yearly_file_holds_only_climate_columns_and_matches_engine(tmp_path):
    data = tmp_path / "grid"
    data.mkdir()
    _write(data / "earth_1deg.csv", _earth_rows())
    _write(data / "earth_1deg_2050.csv", _earth_rows(swing_shift=30))  # synthetic future: one cell changes
    _write(data / "mars_1deg.csv", _mars_rows())
    out = tmp_path / "web"
    m = we.export(data, out, calibrate=False)
    assert m["years"] == ["now", 2050] and m["files"]["earth"]["2050"] == "earth_2050.json"
    runner = tmp_path / "year.js"
    runner.write_text(YEAR_RUNNER, encoding="utf-8")
    js = json.loads(subprocess.run([NODE, str(runner), str(SCORING), str(out), "2050"],
                                   capture_output=True, text=True, check=True).stdout)
    assert js["cols"] == ["id"] + we.YEAR_COLUMNS
    built = es.load_grid(str(data), "earth_1deg_2050.csv")
    preset = next(p for p in es.PRESETS if p["id"] == "thermal_environment")
    profile, _ = es.preset_profile("thermal_environment", data, calibrate=False, cache_file=None)
    py = rank(es._target(preset, built), built["earth_sites"], profile, g.feature_definitions())
    assert [i for i, _ in js["ranked"]] == py.order()
