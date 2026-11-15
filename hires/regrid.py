"""Bring 1-degree fields onto the fine grids."""
import numpy as np

from hires_common import SHAPE, centres, parent_index


def bilinear(planet: str, a1: np.ndarray) -> np.ndarray:
    """NaN-aware bilinear interpolation of a 180x360 field (cell centres) to the fine cell centres.
    Where neighbours are missing, the weights renormalise; isolated cells fall back to the parent."""
    lat, lon = centres(planet)
    fy = np.clip(89.5 - lat, 0, 179)  # fractional row
    fx = (lon + 179.5) % 360  # fractional col (wraps)
    y0 = np.floor(fy).astype(int); y1 = np.minimum(y0 + 1, 179); wy = (fy - y0)[:, None]
    x0 = np.floor(fx).astype(int) % 360; x1 = (x0 + 1) % 360; wx = (fx - np.floor(fx))[None, :]
    num = np.zeros(SHAPE[planet]); den = np.zeros(SHAPE[planet])
    for yy, wyy in ((y0, 1 - wy), (y1, wy)):
        for xx, wxx in ((x0, 1 - wx), (x1, wx)):
            v = a1[yy][:, xx]
            w = wyy * wxx
            ok = np.isfinite(v)
            num += np.where(ok, v, 0) * w
            den += np.where(ok, w, 0)
    with np.errstate(all="ignore"):
        out = num / den
    pi, pj = parent_index(planet)
    par = a1[pi][:, pj]
    out = np.where(den > 0.15, out, par)
    return out.astype(np.float32)


def parent(planet: str, a1: np.ndarray) -> np.ndarray:
    pi, pj = parent_index(planet)
    return a1[pi][:, pj]
