"""Shared helpers for the ~11 km Planalogy grid.

Grids (cell centres, row 0 = north edge):
  Earth: 0.1 deg   -> 1800 x 3600 cells (~11.1 km at the equator)
  Mars : 0.1875 deg ->  960 x 1920 cells (~11.1 km at the equator)
Both planets have the same cell size in km, as the engine requires.
"""
from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np

# Layout: this folder next to hires_data/ (downloads and outputs, ~17 GB, not in git) and data/grid_1deg
# (the Data team's 1-degree grid with the ssp245/ssp585 projections). Override with environment variables.
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("PLANALOGY_HIRES_DATA", ROOT / "hires_data"))
RAW = DATA / "raw"
OUT = DATA / "grid_11km"
GRID_1DEG = Path(os.environ.get("PLANALOGY_GRID_1DEG", ROOT / "data" / "grid_1deg"))
OUT.mkdir(parents=True, exist_ok=True)

STEP = {"earth": 0.1, "mars": 0.1875}
SHAPE = {"earth": (1800, 3600), "mars": (960, 1920)}
RADIUS_M = {"earth": 6371007.0, "mars": 3396190.0}


def centres(planet: str) -> tuple[np.ndarray, np.ndarray]:
    s = STEP[planet]
    ny, nx = SHAPE[planet]
    lat = 90 - (np.arange(ny) + 0.5) * s
    lon = -180 + (np.arange(nx) + 0.5) * s
    return lat, lon


def cell_of(planet: str, lat, lon):
    """Row/col of the cell containing (lat, lon); arrays or scalars."""
    s = STEP[planet]
    ny, nx = SHAPE[planet]
    r = np.clip(np.floor((90 - np.asarray(lat)) / s).astype(int), 0, ny - 1)
    c = np.floor((((np.asarray(lon) + 180) % 360)) / s).astype(int) % nx
    return r, c


def bin_mean(planet: str, values: np.ndarray, lat0: float, lon0: float, px: float,
             row_offset: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Area-free mean of a lat/lon raster block into grid cells by pixel centre.

    values: 2-D block (rows from north); lat0/lon0: top-left corner of the FULL raster;
    px: pixel size in degrees; row_offset: index of the block's first row in the full raster.
    Returns (sum, count) arrays of the grid shape (NaNs ignored).
    """
    ny, nx = SHAPE[planet]
    s = STEP[planet]
    rows = np.arange(values.shape[0]) + row_offset
    plat = lat0 - (rows + 0.5) * px
    plon = lon0 + (np.arange(values.shape[1]) + 0.5) * px
    gr = np.clip(np.floor((90 - plat) / s).astype(np.int64), 0, ny - 1)
    gc = (np.floor(((plon + 180) % 360) / s).astype(np.int64)) % nx
    idx = (gr[:, None] * nx + gc[None, :]).ravel()
    v = values.ravel().astype(np.float64)
    ok = np.isfinite(v)
    tot = np.bincount(idx[ok], weights=v[ok], minlength=ny * nx).reshape(ny, nx)
    cnt = np.bincount(idx[ok], minlength=ny * nx).reshape(ny, nx)
    return tot, cnt


def load_1deg(planet: str) -> dict[str, np.ndarray]:
    """The Data team's 1-degree grid as 180 x 360 arrays (row 0 = 89.5 N); strings kept as object arrays."""
    import csv
    path = GRID_1DEG / f"{planet}_1deg.csv"
    with path.open(encoding="utf-8", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames
        out = {c: np.full((180, 360), np.nan) for c in cols}
        txt = {c: np.full((180, 360), "", dtype=object) for c in ("rock_group", "mineral_groups", "rock_code")}
        for r in rd:
            i = int(round(89.5 - float(r["lat"])))
            j = int(round(float(r["lon"]) + 179.5))
            for c in cols:
                if c in txt:
                    txt[c][i, j] = r[c]
                    continue
                v = r[c]
                try:
                    out[c][i, j] = float(v) if v not in ("", None) else np.nan
                except ValueError:
                    pass
    out.update(txt)
    return out


def parent_index(planet: str) -> tuple[np.ndarray, np.ndarray]:
    """1-degree parent row/col for every fine cell."""
    lat, lon = centres(planet)
    pi = np.clip(np.floor(90 - lat).astype(int), 0, 179)
    pj = np.clip(np.floor(lon + 180).astype(int), 0, 359)
    return pi, pj


def deg_m(planet: str) -> float:
    return math.pi * RADIUS_M[planet] / 180.0
