"""Any grid resolution, on SYNTHETIC grids (no real data needed).

The 1-degree grid must keep exactly its ids and cells; a 50 km grid
(Earth 0.45 deg, Mars 0.84 deg) must load, rank and export with the same
rules, and the browser must still match the engine bit for bit.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from analogue_engine import rank
from backend import engine_service as es
from backend import grid_data as g
from backend import web_export as we
from backend.analog_presets import CELLS, EARTH
from backend.tests.test_engine_service import _write

ROOT = Path(__file__).resolve().parents[2]
SCORING = ROOT / "web" / "app" / "js" / "scoring.js"
NODE = shutil.which("node")

# The cells the 1-degree app used before targets became points: must not move.
ONE_DEGREE_CELLS = {
    "Gale Crater (Curiosity)": (-5.5, 137.5), "Jezero Crater (Perseverance)": (18.5, 77.5),
    "Arcadia Planitia (approx.)": (46.5, -167.5), "Atacama": (-24.5, -69.5), "Arizaro": (-24.5, -67.5),
    "Kara-Kul": (39.5, 73.5), "Dry Valleys": (-77.5, 161.5), "Devon Island (Haughton)": (75.5, -89.5),
}


def _global(planet: str, step: float) -> g.GridSpec:
    """Lattice of a grid that starts at the south pole and the antimeridian (as the Data team's grids do)."""
    n_lat, n_lon = int(180 / step + 1e-9), int(360 / step + 1e-9)  # not //: 180 // 0.45 == 399.0 in floats
    lat0, lon0 = round(-90 + step / 2, 6), round(-180 + step / 2, 6)
    return g.GridSpec(planet, step, step, lat0, lon0, n_lat, n_lon, g._decimals(step, lat0, lon0))


def _block(spec: g.GridSpec, lat: float, lon: float, half: int):
    i0, j0 = spec.index(lat, lon)
    return [spec.centre(i, j) for i in range(i0 - half, i0 + half + 1) for j in range(j0 - half, j0 + half + 1)]


def _earth_rows_50km(swing_shift: float = 0.0):
    rows = []
    for k, (lat, lon) in enumerate(_block(_global("earth", 0.45), 22.0, 12.0, 3)):  # 7 x 7 cells
        rows.append({
            "lat": lat, "lon": lon, "is_land": "1.0", "elevation_m": 300 + 150 * (k % 5) + 7 * (k % 3),
            "surface_temp_swing_K": 10 + k * 0.7 + (swing_shift if k == 24 else 0), "surface_temp_min_K": 250 - k,
            "apparent_thermal_inertia": 0.02 + 0.003 * k, "albedo": 0.15 + 0.01 * (k % 10),
            "rock_group": ["sedimentary", "volcanic", "ancient_crust"][k % 3],
            "crater_count": 1 if k % 7 == 0 else 0, "ground_ice_flag": 1 if k % 4 == 0 else 0,
            "precipitation_mm_yr": 900 if k == 5 else 100, "ndvi": 0.1,
        })
    return rows


def _mars_rows_50km():
    rows, spec = [], _global("mars", 0.84)
    for lat, lon in CELLS.values():
        for k, (la, lo) in enumerate(_block(spec, lat, lon, 1)):
            rows.append({
                "lat": la, "lon": lo, "is_land": "1.0", "elevation_m": -2500 + 400 * (k // 3) + 30 * k,
                "surface_temp_swing_K": 80, "surface_temp_min_K": 185, "apparent_thermal_inertia": 0.01 + 0.001 * k,
                "albedo": 0.2, "rock_group": "sedimentary", "crater_count": 5, "ground_ice_flag": 0,
                "precipitation_mm_yr": "", "ndvi": "",
            })
    return rows


@pytest.fixture
def grid50(tmp_path):
    d = tmp_path / "grid_50km"
    d.mkdir()
    _write(d / "earth_50km.csv", _earth_rows_50km())
    _write(d / "mars_50km.csv", _mars_rows_50km())
    return d


# --------------------------------------------------------------------------- 1 degree unchanged


def test_one_degree_ids_and_target_cells_are_unchanged():
    spec = g.GridSpec.one_degree("earth")
    assert spec.cell_id(83.5, -77.5) == "earth_+83.5_-077.5" == g.cell_id("earth", 83.5, -77.5)
    for name, pt in {**CELLS, **EARTH}.items():
        assert spec.containing(*pt) == ONE_DEGREE_CELLS[name], name


def test_one_degree_grid_is_detected_with_the_original_support(tmp_path):
    from backend.tests.test_engine_service import _earth_rows, _mars_rows
    _write(tmp_path / "earth_1deg.csv", _earth_rows())
    _write(tmp_path / "mars_1deg.csv", _mars_rows())
    d = g.build(tmp_path)
    assert (d["earth_spec"].lat_step, d["earth_spec"].decimals, d["support"]) == (1.0, 1, g.SUPPORT)
    assert d["limitations"] == g.COMMON_LIMITATIONS


# --------------------------------------------------------------------------- grid detection


def test_50km_grids_are_detected_and_comparable(grid50):
    d = g.build(grid50, "earth_50km.csv", "mars_50km.csv")
    e, m = d["earth_spec"], d["mars_spec"]
    assert (e.lat_step, e.lon_step, e.decimals) == (0.45, 0.45, 3)
    assert (m.lat_step, m.lon_step, m.decimals) == (0.84, 0.84, 2)
    assert e.cell_km == pytest.approx(50.0, abs=0.1) and m.cell_km == pytest.approx(49.7, abs=0.1)
    assert d["support"] == "grid_50km_v1"
    assert all(s["measurements"][0]["spatial_support"] == "grid_50km_v1" for s in d["earth_sites"])
    assert "50 km on Earth (0.45 deg)" in d["limitations"][-1] and "Mars (0.84 deg)" in d["limitations"][-1]
    assert d["earth_sites"][0]["id"].count(".") == 2 and len(d["earth_sites"][0]["id"].split("_")[1]) == 7  # +21.375


def test_cells_of_different_physical_size_are_refused(tmp_path):
    from backend.tests.test_engine_service import _earth_rows
    _write(tmp_path / "earth_1deg.csv", _earth_rows())  # 1 deg = 111 km
    _write(tmp_path / "mars_50km.csv", _mars_rows_50km())  # 0.84 deg = 50 km
    with pytest.raises(ValueError, match="not comparable"):
        g.build(tmp_path, "earth_1deg.csv", "mars_50km.csv")


def test_irregular_grid_is_refused():
    grid = {(0.0, 0.0): {}, (0.45, 0.0): {}, (1.0, 0.45): {}, (0.0, 0.45): {}}
    with pytest.raises(ValueError, match="not regular"):
        g.grid_spec("earth", grid)


# --------------------------------------------------------------------------- cells and neighbours


def test_point_to_cell_edges_wrap_and_outside():
    e = _global("earth", 0.45)
    assert e.containing(-5.5, 137.8) == (-5.625, 137.925)
    assert e.containing(-5.4, 137.8) == (-5.175, 137.925)  # exactly on an edge: the northern cell, as at 1 deg
    assert e.containing(90.0, 0.0)[0] == 89.775  # the pole belongs to the top cell
    assert e.containing(10.0, 180.0) == e.containing(10.0, -180.0)  # antimeridian wraps
    mars_partial = g.GridSpec("mars", 1.0, 1.0, -61.5, -179.5, 152, 360, 1)  # like the real Mars grid
    assert mars_partial.containing(-80.0, 10.0) is None  # outside: never snapped to the edge cell
    assert mars_partial.containing(-61.9, 10.0) == (-61.5, 10.5)


def test_relief_uses_the_grid_neighbours(grid50):
    d = g.build(grid50, "earth_50km.csv", "mars_50km.csv")
    spec, grid = d["earth_spec"], d["earth"]
    key = spec.containing(22.0, 12.0)
    ring = [grid[spec.neighbour(*key, di, dj)] for di in (-1, 0, 1) for dj in (-1, 0, 1)]
    elev = [float(r["elevation_m"]) for r in ring]
    site = g.cell_site("earth", grid, key, d["earth_ati"], spec=spec, support=d["support"])
    relief = next(m["value"] for m in site["measurements"] if m["feature_id"] == "regional_relief_m")
    assert relief == max(elev) - min(elev) > 0


# --------------------------------------------------------------------------- service and export at 50 km


def test_run_preset_on_a_50km_grid(grid50):
    out = es.run_preset("rover_navigation", data_dir=grid50, top_n=5, calibrate=False, cache_file=None)
    d = es.load_grid(str(grid50))
    gale = d["mars_spec"].containing(*CELLS["Gale Crater (Curiosity)"])
    assert (out["target"]["lat"], out["target"]["lon"]) == gale and out["target"]["point"] == {"lat": -5.4, "lon": 137.8}
    assert out["profile_used"]["target_id"] == d["mars_spec"].cell_id(*gale) == "mars_-05.58_+137.94"
    assert out["grid"]["spatial_support"] == "grid_50km_v1" and out["heatmap"]["cell_size_deg"] == 0.45
    # 49 cells, one wet (filtered out); the 4 corners have under 5 cells for the relief, so they are partial
    assert out["counts"]["ranked"] == len(out["heatmap"]["rows"]) == 44 and out["counts"]["partial"] == 4
    assert any("50 km" in x for x in out["declared_limitations"])


def test_yearly_files_follow_the_grid_name(grid50):
    _write(grid50 / "earth_50km_2050.csv", _earth_rows_50km(swing_shift=30))
    assert es.yearly_files(grid50) == [(2050, "earth_50km_2050.csv")]
    out = es.run_preset_over_years("thermal_environment", data_dir=grid50, calibrate=False, cache_file=None)
    assert out["years"] == [2050] or "message" in out  # one year only: slider needs two


def test_grid_files_need_one_grid_per_folder(grid50):
    _write(grid50 / "earth_other.csv", _earth_rows_50km())
    with pytest.raises(es.DataNotFound, match="Several earth grids"):
        es.grid_files(grid50)


def test_export_compresses_only_over_budget(grid50, tmp_path, monkeypatch):
    plain = we.export(grid50, tmp_path / "plain", calibrate=False)
    assert plain["compression"] == "none" and plain["files"]["mars"] == "mars.json"
    monkeypatch.setattr(we, "SIZE_BUDGET", 0)
    _write(grid50 / "earth_50km_2050.csv", _earth_rows_50km(swing_shift=30))
    m = we.export(grid50, tmp_path / "gz", calibrate=False)
    assert m["compression"] == "gzip" and m["files"]["earth"] == {"now": "earth.json.gz", "2050": "earth_2050.json.gz"}
    year = json.loads(gzip.decompress((tmp_path / "gz" / "earth_2050.json.gz").read_bytes()))
    assert year["base"] == "earth.json.gz"
    same = json.loads(gzip.decompress((tmp_path / "gz" / "earth.json.gz").read_bytes()))
    assert same == json.loads((tmp_path / "plain" / "earth.json").read_text(encoding="utf-8"))  # values unchanged
    assert m["grid"]["earth"]["lat_step"] == 0.45 and m["grid"]["mars"]["decimals"] == 2


RUNNER = r"""
const fs = require('fs'), path = require('path'), zlib = require('zlib');
const S = require(process.argv[2]);
const dir = process.argv[3], job = JSON.parse(process.argv[4]);
const read = f => { const b = fs.readFileSync(path.join(dir, f)); return JSON.parse(f.endsWith('.gz') ? zlib.gunzipSync(b) : b); };
const m = read('manifest.json'), earth = read(m.files.earth.now), mars = read(m.files.mars);
const out = {cells: job.points.map(p => { const c = S.marsCell(m, mars, p[0], p[1]); return c ? [c.lat, c.lon] : null; }),
             label: S.cellLabel(m, 'earth')};
const t = S.marsCell(m, mars, job.points[0][0], job.points[0][1]);
const sims = S.similarities(m, earth, t.values);
out.sims = sims.by_id;
out.ranked = {};
for (const p of m.presets) {
  const tg = m.targets.find(x => x.key === p.target);
  const r = S.scoreCells(m, earth, S.similarities(m, earth, tg.values), {categoryWeights: p.category_weights,
    featureWeights: p.feature_weights, requirements: p.requirements, requiredFeatures: p.required_features});
  out.ranked[p.id] = r.ranked.map(x => [x.id, x.score]);
}
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_browser_matches_engine_on_a_compressed_50km_export(grid50, tmp_path):
    out = tmp_path / "web"
    we.export(grid50, out, calibrate=False, compress=True)
    d = es.load_grid(str(grid50))
    spec = d["mars_spec"]
    points = [(-5.4, 137.8), (-5.0, 138.3), (18.38, 77.58), (46.9, -167.1), (-80.0, 10.0)]
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    js = json.loads(subprocess.run([NODE, str(runner), str(SCORING), str(out), json.dumps({"points": points})],
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert js["label"] == "0.45° cell (≈50 km)"
    for p, cell in zip(points, js["cells"]):  # same point -> cell rule as Python
        key = spec.containing(*p)
        assert cell == (list(key) if key in d["mars"] else None), p
    target = g.cell_site("mars", d["mars"], tuple(js["cells"][0]), d["mars_ati"], spec=spec, support=d["support"])
    sites = [g.cell_site("earth", d["earth"], k, d["earth_ati"], spec=d["earth_spec"], support=d["support"])
             for k in d["earth"]]
    profile = g.make_profile("all", target["id"], {c: 1 for c in set(g.DIMENSION_OF.values())},
                             {f: 1 for f in we.FEATURES}, description="all features")
    res = rank(target, sites, profile, g.feature_definitions())
    for r in [e.result for e in res.ranked] + list(res.partial) + list(res.excluded):
        by = {c.feature_id: c.similarity for c in r.components}
        assert js["sims"][r.candidate_id] == [by[f] for f in we.FEATURES]  # bit for bit
    for preset in es.PRESETS:
        prof, _ = es.preset_profile(preset["id"], grid50, calibrate=False, cache_file=None)
        py = rank(es._target(preset, d), d["earth_sites"], prof, g.feature_definitions())
        assert [i for i, _ in js["ranked"][preset["id"]]] == py.order(), preset["id"]
