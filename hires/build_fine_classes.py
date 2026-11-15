"""Rock type, ground ice, impact craters and thermal inertia at 11 km (replacing the 1-degree versions).

Earth (0.1 deg):
  rock group + mineral proxy  GLiM vector map (1.2 M polygons, Eckert IV) rasterised at 0.02 deg, majority class per
                              cell; GLiM class -> rock group / mineral groups with the Data team's own mapping
                              (read from data/grid_1deg/earth_1deg.csv, so the classes mean the same as before).
  ground ice                  Obu et al. 2019 permafrost probability (1 km, EPSG:3995) averaged over 5x5 points per
                              cell; ice = probability >= 0.5 or GLiM glacier class (the Data team's rule). The map
                              covers the Northern Hemisphere only: south of the equator the 1-degree flag is kept.
Mars (0.1875 deg):
  rock group                  SIM 3292 geologic units rasterised at 0.0375 deg, majority unit per cell, unit -> group
                              with the Data team's mapping (mars_1deg.csv); impact units (AHi) take the 1-degree
                              group, as in the Data team's rule.
  ground ice                  Odyssey GRS H2O >= 10 wt% (1-degree, unchanged) or a polar/ice unit in the cell.
  inside an impact crater     Robbins & Hynek 2012 (384,343 craters >= 1 km): cell centre inside the rim, radius at
                              least half a cell (same rule as Earth's impact structures).
  thermal inertia             TES night thermal inertia 2007 (Putzig & Mellon, 20 ppd), cell mean; used for the
                              thermal-inertia percentile where it exists.

usage: python -I build_fine_classes.py      -> grid_11km/earth_classes.npz, mars_classes.npz
"""
import csv
import collections
import sys
import time
from pathlib import Path

import numpy as np
import pyogrio
import shapely
import tifffile
from PIL import Image, ImageDraw
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import GRID_1DEG, OUT, RAW, SHAPE, bin_mean, centres  # noqa: E402

t0 = time.time()
log = lambda *a: print(f"[{time.time() - t0:6.0f}s]", *a, flush=True)


def mapping(planet):
    grp, mins, h2o = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), {}
    with (GRID_1DEG / f"{planet}_1deg.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["rock_code"]:
                grp[r["rock_code"]][r["rock_group"]] += 1
                mins[r["rock_code"]][r["mineral_groups"]] += 1
    return ({c: g.most_common(1)[0][0] for c, g in grp.items()}, {c: m.most_common(1)[0][0] for c, m in mins.items()})


def rasterize(polys, codes, order, width, height, lon0, lat0, px):
    """Draw polygons (exterior rings, largest first so holes get the inner polygons) into a uint8 class image."""
    img = Image.new("L", (width, height), 0)
    dr = ImageDraw.Draw(img)
    for k in order:
        g = polys[k]
        for part in getattr(g, "geoms", [g]):
            xy = np.asarray(part.exterior.coords)
            if len(xy) < 3:
                continue
            col = (xy[:, 0] - lon0) / px
            row = (lat0 - xy[:, 1]) / px
            dr.polygon(np.column_stack([col, row]).ravel().tolist(), fill=int(codes[k]))
    return np.asarray(img)


def majority(img, f, n_classes):
    ny, nx = img.shape[0] // f, img.shape[1] // f
    blk = img[:ny * f, :nx * f].reshape(ny, f, nx, f)
    best, best_n = np.zeros((ny, nx), np.uint8), np.zeros((ny, nx), np.int16)
    for k in range(1, n_classes + 1):
        n = (blk == k).sum(axis=(1, 3))
        take = n > best_n
        best[take], best_n[take] = k, n[take]
    return best


# ------------------------------------------------------------------ Earth rock (GLiM)
e_group, e_min = mapping("earth")
gdb = next((RAW / "glim").glob("*.gdb"))
log("reading GLiM")
meta, idx, geom, fields = pyogrio.raw.read(gdb, columns=["xx"], return_fids=False)
codes_txt = fields[0]
classes = sorted(set(codes_txt) - {None, ""})
code_ix = {c: i + 1 for i, c in enumerate(classes)}
polys = shapely.from_wkb(geom)
log("projecting", len(polys), "polygons from Eckert IV")
tr = Transformer.from_crs(meta["crs"], "EPSG:4326", always_xy=True)
polys = shapely.transform(polys, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
areas = shapely.area(polys)
order = np.argsort(-areas)
codes = np.array([code_ix.get(c, 0) for c in codes_txt], np.uint8)
F = 5
log("rasterising GLiM")
img = rasterize(polys, codes, order, 3600 * F, 1800 * F, -180.0, 90.0, 0.1 / F)
cls = majority(img, F, len(classes))
del img, polys
rock = np.array([""] + [e_group.get(c, "") for c in classes], dtype="U16")[cls]
mins = np.array([""] + [e_min.get(c, "") for c in classes], dtype="U80")[cls]
glacier = cls == code_ix.get("ig", 255)
log("GLiM classes per cell", collections.Counter(rock.ravel().tolist()).most_common(8))

# ------------------------------------------------------------------ Earth ground ice (Obu 2019)
log("sampling Obu permafrost probability")
obu = tifffile.imread(next((RAW / "obu").glob("*NH.tif")), out="memmap")
x0, y0, opx = -10389109.8424841110, 9199572.4044017550, 926.6254331383
lat_c, lon_c = centres("earth")
to_ps = Transformer.from_crs("EPSG:4326", "EPSG:3995", always_xy=True)
prob = np.full(SHAPE["earth"], np.nan, np.float32)
offs = (np.arange(5) - 2) * 0.02
rows_n = np.nonzero(lat_c > 0)[0]
for r in rows_n:
    la = (lat_c[r] + offs)[:, None, None] * np.ones((1, 5, len(lon_c)))
    lo = (lon_c[None, :] + offs[:, None])[None, :, :] * np.ones((5, 1, 1))
    x, y = to_ps.transform(lo.ravel(), la.ravel())
    col = np.floor((x - x0) / opx).astype(np.int64)
    row = np.floor((y0 - y) / opx).astype(np.int64)
    ok = (row >= 0) & (row < obu.shape[0]) & (col >= 0) & (col < obu.shape[1])
    v = np.full(x.shape, np.nan, np.float32)
    v[ok] = obu[row[ok], col[ok]]
    v[(v < 0) | (v > 1)] = np.nan
    v = v.reshape(25, len(lon_c))
    with np.errstate(all="ignore"):
        prob[r] = np.where(np.isfinite(v).any(0), np.nan_to_num(v, nan=0).sum(0) / 25, np.nan)
earth_ice = np.where(lat_c[:, None] > 0, (np.nan_to_num(prob) >= 0.5) | glacier, -1).astype(np.int8)  # -1: keep 1 deg
log("permafrost cells (prob >= 0.5):", int((np.nan_to_num(prob) >= 0.5).sum()))
np.savez_compressed(OUT / "earth_classes.npz", rock_group=rock, mineral_groups=mins, glim_class=cls,
                    permafrost_prob=prob, ground_ice=earth_ice, classes=np.array(classes))

# ------------------------------------------------------------------ Mars rock (SIM 3292)
m_group, _ = mapping("mars")
shp = next((RAW / "sim3292").rglob("SIM3292_Global_Geology.shp"))
log("reading SIM 3292")
meta, _, geom, fields = pyogrio.raw.read(shp, columns=["Unit"], return_fids=False)
units = fields[0]
uclasses = sorted(set(units) - {None, ""})
u_ix = {u: i + 1 for i, u in enumerate(uclasses)}
mpolys = shapely.from_wkb(geom)
mpolys = shapely.transform(mpolys, lambda xy: np.column_stack([((xy[:, 0] + 180) % 360) - 180 if xy[:, 0].max() > 180 else xy[:, 0], xy[:, 1]]))
morder = np.argsort(-shapely.area(mpolys))
mcodes = np.array([u_ix.get(u, 0) for u in units], np.uint8)
MF = 5
mimg = rasterize(mpolys, mcodes, morder, 1920 * MF, 960 * MF, -180.0, 90.0, 0.1875 / MF)
mcls = majority(mimg, MF, len(uclasses))
del mimg
munit = np.array([""] + uclasses, dtype="U12")[mcls]
mrock = np.array([""] + [m_group.get(u, "") for u in uclasses], dtype="U16")[mcls]
log("SIM groups per cell", collections.Counter(mrock.ravel().tolist()).most_common(8))

# ------------------------------------------------------------------ Mars craters (Robbins)
log("Robbins craters")
cr = np.genfromtxt(RAW / "robbins" / "robbins_v1.csv", delimiter=",", names=True, dtype=None, encoding="utf-8")
clat, clon, cd = cr["lat"].astype(float), ((cr["lon_e"].astype(float) + 180) % 360) - 180, cr["diamkm"].astype(float)
mlat, mlon = centres("mars")
ny, nx = SHAPE["mars"]
inside = np.zeros((ny, nx), np.int8)
step, km_deg = 0.1875, np.pi * 3389.5 / 180
half_cell = step * km_deg / 2
r_i = np.clip(np.floor((90 - clat) / step).astype(int), 0, ny - 1)
c_i = np.floor((clon + 180) / step).astype(int) % nx
inside[r_i, c_i] = 1  # every crater marks the cell containing its centre (radius >= half a cell)
big = np.nonzero(cd / 2 > half_cell)[0]
for k in big:
    rad = cd[k] / 2
    dr_ = int(np.ceil(rad / km_deg / step)) + 1
    rows = np.arange(r_i[k] - dr_, r_i[k] + dr_ + 1)
    rows = rows[(rows >= 0) & (rows < ny)]
    coslat = max(np.cos(np.radians(clat[k])), 0.02)
    dc = min(int(np.ceil(rad / (km_deg * coslat) / step)) + 1, nx // 2)
    cols = np.arange(c_i[k] - dc, c_i[k] + dc + 1) % nx
    dy = (mlat[rows] - clat[k])[:, None] * km_deg
    dx = (((mlon[cols] - clon[k] + 180) % 360) - 180)[None, :] * km_deg * np.cos(np.radians(mlat[rows]))[:, None]
    inside[np.ix_(rows, cols)] |= (np.hypot(dx, dy) <= rad).astype(np.int8)
log("Mars cells inside a crater rim:", f"{inside.mean():.1%}", "craters", len(cd), "large", len(big))

# ------------------------------------------------------------------ Mars thermal inertia (TES)
ti = np.fromfile(RAW / "mars_ti" / "global_ti_night_2007.img", dtype=">i2").reshape(3600, 7200).astype(np.float32)
ti[ti <= 0] = np.nan
s, c = bin_mean("mars", ti, 90.0, -180.0, 0.05)
with np.errstate(all="ignore"):
    mti = (s / c).astype(np.float32)
log("Mars cells with TES thermal inertia:", f"{np.isfinite(mti).mean():.1%}")
np.savez_compressed(OUT / "mars_classes.npz", rock_group=mrock, unit=munit, inside_crater=inside, thermal_inertia=mti)
log("saved")
