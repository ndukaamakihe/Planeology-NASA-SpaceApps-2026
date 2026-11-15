"""Map layers for the Analog Atlas page (equirectangular PNGs, north up, -180..180).

usage: python -I render_layers.py <out dir> [future_ranks.json of the 1-degree engine run]

  score_<preset>.png   11 km similarity to the mission's Mars target, dry land only (0.1 deg, 3600x1800)
  score1_<preset>.png  the same at 1 degree from the app's engine run (360x180), for the resolution comparison
  change_<scen>_<year>.png  dry land gained / lost vs today (0.1 deg)
  land.png             land mask
Colours: a sequential ramp for scores (scaled per preset between its 50th and 99.99th percentile
among dry cells); gain/loss in two hues.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import planalogy_hires as H  # noqa: E402
from hires_common import SHAPE  # noqa: E402

OUTDIR = Path(sys.argv[1])
OUTDIR.mkdir(parents=True, exist_ok=True)
S = H.static()
idx = np.load(H.TAB / "index2d.npy")
land = idx >= 0
ny, nx = SHAPE["earth"]

# sequential ramp (dark ochre -> amber -> pale), RGBA; transparency where no value
STOPS = np.array([[0.00, 84, 38, 24], [0.35, 158, 66, 30], [0.65, 222, 128, 44], [0.85, 245, 190, 92], [1.00, 255, 244, 200]])


def ramp(t):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,))
    for k in range(3):
        out[..., k] = np.interp(t, STOPS[:, 0], STOPS[:, k + 1])
    return out


def to2d(v, fill=np.nan):
    g = np.full((ny, nx), fill, np.float32)
    g[land] = v[idx[land]]
    return g


def save_rgba(arr, name):
    Image.fromarray(arr.astype(np.uint8), "RGBA").save(OUTDIR / name, optimize=True)


meta = {"presets": {}, "changes": {}}
lm = np.zeros((ny, nx, 4), np.uint8)
lm[land] = (128, 128, 128, 255)
save_rgba(lm, "land.png")
for pid in ("rover_navigation", "sample_science", "thermal_environment", "ice_prospecting"):
    run = H.Run(pid)
    Y = run.year("now")
    sc = np.where(Y["pool"], Y["score"], np.nan)
    lo, hi = np.nanpercentile(sc, 50), np.nanpercentile(sc, 99.99)
    g = to2d(sc)
    rgba = np.zeros((ny, nx, 4))
    ok = np.isfinite(g)
    rgba[ok, :3] = ramp((g[ok] - lo) / (hi - lo))
    rgba[ok, 3] = 255
    save_rgba(rgba, f"score_{pid}.png")
    meta["presets"][pid] = {"lo": round(float(lo) * 100, 1), "hi": round(float(hi) * 100, 1), "dry_cells": Y["n"],
                            "target": run.label, "mars_cell": run.tv["_cell"]}
    # 1-degree engine result (app grid) for comparison
    if len(sys.argv) < 3:  # optional: 1-degree engine ranks (future_ranks.json) for the comparison layer
        print(pid, meta["presets"][pid], flush=True)
        continue
    D = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    R = D["results"][pid]["ranks"]["now"]
    g1 = np.full((180, 360), np.nan)
    for cid, (rk, s) in R.items():
        _, la, lo_ = cid.split("_")
        g1[int(round(89.5 - float(la))), int(round(float(lo_) + 179.5))] = s / 100
    l1, h1 = np.nanpercentile(g1, 50), np.nanpercentile(g1, 99.9)
    r1 = np.zeros((180, 360, 4))
    ok = np.isfinite(g1)
    r1[ok, :3] = ramp((g1[ok] - l1) / (h1 - l1))
    r1[ok, 3] = 255
    save_rgba(r1, f"score1_{pid}.png")
    meta["presets"][pid]["dry_cells_1deg"] = int(ok.sum())
    del D
    print(pid, meta["presets"][pid], flush=True)

pool_now, _ = H.dry(H.climate("now"))
for key in ("ssp245_2050", "ssp585_2050", "ssp245_2090", "ssp585_2090"):
    pool, _ = H.dry(H.climate(key))
    gain, loss = pool & ~pool_now, pool_now & ~pool
    g = np.zeros((ny, nx, 4), np.uint8)
    G2, L2 = to2d(gain.astype(np.float32), 0) > 0, to2d(loss.astype(np.float32), 0) > 0
    g[G2] = (46, 160, 140, 255)
    g[L2] = (214, 70, 92, 255)
    save_rgba(g, f"change_{key}.png")
    meta["changes"][key] = {"gain": int(gain.sum()), "loss": int(loss.sum()), "dry": int(pool.sum())}
    print(key, meta["changes"][key], flush=True)
meta["dry_now"] = int(pool_now.sum())
(OUTDIR / "layers.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print("done")
