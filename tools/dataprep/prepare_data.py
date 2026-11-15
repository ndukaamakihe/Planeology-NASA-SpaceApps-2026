import sys
#!/usr/bin/env python3
"""
Turns the downloaded raw data (data/earth, data/mars) into ONE ready-to-use dataset:

    data/ready/earth_1deg.csv      one row per 1x1 degree cell, one column per parameter
    data/ready/mars_1deg.csv       same columns, same units
    data/ready/analog_1deg.sqlite  tables earth, mars, parameters (for the backend)
    data/ready/parameters.csv      column, unit, description, source per planet, comparable?
    data/ready/preview/*.png       Earth vs Mars map for each parameter

It also unpacks all zip archives next to the zip (step 1).

Run:  python prepare_data.py                         1 degree (the files above)
      python prepare_data.py --res 0.25 --mars-res 0.5  finer grids, written to data/ready/fine/:
          earth_0p25deg.csv.gz (land cells only), mars_0p5deg.csv.gz, parameters.csv
      The finest sensible Earth grid is 0.25 deg: surface temperature and NDVI are stored at 0.2 deg,
      the rock map at 0.5 deg; a finer grid would only split those values.
Needs: numpy pandas scipy tifffile netCDF4 pyhdf matplotlib
"""

import glob
import json
import re
import sqlite3
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
READY = DATA / "ready"
R = {"earth": 6371.0, "mars": 3389.5}     # planet radius km

# The grid is set per planet with set_grid(res). G = cells per degree (1 for the 1-degree grid).
G, RES, NLAT, NLON, LAT, LON = 1, 1.0, 180, 360, None, None


def set_grid(res):
    global G, RES, NLAT, NLON, LAT, LON
    G = int(round(1 / res)); assert abs(G * res - 1) < 1e-9, "res must be 1/n degrees"
    RES, NLAT, NLON = 1.0 / G, 180 * G, 360 * G
    LAT = 90 - (np.arange(NLAT) + 0.5) / G       # cell centres, north -> south
    LON = -180 + (np.arange(NLON) + 0.5) / G     # cell centres, west -> east


def tag(res):
    return ("1deg" if res == 1 else f"{res:g}deg".replace(".", "p"))


set_grid(1.0)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _to_grid_res(a, ppd):
    """Raster with ppd pixels/deg -> raster whose pixel count per cell is a whole number f; returns (a, f).
    A raster coarser than the grid, or not a multiple of it, is repeated (nearest) up to the least common multiple."""
    from math import lcm
    L = lcm(int(ppd), G)
    k = L // int(ppd)
    if k > 1:
        a = np.repeat(np.repeat(a, k, 0), k, 1)
    return a, L // G


def block_mean(a, ppd):
    """Global raster (north-up, lon -180..180) with ppd pixels/deg -> NLAT x NLON mean (NaN ignored)."""
    a = np.asarray(a, dtype="float32" if G > 1 else "float64")
    h, w = a.shape
    assert h == 180 * ppd and w == 360 * ppd, (a.shape, ppd)
    a, f = _to_grid_res(a, ppd)
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore")
        return np.nanmean(a.reshape(NLAT, f, NLON, f), axis=(1, 3)).astype("float64")


def block_mode(a, ppd, nodata):
    a, ppd = _to_grid_res(a, ppd)
    if ppd == 1:
        return a
    b = a.reshape(NLAT, ppd, NLON, ppd).transpose(0, 2, 1, 3).reshape(NLAT, NLON, ppd * ppd)
    out = np.full((NLAT, NLON), nodata, dtype=a.dtype)
    for i in range(NLAT):
        for j in range(NLON):
            v = b[i, j][b[i, j] != nodata]
            if v.size:
                vals, cnt = np.unique(v, return_counts=True)
                out[i, j] = vals[cnt.argmax()]
    return out


def interp_grid(values, lats, lons):
    """values[lat, lon] on an arbitrary regular grid -> grid cell centres (bilinear, lon wraps)."""
    from scipy.interpolate import RegularGridInterpolator
    lats, lons, values = np.asarray(lats, float), np.asarray(lons, float), np.asarray(values, float)
    if lats[0] > lats[-1]:
        lats, values = lats[::-1], values[::-1]
    order = np.argsort(lons)
    lons, values = lons[order], values[:, order]
    lons = np.concatenate([lons[-1:] - 360, lons, lons[:1] + 360])          # wrap
    values = np.concatenate([values[:, -1:], values, values[:, :1]], axis=1)
    lats = np.concatenate([[-90.0], lats, [90.0]]) if lats[0] > -90 else lats
    if values.shape[0] != lats.size:                                        # pad poles with edge rows
        values = np.concatenate([values[:1], values, values[-1:]], axis=0)
    f = RegularGridInterpolator((lats, lons), values, bounds_error=False, fill_value=np.nan)
    gl, gn = np.meshgrid(LAT, LON, indexing="ij")
    return f(np.stack([gl, gn], -1))


def points_to_cells(lat, lon, value=None, how="count"):
    lat, lon = np.asarray(lat, float), (np.asarray(lon, float) + 180) % 360 - 180
    i = np.clip(((90 - lat) * G).astype(int), 0, NLAT - 1)
    j = np.clip(((lon + 180) * G).astype(int), 0, NLON - 1)
    if how == "count":
        out = np.zeros((NLAT, NLON))
        np.add.at(out, (i, j), 1)
        return out
    out = np.full((NLAT, NLON), -np.inf if how == "max" else 0.0)
    if how == "max":
        np.maximum.at(out, (i, j), value)
        out[np.isinf(out)] = np.nan
        return out
    s, n = np.zeros((NLAT, NLON)), np.zeros((NLAT, NLON))
    np.add.at(s, (i, j), value)
    np.add.at(n, (i, j), 1)
    with np.errstate(all="ignore"):
        return np.where(n > 0, s / n, np.nan)


def cell_area_km2(planet):
    r = R[planet]
    top, bot = np.radians(LAT + RES / 2), np.radians(LAT - RES / 2)
    return (r ** 2 * np.radians(RES) * (np.sin(top) - np.sin(bot)))[:, None] * np.ones((1, NLON))


def read_tif(path):
    import tifffile
    raw = tifffile.imread(path)
    a = raw.astype("float64")
    if raw.dtype == np.uint16:
        a[raw == 65535] = np.nan                                  # uint16 nodata (e.g. srad)
    a[(a < -1e30) | (a > 1e30) | (a <= -32767)] = np.nan   # GDAL nodata (float -3.4e38, int16 -32768)
    return a


def read_mcd(path):
    """Mars Climate Database web-interface text grid -> (values[lat, lon], lats, lons)."""
    lats, lons, rows = None, [], []
    for line in Path(path).read_text().splitlines():
        if line.startswith("----") and "||" in line:
            lats = np.array(line.split("||")[1].split(), float)
        elif "||" in line and not line.startswith("#"):
            lon, vals = line.split("||")
            lons.append(float(lon))
            rows.append(np.array(vals.split(), float))
    v = np.array(rows).T                       # [lat, lon]
    lons = np.array(lons)
    keep = lons < 180                          # -180 and +180 are the same meridian
    return v[:, keep], lats, lons[keep]


def mcd_stack(var, lt):
    files = sorted(glob.glob(str(DATA / "mars" / "*" / f"mcd_{var}_Ls*_LT{lt:02d}.txt")))
    return np.array([interp_grid(*read_mcd(f)) for f in files])


def grs_table(path):
    a = np.loadtxt(path)
    lats, lons = np.unique(a[:, 0]), np.unique(a[:, 1])
    g = np.full((lats.size, lons.size), np.nan)
    for la, lo, c in a[:, :3]:
        if c < 9999:
            g[np.searchsorted(lats, la), np.searchsorted(lons, lo)] = c
    lons = (lons + 180) % 360 - 180
    return interp_grid(g, lats, lons)


# --------------------------------------------------------------------------- #
# step 1: unzip
# --------------------------------------------------------------------------- #
def unzip_all():
    for z in DATA.rglob("*.zip"):
        target = z.with_suffix("")
        if target.exists():
            continue
        with zipfile.ZipFile(z) as zf:
            zf.extractall(target)
        print("  unpacked", z.relative_to(DATA))


# --------------------------------------------------------------------------- #
# step 2: EARTH
# --------------------------------------------------------------------------- #
def earth():
    E = {}
    tifs = lambda v: sorted(glob.glob(str(DATA / "earth" / "*" / f"wc2.1_10m_{v}" / "*.tif")))
    stack = lambda v: np.array([block_mean(read_tif(f), 6) for f in tifs(v)])

    elev = block_mean(read_tif(glob.glob(str(DATA / "earth/elevation/wc2.1_5m_elev/*.tif"))[0]), 12)
    land = np.isfinite(elev)
    E["is_land"] = land.astype(float)
    E["elevation_m"] = elev

    def npz(name):
        d = np.load(DATA / "earth" / name)
        return np.array([block_mean(m, 5) for m in d["data"]])
    day, night = npz("surface_temperature/surface_temperature_day.npz"), npz("surface_temperature/surface_temperature_night.npz")
    with np.errstate(all="ignore"):
        import warnings; warnings.simplefilter("ignore")
        E["surface_temp_day_K"] = np.nanmean(day, 0)
        E["surface_temp_night_K"] = np.nanmean(night, 0)
        E["surface_temp_swing_K"] = np.nanmean(day - night, 0)
        E["surface_temp_min_K"] = np.nanmin(night, 0)
        E["surface_temp_max_K"] = np.nanmax(day, 0)

        tavg, tmin, tmax = stack("tavg"), stack("tmin"), stack("tmax")
        E["air_temp_mean_K"] = np.nanmean(tavg, 0) + 273.15
        E["air_temp_min_K"] = np.nanmin(tmin, 0) + 273.15
        E["air_temp_max_K"] = np.nanmax(tmax, 0) + 273.15
        E["air_pressure_Pa"] = np.where(land, 101325 * np.exp(-np.clip(elev, -500, None) / 8434), np.nan)
        E["solar_radiation_Wm2"] = np.nanmean(stack("srad"), 0) * 1000 / 86400
        E["wind_ms"] = np.nanmean(stack("wind"), 0)

        alb = []
        from pyhdf.SD import SD
        for f in sorted(glob.glob(str(DATA / "earth/albedo/*.hdf"))):
            sds = SD(f).select("Albedo_WSA_shortwave")
            a = sds.get().astype("float64")
            a[a == 32767] = np.nan
            alb.append(block_mean(a * 0.001, 20))
        E["albedo"] = np.nanmean(alb, 0) if alb else np.full((NLAT, NLON), np.nan)
        E["apparent_thermal_inertia"] = (1 - E["albedo"]) / E["surface_temp_swing_K"]
        E["apparent_thermal_inertia"][~np.isfinite(E["apparent_thermal_inertia"]) | (E["surface_temp_swing_K"] < 1)] = np.nan

        E["vapour_pressure_kPa"] = np.nanmean(stack("vapr"), 0)
        E["precipitation_mm_yr"] = np.nansum(stack("prec"), 0)
        E["precipitation_mm_yr"][~land] = np.nan
        E["soil_moisture_pct"] = np.nanmean(npz("soil_moisture/soil_moisture_day_monthly_normal.npz"), 0)
        E["ndvi"] = np.nanmean(npz("vegetation/ndvi_monthly_normal.npz"), 0)

    # geology GLiM 0.5 deg -> majority per 1 deg cell
    asc = glob.glob(str(DATA / "earth/geology/GLiM_0.5deg/*.asc"))[0]
    g = np.loadtxt(asc, skiprows=6).astype(int)
    codes = {1: "su", 2: "vb", 3: "ss", 4: "pb", 5: "sm", 6: "sc", 7: "va", 8: "mt", 9: "pa",
             10: "vi", 11: "wb", 12: "py", 13: "pi", 14: "ev", 15: "nd", 16: "ig"}
    gm = block_mode(g, 2, -9999)
    group = {"vb": "volcanic", "va": "volcanic", "vi": "volcanic", "py": "volcanic",
             "mt": "ancient_crust", "pa": "ancient_crust", "pi": "ancient_crust", "pb": "ancient_crust",
             "su": "sedimentary", "ss": "sedimentary", "sm": "sedimentary", "sc": "sedimentary",
             "ev": "evaporite_salt", "ig": "ice", "wb": "water", "nd": ""}
    code_arr = np.vectorize(lambda v: codes.get(v, ""))(gm)
    E["rock_code"] = code_arr
    E["rock_group"] = np.vectorize(lambda c: group.get(c, ""))(code_arr)

    # permafrost (Obu et al.), polar stereographic -> bin by lat/lon
    import netCDF4
    nc = netCDF4.Dataset(DATA / "earth/ground_ice/UiO_PEX_5.0_20181127_2000_2016_25km.nc")
    la, lo, pp = (np.ma.filled(nc[v][:], np.nan).ravel() for v in ("latitude", "longitude", "PerProb"))
    ok = np.isfinite(pp) & np.isfinite(la)
    E["permafrost_prob"] = points_to_cells(la[ok], lo[ok], pp[ok], how="mean")
    covered = points_to_cells(la[np.isfinite(la)], lo[np.isfinite(la)]) > 0
    if G > 1:   # 25 km points do not hit every fine cell: fill holes from the surrounding cells
        from scipy import ndimage
        pp_ = E["permafrost_prob"]; ok_ = np.isfinite(pp_)
        k = 2 * G + 1
        num = ndimage.uniform_filter(np.where(ok_, pp_, 0.0), k, mode="wrap")
        den = ndimage.uniform_filter(ok_.astype(float), k, mode="wrap")
        with np.errstate(all="ignore"):
            E["permafrost_prob"] = np.where(ok_, pp_, np.where(den > 0, num / den, np.nan))
        covered = ndimage.maximum_filter(covered.astype(np.uint8), k, mode="wrap") > 0
    E["permafrost_prob"] = np.where(covered & land & np.isnan(E["permafrost_prob"]), 0.0, E["permafrost_prob"])
    E["ground_ice_flag"] = np.where(land, ((np.nan_to_num(E["permafrost_prob"]) >= 0.5) | (E["rock_group"] == "ice")).astype(float), np.nan)

    # craters
    c = pd.read_csv(DATA / "earth/craters/earth_impact_structures.csv")
    c["name"] = c["name"].astype(str).str.replace(r"\[.*?\]", "", regex=True).str.strip()
    c = c.drop_duplicates(subset=["name", "lat", "lon"])
    c.to_csv(DATA / "earth/craters/earth_impact_structures_clean.csv", index=False)
    E["crater_count"] = points_to_cells(c.lat, c.lon)
    E["crater_max_diam_km"] = points_to_cells(c.lat, c.lon, c.diameter_km.fillna(0).values, how="max")
    return E


# --------------------------------------------------------------------------- #
# step 3: MARS
# --------------------------------------------------------------------------- #
def clean_robbins(path):
    """Repair pages whose columns were written in a different order.
    x/y (geometry) are always right; among the 4 property columns the crater id
    is the text one, lon/lat repeat x/y and the remaining number is the diameter."""
    raw = pd.read_csv(path, dtype=str)
    x = raw.x.astype(float).values
    y = raw.y.astype(float).values
    props = [c for c in raw.columns if c not in ("x", "y")]
    txt = raw[props].values
    num = raw[props].apply(pd.to_numeric, errors="coerce").values
    is_id = np.vectorize(lambda v: bool(re.fullmatch(r"\d\d-\d+", str(v))))(txt)
    used = is_id.copy()
    for ref in (x, ((x + 360) % 360), y):
        hit = (~used) & np.isclose(num, ref[:, None], atol=1e-3)
        first = hit & (np.cumsum(hit, axis=1) == 1)
        used |= first
    diam = np.where(~used, num, np.nan)
    diam = np.nanmax(np.where(np.isnan(diam), -1, diam), axis=1)
    cid = np.where(is_id, txt, "").max(axis=1)
    c = pd.DataFrame({"craterid": cid, "lat": y, "lon": x, "diamkm": diam})
    c = c[c.diamkm > 0].drop_duplicates("craterid")
    c.to_csv(path.with_name("mars_craters_robbins2012_clean.csv"), index=False)
    c["x"], c["y"] = c.lon, c.lat
    return c


def mars():
    M = {"is_land": np.ones((NLAT, NLON))}
    mola = np.fromfile(DATA / "mars/elevation/megt90n000eb.img", ">i2").reshape(2880, 5760).astype(float)
    M["elevation_m"] = np.roll(block_mean(mola, 16), NLON // 2, axis=1)  # 0..360 -> -180..180

    import warnings; warnings.simplefilter("ignore")
    day, night = mcd_stack("tsurf", 14), mcd_stack("tsurf", 2)
    M["surface_temp_day_K"], M["surface_temp_night_K"] = day.mean(0), night.mean(0)
    M["surface_temp_swing_K"] = (day - night).mean(0)
    M["surface_temp_min_K"], M["surface_temp_max_K"] = night.min(0), day.max(0)
    tday, tnight = mcd_stack("t", 14), mcd_stack("t", 2)
    M["air_temp_mean_K"] = np.concatenate([tday, tnight]).mean(0)
    M["air_temp_min_K"], M["air_temp_max_K"] = tnight.min(0), tday.max(0)
    M["air_pressure_Pa"] = np.concatenate([mcd_stack("ps", 14), mcd_stack("ps", 2)]).mean(0)
    daymean = sorted(glob.glob(str(DATA / "mars/solar_radiation/mcd_fluxsurf_dn_sw_Ls*_daymean.txt")))
    M["solar_radiation_Wm2"] = (np.array([interp_grid(*read_mcd(f)) for f in daymean]).mean(0)
                                if daymean else np.full((NLAT, NLON), np.nan))
    M["solar_flux_14h_Wm2"] = mcd_stack("fluxsurf_dn_sw", 14).mean(0)
    M["wind_ms"] = np.concatenate([mcd_stack("wind", 14), mcd_stack("wind", 2)]).mean(0)

    alb = np.fromfile(DATA / "mars/albedo/global_albedo_8ppd.img", "<f4").reshape(1440, 2880).astype(float)
    alb[alb <= 0] = np.nan
    M["albedo"] = block_mean(alb, 8)
    ti = np.full((1440, 2880), np.nan)
    raw = np.fromfile(DATA / "mars/thermal_inertia/global_ti_60n_50s_8ppd.img", "<f4").reshape(882, 2880).astype(float)
    raw[raw <= 0] = np.nan
    ti[239:239 + 882] = raw
    M["thermal_inertia_SI"] = block_mean(ti, 8)
    M["apparent_thermal_inertia"] = (1 - M["albedo"]) / M["surface_temp_swing_K"]

    dci = np.fromfile(DATA / "mars/dust_cover/dci_lo_ice_dust_16ppd_shifted.pds", "<f4", offset=1024).reshape(2880, 5760).astype(float)
    dci[(dci < 0.5) | (dci > 1.2)] = np.nan
    M["dust_cover_index"] = block_mean(dci, 16)

    env = np.fromfile(DATA / "mars/minerals/TES_mineral_maps_4_ppd.envi", ">f4").reshape(13, 720, 1440).astype(float)
    names = ["quartz", "k_feldspar", "plagioclase", "amphibole", "low_ca_pyroxene", "high_ca_pyroxene",
             "olivine", "hematite", "sulfates", "carbonates", "sheet_silicates_hi_si_glass", "surface_dust"]
    for k, n in enumerate(names):
        b = env[k].copy()
        b[(b < 0) | (b > 1.5)] = np.nan
        M[f"mineral_{n}"] = block_mean(b, 4)
    h = pd.read_csv(DATA / "mars/minerals/hydrous_sites_geo_map.csv", header=None)
    M["hydrated_mineral_sites"] = points_to_cells(h[1], h[0])

    M["ground_ice_h2o_wt"] = grs_table(DATA / "mars/ground_ice/h2o_sr_5x5.tab")
    for el in ["fe", "k", "cl", "si", "th"]:
        M[f"chem_{el}_wt"] = grs_table(DATA / f"mars/chemistry/{el}_sr_5x5.tab")

    # geology polygons -> unit of each cell centre
    from matplotlib.path import Path as MPath
    g = json.loads((DATA / "mars/geology/mars_geologic_units_sim3292.geojson").read_text())
    unit = np.full((NLAT, NLON), "", dtype=object)
    gl, gn = np.meshgrid(LAT, LON, indexing="ij")
    pts = np.column_stack([gn.ravel(), gl.ravel()])
    for f in g["features"]:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            outer = np.asarray(poly[0])
            x0, y0 = outer.min(0)
            x1, y1 = outer.max(0)
            cand = np.where((pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1))[0]
            if cand.size == 0:
                continue
            inside = MPath(outer).contains_points(pts[cand])
            for hole in poly[1:]:
                inside &= ~MPath(np.asarray(hole)).contains_points(pts[cand])
            unit.ravel()[cand[inside]] = f["properties"]["unit"]

    groups = {
        "volcanic": "AHv eHv lAv lHv lNv Av Ave lHvf Hve lAvf Nve",
        "ancient_crust": "mNh eNh lNh eNhm mNhm eHh Nhu HNhu Nhe",
        "impact": "AHi",
        "ice": "Apu Hp lApc Ap Hpe Hpu",
        "sedimentary": "lHl mAl eHt HNt lHt AHtu Hto Ht Htu lHb HNb eAb eHb Aa ANa lAa lApd",
    }
    u2g = {u: g for g, us in groups.items() for u in us.split()}
    M["rock_code"] = unit
    M["rock_group"] = np.vectorize(lambda u: u2g.get(u, ""))(unit)
    M["ground_ice_flag"] = ((np.nan_to_num(M["ground_ice_h2o_wt"]) >= 10) | (M["rock_group"] == "ice")).astype(float)

    c = clean_robbins(DATA / "mars/craters/mars_craters_robbins2012.csv")
    M["crater_count"] = points_to_cells(c.y, c.x)
    M["crater_max_diam_km"] = points_to_cells(c.y, c.x, c.diamkm.values, how="max")
    return M


# --------------------------------------------------------------------------- #
# parameter catalogue (also written to parameters.csv / sqlite)
# --------------------------------------------------------------------------- #
P = [  # column, unit, description, earth source, mars source, comparable
    ("is_land", "0/1", "1 = land cell (Mars: always 1)", "WorldClim elevation mask", "-", "filter"),
    ("cell_area_km2", "km2", "Area of the grid cell (differs per planet and latitude)", "computed", "computed", "helper"),
    ("slope_deg", "deg", "P1: mean slope inside the cell, from a ~9-10 km DEM grid (same method both planets)", "WorldClim 5' elevation", "MOLA resampled to 6 ppd", "yes"),
    ("roughness_m", "m", "P1: standard deviation of elevation inside the cell (~9-10 km pixels)", "WorldClim 5' elevation", "MOLA resampled to 6 ppd", "yes"),
    ("relief_m", "m", "P1: highest minus lowest point inside the cell (~9-10 km pixels)", "WorldClim 5' elevation", "MOLA resampled to 6 ppd", "yes"),
    ("elevation_m", "m", "Surface height (Earth: above sea level, Mars: above areoid)", "WorldClim 2.1 (SRTM) 5'", "MOLA MEGDR 16 ppd", "yes"),
    ("surface_temp_day_K", "K", "Mean daytime ground temperature", "MODIS MOD11C1 day, monthly normal 2012-21", "MCD v6 tsurf 14h, 4 seasons", "yes"),
    ("surface_temp_night_K", "K", "Mean night-time ground temperature", "MODIS MOD11C1 night", "MCD v6 tsurf 02h", "yes"),
    ("surface_temp_swing_K", "K", "Mean day minus night ground temperature", "MODIS", "MCD v6", "yes"),
    ("surface_temp_min_K", "K", "Coldest monthly/seasonal night ground temperature", "MODIS", "MCD v6", "yes"),
    ("surface_temp_max_K", "K", "Warmest monthly/seasonal day ground temperature", "MODIS", "MCD v6", "yes"),
    ("air_temp_swing_K", "K", "P2: mean daily air temperature range (Earth tmax-tmin per month; Mars 14h-02h per season)", "WorldClim tmax, tmin", "MCD v6 t 14h - 02h", "yes"),
    ("air_temp_mean_K", "K", "Mean air temperature near the ground", "WorldClim tavg (2 m)", "MCD v6 t at 10 m", "yes"),
    ("air_temp_min_K", "K", "Coldest air temperature (coldest month / season night)", "WorldClim tmin", "MCD v6 t 02h", "yes"),
    ("air_temp_max_K", "K", "Warmest air temperature (warmest month / season day)", "WorldClim tmax", "MCD v6 t 14h", "yes"),
    ("air_pressure_Pa", "Pa", "Surface air pressure", "computed from elevation (barometric)", "MCD v6 ps", "yes (Mars ~100x lower)"),
    ("solar_radiation_Wm2", "W/m2", "Daily mean sunlight at the ground", "WorldClim srad", "MCD v6 daily mean (if downloaded)", "yes"),
    ("solar_flux_14h_Wm2", "W/m2", "Sunlight at 14h local time (Mars only, instantaneous)", "-", "MCD v6 fluxsurf_dn_sw 14h", "no"),
    ("wind_ms", "m/s", "Mean near-surface wind speed", "WorldClim wind", "MCD v6 wind 10 m", "yes"),
    ("albedo", "0..1", "Surface brightness", "MODIS MCD43C3 white-sky shortwave, 4 dates 2024", "TES bolometric albedo", "yes"),
    ("apparent_thermal_inertia", "1/K", "(1 - albedo) / day-night swing; same formula on both planets", "computed", "computed", "yes"),
    ("thermal_inertia_SI", "J m-2 K-1 s-1/2", "Physical thermal inertia (Mars only)", "-", "TES (Mellon 2000), 60N-50S", "no"),
    ("rock_group", "class", "Common rock group: volcanic, ancient_crust, sedimentary, evaporite_salt, ice, impact, water", "GLiM classes grouped", "SIM 3292 units grouped", "yes"),
    ("rock_code", "code", "Original class (Earth GLiM code / Mars SIM 3292 unit)", "GLiM", "SIM 3292", "no"),
    ("ground_ice_flag", "0/1", "1 = ground ice likely (Earth: permafrost >= 0.5 or glacier; Mars: H2O >= 10 wt% or polar unit)", "Obu 2019 + GLiM", "Odyssey GRS + SIM 3292", "yes"),
    ("permafrost_prob", "0..1", "Permafrost probability (Earth, northern hemisphere)", "Obu et al. 2019", "-", "no"),
    ("ground_ice_h2o_wt", "wt%", "Water-equivalent hydrogen in top metre (Mars)", "-", "Odyssey GRS 5x5 deg", "no"),
    ("crater_count", "n", "Impact craters with centre in the cell", "Earth Impact Database (Wikipedia lists)", "Robbins 2012 (>= 1 km)", "yes (use density)"),
    ("crater_density_per_10k_km2", "n per 10000 km2", "crater_count normalised by cell area", "computed", "computed", "yes"),
    ("crater_max_diam_km", "km", "Largest crater in the cell", "EID", "Robbins 2012", "yes"),
    ("mineral_groups", "set", "P7 PROXY: present mineral groups, '|' separated (basaltic, felsic, clays_hydrated, sulfates_salts, carbonates, iron_oxides)", "GLiM class -> typical minerals", "TES (normalised, >= 20 %) + OMEGA/CRISM hydrated sites", "yes (proxy)"),
    ("dust_cover_index", "-", "TES dust cover index (lower = more dust)", "-", "Ruff & Christensen 2002", "no"),
    ("hydrated_mineral_sites", "n", "Detections of water-formed minerals (clays, sulfates)", "-", "OMEGA + CRISM", "no"),
]
P += [(f"mineral_{n}", "fraction", f"TES abundance of {n.replace('_', ' ')}", "-", "TES (Bandfield 2002) 4 ppd", "no")
      for n in ["quartz", "k_feldspar", "plagioclase", "amphibole", "low_ca_pyroxene", "high_ca_pyroxene",
                "olivine", "hematite", "sulfates", "carbonates", "sheet_silicates_hi_si_glass", "surface_dust"]]
P += [(f"chem_{e}_wt", "wt%" if e != "th" else "ppm-scale (see label)", f"{e.upper()} concentration", "-", "Odyssey GRS 5x5 deg", "no")
      for e in ["fe", "k", "cl", "si", "th"]]
P += [("vapour_pressure_kPa", "kPa", "Water vapour in air (Earth-only filter)", "WorldClim vapr", "-", "filter"),
      ("precipitation_mm_yr", "mm/yr", "Yearly precipitation (Earth-only filter)", "WorldClim prec", "-", "filter"),
      ("soil_moisture_pct", "%", "Topsoil water (Earth-only filter, no data over ice)", "AMSR2 via JAXA", "-", "filter"),
      ("ndvi", "-1..1", "Vegetation index (Earth-only filter)", "MODIS via JAXA", "-", "filter"),
      ("aridity_index", "-", "Earth-only filter: yearly precipitation / Hargreaves PET (UNEP aridity index, same method today and in projections)", "WorldClim tmin, tmax, prec", "-", "filter"),
      ("aridity_class", "class", "Earth-only filter: hyperarid < 0.05 <= arid < 0.2 <= semi_arid < 0.5 <= dry_subhumid < 0.65 <= humid", "from aridity_index", "-", "filter")]


def to_frame(planet, d):
    d["cell_area_km2"] = cell_area_km2(planet)
    d["crater_density_per_10k_km2"] = d["crater_count"] / d["cell_area_km2"] * 1e4
    gl, gn = np.meshgrid(LAT, LON, indexing="ij")
    df = pd.DataFrame({"lat": gl.ravel(), "lon": gn.ravel()})
    for col, *_ in P:
        v = d.get(col, np.full((NLAT, NLON), np.nan))
        v = np.asarray(v)
        df[col] = v.ravel() if v.dtype == object or v.dtype.kind in "US" else np.round(v.ravel().astype(float), 4)
    return df


def preview(earth_df, mars_df):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = READY / "preview"
    out.mkdir(parents=True, exist_ok=True)
    for col, unit, desc, *_ in P:
        if col in ("rock_code", "cell_area_km2", "is_land"):
            continue
        fig, axes = plt.subplots(1, 2, figsize=(13, 3.6))
        for ax, (name, df) in zip(axes, [("Earth", earth_df), ("Mars", mars_df)]):
            v = df[col]
            if v.dtype == object:
                cats = sorted(c for c in set(earth_df[col]) | set(mars_df[col]) if c)
                v = v.map({c: i for i, c in enumerate(cats)}).astype(float)
                im = ax.imshow(v.values.reshape(180, 360), extent=[-180, 180, -90, 90], cmap="tab10", vmin=0, vmax=9)
                ax.set_title(f"{name}  ({', '.join(f'{i}={c}' for i, c in enumerate(cats))})", fontsize=7, loc="left")
            else:
                arr = v.values.reshape(180, 360).astype(float)
                if np.all(np.isnan(arr)):
                    ax.text(0, 0, "not available", ha="center", va="center", color="#888")
                    ax.set_xlim(-180, 180); ax.set_ylim(-90, 90)
                    ax.set_title(name, loc="left", fontsize=10)
                    continue
                vmin, vmax = np.nanpercentile(arr, [2, 98])
                im = ax.imshow(arr, extent=[-180, 180, -90, 90], cmap="viridis", vmin=vmin, vmax=vmax)
                ax.set_title(name, loc="left", fontsize=10)
                fig.colorbar(im, ax=ax, shrink=0.8, label=unit)
            ax.tick_params(labelsize=7)
        fig.suptitle(f"{col} - {desc}", fontsize=10, x=0.01, ha="left")
        fig.tight_layout()
        fig.savefig(out / f"{col}.png", dpi=90)
        plt.close(fig)


def main():
    # extra_features imports this file as "prepare_data": make that the same module as the one running,
    # so the grid set here (set_grid) is the grid it uses.
    sys.modules.setdefault("prepare_data", sys.modules[__name__])
    # Each step caches its result, so a run that stops can be restarted
    # (python prepare_data.py --fresh recomputes everything).
    import pickle
    cache = DATA / "_prep_cache"
    cache.mkdir(parents=True, exist_ok=True)
    def step(name, fn):
        f = cache / f"{name}.pkl"
        if f.exists() and "--fresh" not in sys.argv:
            return pickle.loads(f.read_bytes())
        r = fn()
        f.write_bytes(pickle.dumps(r))
        return r
    arg = lambda k, d: float(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    er, mr = arg("--res", 1.0), arg("--mars-res", arg("--res", 1.0))
    if (er, mr) != (1.0, 1.0):
        return main_fine(er, mr, step)
    print("1/4 unpacking archives")
    unzip_all()
    print("2/4 Earth")
    import extra_features as x
    e = to_frame("earth", step("earth", lambda: x.earth_extra(earth())))
    print("3/4 Mars")
    m = to_frame("mars", step("mars", lambda: x.mars_extra(mars())))
    print("4/4 writing outputs")
    READY.mkdir(parents=True, exist_ok=True)
    e.to_csv(READY / "earth_1deg.csv", index=False)
    m.to_csv(READY / "mars_1deg.csv", index=False)
    params = pd.DataFrame(P, columns=["column", "unit", "description", "earth_source", "mars_source", "comparable"])
    params.to_csv(READY / "parameters.csv", index=False)
    # sqlite cannot lock files on some mounted/synced folders, so build it in temp and copy
    import tempfile, shutil
    tmpdb = Path(tempfile.gettempdir()) / "analog_1deg.sqlite"
    if tmpdb.exists():
        tmpdb.unlink()
    with sqlite3.connect(tmpdb) as con:
        e.to_sql("earth", con, if_exists="replace", index=False)
        m.to_sql("mars", con, if_exists="replace", index=False)
        params.to_sql("parameters", con, if_exists="replace", index=False)
        for t in ("earth", "mars"):
            con.execute(f"CREATE INDEX IF NOT EXISTS idx_{t}_latlon ON {t}(lat, lon)")
    con.close()
    shutil.copyfile(tmpdb, READY / "analog_1deg.sqlite")
    (READY / "SOURCE.txt").write_text(
        "Ready-to-use dataset, 1 x 1 degree grid, cell centres lat 89.5..-89.5, lon -179.5..179.5 (east positive).\n"
        "Same columns and units on both planets (temperatures K, pressure Pa, radiation W/m2, heights m).\n"
        "Empty value = parameter not available on this planet or no data in this cell.\n"
        "Built by prepare_data.py from the raw files in data/earth and data/mars.\n"
        "Column descriptions, units and sources per planet: parameters.csv (also table 'parameters' in the sqlite).\n"
        "Preview maps of every column: preview/*.png\n", encoding="utf-8")
    if "--no-preview" not in sys.argv:
        preview(e, m)
    print(f"done -> {READY}")


def main_fine(er, mr, step):
    """Finer grids for the app: Earth land cells only (the ocean is never a candidate), gzip CSV."""
    import extra_features as x
    out = READY / "fine"
    out.mkdir(parents=True, exist_ok=True)
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else "earth,mars"
    unzip_all()
    if "earth" in only:
        set_grid(er)
        print(f"Earth {RES} deg ({NLAT} x {NLON})")
        e = to_frame("earth", step(f"earth_{tag(er)}", lambda: x.earth_extra(earth())))
        e = e[e.is_land == 1]
        e.to_csv(out / f"earth_{tag(er)}.csv.gz", index=False, compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
        print("  ->", out / f"earth_{tag(er)}.csv.gz", len(e), "land cells")
    if "mars" in only:
        set_grid(mr)
        print(f"Mars {RES} deg ({NLAT} x {NLON})")
        m = to_frame("mars", step(f"mars_{tag(mr)}", lambda: x.mars_extra(mars())))
        m.to_csv(out / f"mars_{tag(mr)}.csv.gz", index=False, compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
        print("  ->", out / f"mars_{tag(mr)}.csv.gz", len(m), "cells")
    pd.DataFrame(P, columns=["column", "unit", "description", "earth_source", "mars_source", "comparable"]).to_csv(out / "parameters.csv", index=False)
    (out / "SOURCE.txt").write_text(
        f"Finer grids built by prepare_data.py --res {er} --mars-res {mr}: same columns and units as the 1-degree files.\n"
        "Earth file holds land cells only. Native data resolution limits the detail: surface temperature, NDVI and\n"
        "soil moisture 0.2 deg, rock map (GLiM) 0.5 deg, permafrost 25 km, climate 10', elevation 5', albedo 0.05 deg;\n"
        "Mars climate (MCD) about 5 deg, TES minerals 0.25 deg, albedo/thermal inertia 0.125 deg, MOLA 1/16 deg.\n", encoding="utf-8")
    print("done ->", out)


if __name__ == "__main__":
    main()
