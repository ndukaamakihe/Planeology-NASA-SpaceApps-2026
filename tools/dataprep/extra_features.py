"""Extra columns for the Science P1-P10 analysis, computed the same way on both planets.

P1 terrain  slope_deg, roughness_m, relief_m  from a ~9-10 km DEM grid
            (Earth WorldClim 5' = 9.3 km, Mars MOLA resampled to 6 ppd = 9.9 km),
            mean slope / std of elevation / max-min elevation inside each 1-degree cell.
P2 thermal  air_temp_swing_K  mean daily air temperature range
            (Earth: mean over 12 months of tmax - tmin, WorldClim;
             Mars: mean over 4 seasons of air T at 14h - 02h, Mars Climate Database).
P7 minerals mineral_groups  shared vocabulary, '|' separated (PROXY, see MINERAL_* below).
P8 geology  rock_group on Mars: cells whose unit is an impact unit (AHi) get the most
            frequent non-impact group of the surrounding 5x5 cells (crater fill takes the
            material of its surroundings). The original unit stays in rock_code.
"""
import glob
import numpy as np
from scipy import ndimage

import prepare_data as p

R_KM = {"earth": 6371.0, "mars": 3389.5}
MINERAL_GROUPS = ["basaltic", "felsic", "clays_hydrated", "sulfates_salts", "carbonates", "iron_oxides"]
# Earth: GLiM lithology class -> typical mineral groups (proxy)
GLIM_MINERALS = {
    "vb": ["basaltic"], "pb": ["basaltic"], "py": ["basaltic"],
    "vi": ["basaltic", "felsic"], "pi": ["basaltic", "felsic"],
    "va": ["felsic"], "pa": ["felsic"], "mt": ["felsic"],
    "ss": ["felsic", "clays_hydrated"], "su": ["felsic", "clays_hydrated"],
    "sm": ["felsic", "clays_hydrated", "carbonates"], "sc": ["carbonates"],
    "ev": ["sulfates_salts", "carbonates"],
}
# Mars: TES abundances are normalised to the sum of all non-dust minerals in the cell
# (the raw fractions also contain atmosphere/blackbody), then a group counts as present
# from 20 % of that sum. Gale -> basaltic + clays_hydrated, Meridiani -> iron_oxides.
TES_MIN = 0.20


def shrink(a, f):
    h, w = a.shape
    return a.reshape(h // f, f, w // f, f).mean(axis=(1, 3))


def terrain(elev, ppd, planet):
    h, w = elev.shape
    lat = 90 - (np.arange(h) + 0.5) / ppd
    dy = R_KM[planet] * 1000 * np.deg2rad(1 / ppd)
    dx = dy * np.cos(np.deg2rad(lat))[:, None]
    gy = np.gradient(elev, axis=0) / dy
    gx = (np.roll(elev, -1, 1) - np.roll(elev, 1, 1)) / (2 * dx)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    f = ppd // p.G
    assert f * p.G == ppd, "DEM resolution must be a multiple of the grid"
    b = lambda a: a.reshape(p.NLAT, f, p.NLON, f)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return (np.nanmean(b(slope), axis=(1, 3)), np.nanstd(b(elev), axis=(1, 3)),
                np.nanmax(b(elev), axis=(1, 3)) - np.nanmin(b(elev), axis=(1, 3)))


def earth_extra(E):
    elev = p.read_tif(glob.glob(str(p.DATA / "earth/elevation/wc2.1_5m_elev/*.tif"))[0])
    E["slope_deg"], E["roughness_m"], E["relief_m"] = terrain(elev, 12, "earth")
    tifs = lambda v: sorted(glob.glob(str(p.DATA / "earth" / "*" / f"wc2.1_10m_{v}" / "*.tif")))
    tmax = np.array([p.block_mean(p.read_tif(f), 6) for f in tifs("tmax")])
    tmin = np.array([p.block_mean(p.read_tif(f), 6) for f in tifs("tmin")])
    E["air_temp_swing_K"] = np.nanmean(tmax - tmin, 0)
    import climate_indices as ci
    prec = np.array([p.block_mean(p.read_tif(f), 6) for f in tifs("prec")])
    E["aridity_index"], E["aridity_class"] = ci.aridity(tmin, tmax, prec, lat=p.LAT)
    codes = np.asarray(E["rock_code"])
    E["mineral_groups"] = np.vectorize(lambda c: "|".join(GLIM_MINERALS.get(c, [])))(codes)
    return E


def mars_extra(M):
    mola = np.fromfile(p.DATA / "mars/elevation/megt90n000eb.img", ">i2").reshape(2880, 5760).astype(float)
    mola = np.roll(mola, 2880, axis=1)                      # 0..360 -> -180..180
    m6 = ndimage.zoom(shrink(mola, 2), 0.75, order=1)   # 16 -> 8 -> 6 ppd
    M["slope_deg"], M["roughness_m"], M["relief_m"] = terrain(m6, 6, "mars")
    M["air_temp_swing_K"] = (p.mcd_stack("t", 14) - p.mcd_stack("t", 2)).mean(0)

    tes = [k for k in M if k.startswith("mineral_") and k not in ("mineral_groups", "mineral_surface_dust")]
    total = sum(np.nan_to_num(np.asarray(M[k], float)) for k in tes)
    with np.errstate(all="ignore"):
        g = lambda k: (np.nan_to_num(np.asarray(M[k], float) / total) if k in tes
                       else np.nan_to_num(np.asarray(M[k], float)))
    has = np.isfinite(np.asarray(M["mineral_plagioclase"], float))
    rules = {
        "basaltic": (g("mineral_plagioclase") >= TES_MIN) | (g("mineral_high_ca_pyroxene") >= TES_MIN)
                    | (g("mineral_low_ca_pyroxene") >= TES_MIN) | (g("mineral_olivine") >= TES_MIN),
        "felsic": (g("mineral_k_feldspar") >= TES_MIN) | (g("mineral_quartz") >= TES_MIN),
        "clays_hydrated": (g("mineral_sheet_silicates_hi_si_glass") >= TES_MIN) | (g("hydrated_mineral_sites") > 0),
        "sulfates_salts": g("mineral_sulfates") >= TES_MIN,
        "carbonates": g("mineral_carbonates") >= TES_MIN,
        "iron_oxides": g("mineral_hematite") >= TES_MIN,
    }
    out = np.empty((p.NLAT, p.NLON), dtype=object)
    for i in range(p.NLAT):
        for j in range(p.NLON):
            out[i, j] = "|".join(k for k in MINERAL_GROUPS if rules[k][i, j]) if (has[i, j] or rules["clays_hydrated"][i, j]) else ""
    M["mineral_groups"] = out

    grp = np.asarray(M["rock_group"], dtype=object)
    fixed = grp.copy()
    r = 2 * p.G   # same +/- 2 degrees on every grid
    for i, j in zip(*np.where(grp == "impact")):
        vals = [grp[ii, jj % p.NLON] for ii in range(max(0, i - r), min(p.NLAT, i + r + 1)) for jj in range(j - r, j + r + 1)]
        vals = [v for v in vals if v not in ("impact", "")]
        if vals:
            fixed[i, j] = max(set(vals), key=vals.count)
    M["rock_group"] = fixed
    return M
