"""Earth NDVI for the 0.1 deg grid: 2019 annual mean of the monthly MODIS/AVHRR 5 km NDVI
(Zenodo 4305975, monthly 90th percentile of cloud-screened daily NDVI), cell mean by pixel centre."""
import glob
import sys
from pathlib import Path

import numpy as np
import tifffile

sys.path.insert(0, str(Path(__file__).parent))
from hires_common import OUT, RAW, bin_mean  # noqa: E402

files = sorted(glob.glob(str(RAW / "ndvi" / "*2019*.tif")))
assert len(files) == 12, files
acc = None
n = None
for f in files:
    a = tifffile.imread(f).astype(np.float32)
    ok = a > -10001
    v = np.where(ok, a / 10000.0, 0)
    acc = v if acc is None else acc + v
    n = ok.astype(np.int16) if n is None else n + ok
with np.errstate(all="ignore"):
    mean = np.where(n >= 1, acc / np.maximum(n, 1), np.nan)  # snow months are masked: Arctic NDVI = snow-free months
px = 0.044915764205963056
s, c = bin_mean("earth", mean, 90.011191469, -180.022382938, px)
with np.errstate(all="ignore"):
    ndvi = (s / c).astype(np.float32)
np.savez_compressed(OUT / "earth_ndvi.npz", ndvi=ndvi)
print("saved; finite cells", int(np.isfinite(ndvi).sum()))
