"""Year slider between projections (web/app/js/scoring.js blendEarth), on a SYNTHETIC grid.

The Data team ships projections every 20 years; the app lets you pick any
year and interpolates the climate columns linearly between the two nearest
projections. At a projected year it must give exactly that projection.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from backend import web_export as we
from backend.tests.test_engine_service import _earth_rows, _mars_rows, _write

ROOT = Path(__file__).resolve().parents[2]
SCORING = ROOT / "web" / "app" / "js" / "scoring.js"
NODE = shutil.which("node")

RUNNER = r"""
const fs = require('fs'), path = require('path');
const S = require(process.argv[2]);
const dir = process.argv[3];
const read = f => JSON.parse(fs.readFileSync(path.join(dir, f)));
const m = read('manifest.json'), base = read(m.files.earth.now);
const sc = m.scenarios.find(s => s.id === 'ssp585');
const a = S.earthForYear(base, read(sc.files['2050'])), b = S.earthForYear(base, read(sc.files['2090']));
const col = c => a.columns.indexOf(c);
const pick = (t, c) => t.rows.map(r => r[col(c)]);
const mid = S.blendEarth(m, a, b, 0.5), q = S.blendEarth(m, a, b, 0.25);
process.stdout.write(JSON.stringify({
  scenarios: m.scenarios.map(s => [s.id, s.short, s.code, s.years]),
  same0: S.blendEarth(m, a, b, 0) === a, same1: S.blendEarth(m, a, b, 1) === b,
  a: pick(a, 'air_temp_swing_K'), b: pick(b, 'air_temp_swing_K'), mid: pick(mid, 'air_temp_swing_K'),
  q: pick(q, 'air_temp_swing_K'), slopeA: pick(a, 'slope_deg'), slopeMid: pick(mid, 'slope_deg')}));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_blend_between_projections(tmp_path):
    data = tmp_path / "grid"
    data.mkdir()
    _write(data / "earth_1deg.csv", _earth_rows())
    _write(data / "mars_1deg.csv", _mars_rows())
    for scen, shift in (("ssp245", 4), ("ssp585", 12)):
        (data / scen).mkdir()
        _write(data / scen / "earth_1deg_2050.csv", _earth_rows(swing_shift=shift / 2))
        _write(data / scen / "earth_1deg_2090.csv", _earth_rows(swing_shift=shift))
    out = tmp_path / "web"
    m = we.export(data, out, calibrate=False)
    assert [s["id"] for s in m["scenarios"]] == ["ssp245", "ssp585"]  # both scenarios in one export
    runner = tmp_path / "run.js"
    runner.write_text(RUNNER, encoding="utf-8")
    js = json.loads(subprocess.run([NODE, str(runner), str(SCORING), str(out)],
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout)
    assert js["scenarios"][1] == ["ssp585", "High emissions", "SSP5-8.5", [2050, 2090]]
    assert js["same0"] and js["same1"]  # projected years are returned untouched
    for a, b, mid, q in zip(js["a"], js["b"], js["mid"], js["q"]):
        assert mid == pytest.approx((a + b) / 2) and q == pytest.approx(a + (b - a) / 4)
    assert js["a"] != js["b"]  # the synthetic cell does change
    assert js["slopeMid"] == js["slopeA"]  # terrain is not a climate column
