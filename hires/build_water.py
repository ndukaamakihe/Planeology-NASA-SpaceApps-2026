"""Inland water fraction for the 0.1 deg Earth grid from Natural Earth 10 m lakes and reservoirs
(main + North America + Europe supplements), rasterised at 0.02 deg and averaged to 0.1 deg."""
import sys
from pathlib import Path

import numpy as np
import shapefile
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW  # noqa: E402

F = 5  # 0.02 deg supersampling
W, H = 3600 * F, 1800 * F
img = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(img)
n = 0
for name in ("ne_10m_lakes", "ne_10m_lakes_north_america", "ne_10m_lakes_europe"):
    sf = shapefile.Reader(str(RAW / "lakes" / name / f"{name}.shp"))
    for shp in sf.iterShapes():
        pts, parts = shp.points, list(shp.parts) + [len(shp.points)]
        for a, b in zip(parts[:-1], parts[1:]):
            ring = [((x + 180) * 10 * F, (90 - y) * 10 * F) for x, y in pts[a:b]]
            if len(ring) >= 3:
                dr.polygon(ring, fill=255)  # islands inside lakes are ignored (small at 11 km)
        n += 1
a = (np.asarray(img, np.float32) / 255).reshape(1800, F, 3600, F).mean(axis=(1, 3))
np.savez_compressed(OUT / "earth_water.npz", water_frac=a.astype(np.float32))
print("lakes", n, "cells >= 50% water", int((a >= 0.5).sum()))
