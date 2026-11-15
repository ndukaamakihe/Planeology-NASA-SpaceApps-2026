"""Turn the downloaded CMIP6 projections into yearly Earth grid files for the year slider.

    python prepare_future.py

Input : data/earth/future/<scenario>/<model>/wc2.1_10m_{tmin,tmax,prec}_<model>_<scenario>_<period>.tif
        data/ready/earth_1deg.csv (today)
Output: data/ready/future/<scenario>/earth_1deg_<year>.csv   (year = middle of the 20-year period)
        data/ready/future/summary_<scenario>.csv             (aridity classes per year, watched sites)
        and a copy into Planeology-NASA-SpaceApps-2026/data/grid_1deg/<scenario>/ if that folder exists.

Finer grid:  python prepare_future.py --res 0.25
  reads data/ready/fine/earth_0p25deg.csv.gz (from prepare_data.py --res 0.25) and writes
  data/ready/fine/<scenario>/earth_0p25deg_<year>.csv.gz (land cells, same columns). 10' climate -> 0.25 deg.

Each yearly file has the same 1-degree grid and columns as today's file. Only the climate columns
change; everything else (terrain, geology, albedo, ground temperature, ...) stays as today, because
there is no projection for it (and terrain/geology do not change in 80 years):
  changed : air_temp_mean_K, air_temp_min_K, air_temp_max_K, air_temp_swing_K, precipitation_mm_yr,
            aridity_index, aridity_class  (multi-model ensemble mean)
  kept    : ndvi stays at today's value (no projection). An empty NDVI would let every low-rain cell
            pass the dry/bare filter and fake a climate effect; kept, the filter changes only via rain.
  emptied : soil_moisture_pct, vapour_pressure_kPa  (no projection, not used by the engine)
  added   : n_models, air_temp_change_K, precipitation_change_pct, precipitation_spread_mm_yr,
            aridity_class_today, scenario, period
"""
import glob
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import climate_indices as ci
import prepare_data as p

ROOT = Path(sys.argv[sys.argv.index("--root") + 1]) if "--root" in sys.argv else p.DATA / "earth" / "future"
OUT = p.READY / "future"
REPO = Path(__file__).resolve().parent / "Planeology-NASA-SpaceApps-2026" / "data" / "grid_1deg"
ONLY_SSP = sys.argv[sys.argv.index("--ssp") + 1] if "--ssp" in sys.argv else None
ONLY_PERIOD = sys.argv[sys.argv.index("--period") + 1] if "--period" in sys.argv else None
PERIOD_YEAR = {"2021-2040": 2030, "2041-2060": 2050, "2061-2080": 2070, "2081-2100": 2090}
WATCH = {"Atacama": (-24.5, -69.5), "Arizaro": (-24.5, -67.5), "Kara-Kul": (39.5, 73.5),
         "Dry Valleys": (-77.5, 161.5), "Devon Island": (75.5, -89.5), "Mojave/Death Valley": (36.5, -116.5),
         "Ouarzazate (Morocco)": (31.5, -5.5), "Lake Urmia": (37.5, 45.5), "Great Salt Lake": (41.5, -112.5),
         "Aral Sea": (45.5, 59.5), "Lake Poopo": (-18.5, -67.5), "Southern Spain": (37.5, -3.5)}


def read_months(path):
    import tifffile
    a = tifffile.imread(path).astype("float64")
    if a.ndim == 3 and a.shape[-1] == 12 and a.shape[0] != 12:
        a = np.moveaxis(a, -1, 0)
    a[(a < -1e30) | (a > 1e30) | (a <= -32767)] = np.nan
    return np.array([p.block_mean(m, 6) for m in a])          # 10' -> grid (1 degree by default)


def model_fields(folder, model, ssp, period):
    f = {v: folder / f"wc2.1_10m_{v}_{model}_{ssp}_{period}.tif" for v in ("tmin", "tmax", "prec")}
    if not all(x.exists() for x in f.values()):
        return None
    tmin, tmax, prec = (read_months(f[v]) for v in ("tmin", "tmax", "prec"))
    ai, _ = ci.aridity(tmin, tmax, prec)
    return {"air_temp_mean_K": np.nanmean((tmin + tmax) / 2, 0) + 273.15,
            "air_temp_min_K": np.nanmin(tmin, 0) + 273.15,
            "air_temp_max_K": np.nanmax(tmax, 0) + 273.15,
            "air_temp_swing_K": np.nanmean(tmax - tmin, 0),
            "precipitation_mm_yr": np.nansum(prec, 0) * np.where(np.isfinite(prec).all(0), 1, np.nan),
            "_tmin": tmin, "_tmax": tmax, "_prec": prec}


def main_fine(res):
    """Same as main() on a finer grid: land rows only, gzip CSV, models summed one by one (low memory)."""
    import warnings
    warnings.simplefilter("ignore")
    p.set_grid(res)
    t = p.tag(res)
    fine = p.READY / "fine"
    today = pd.read_csv(fine / f"earth_{t}.csv.gz", keep_default_na=False, na_values=[""])
    i = np.round((90 - today.lat.values) * p.G - .5).astype(int)
    j = np.round((today.lon.values + 180) * p.G - .5).astype(int)
    for ssp_dir in sorted(d for d in ROOT.iterdir() if d.is_dir()):
        ssp = ssp_dir.name
        if ONLY_SSP and ssp != ONLY_SSP:
            continue
        for period, year in PERIOD_YEAR.items():
            if ONLY_PERIOD and period != ONLY_PERIOD:
                continue
            out = fine / ssp / f"earth_{t}_{year}.csv.gz"
            if out.exists() and "--fresh" not in sys.argv:
                print(f"{ssp} {period}: exists, skipped"); continue
            n, acc, precs = 0, {}, []
            for md in sorted(d for d in ssp_dir.iterdir() if d.is_dir()):
                f = {v: md / f"wc2.1_10m_{v}_{md.name}_{ssp}_{period}.tif" for v in ("tmin", "tmax", "prec")}
                if not all(x.exists() for x in f.values()):
                    continue
                tmin, tmax, prec = (read_months(f[v]) for v in ("tmin", "tmax", "prec"))
                for k, v in (("tmin", tmin), ("tmax", tmax), ("prec", prec)):
                    acc[k] = acc.get(k, 0) + v
                precs.append((np.nansum(prec, 0) * np.where(np.isfinite(prec).all(0), 1, np.nan))[i, j])
                n += 1
                del tmin, tmax, prec
            if not n:
                print(f"{ssp} {period}: no complete model found, skipped"); continue
            tmin, tmax, prec = acc["tmin"] / n, acc["tmax"] / n, acc["prec"] / n
            ens = {"air_temp_mean_K": np.nanmean((tmin + tmax) / 2, 0) + 273.15,
                   "air_temp_min_K": np.nanmin(tmin, 0) + 273.15,
                   "air_temp_max_K": np.nanmax(tmax, 0) + 273.15,
                   "air_temp_swing_K": np.nanmean(tmax - tmin, 0),
                   "precipitation_mm_yr": np.nansum(prec, 0) * np.where(np.isfinite(prec).all(0), 1, np.nan)}
            ens["aridity_index"], ens["aridity_class"] = ci.aridity(tmin, tmax, prec, lat=p.LAT)
            df = today.copy()
            for k, v in ens.items():
                v = v[i, j]
                df[k] = v if v.dtype == object else np.round(v.astype(float), 4)
            for k in ("soil_moisture_pct", "vapour_pressure_kPa"):
                df[k] = np.nan
            df["n_models"] = n
            df["air_temp_change_K"] = np.round(df["air_temp_mean_K"] - today["air_temp_mean_K"], 3)
            with np.errstate(all="ignore"):
                df["precipitation_change_pct"] = np.round(100 * (df["precipitation_mm_yr"] / today["precipitation_mm_yr"] - 1), 1)
            df["precipitation_spread_mm_yr"] = np.round(np.nanstd(precs, 0), 1)
            df["aridity_class_today"] = today["aridity_class"].fillna("")
            df["scenario"], df["period"] = ssp, period
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, index=False, compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
            print(f"{ssp} {period} -> {out}  ({n} models)", flush=True)


def write_summary(ssp, today):
    """Aridity classes per year and the watched sites, from all yearly files of one scenario."""
    order = ["hyperarid", "arid", "semi_arid", "dry_subhumid", "humid"]
    rank = {c: i for i, c in enumerate(order)}
    rows = []
    for f in sorted((OUT / ssp).glob("earth_1deg_*.csv")):
        df = pd.read_csv(f, keep_default_na=False, na_values=[""])
        now, was = df.aridity_class.fillna(""), today.aridity_class.fillna("")
        both = (df.is_land == 1) & now.isin(order) & was.isin(order)
        delta = now[both].map(rank) - was[both].map(rank)
        cnt = now[df.is_land == 1].value_counts()
        row = {"scenario": ssp, "year": int(f.stem.split("_")[-1]), "period": df.period.iloc[0],
               "n_models": int(df.n_models.iloc[0]), "cells_drier_class": int((delta < 0).sum()),
               "cells_wetter_class": int((delta > 0).sum()), **{f"cells_{c}": int(cnt.get(c, 0)) for c in order}}
        for name, (la, lo) in WATCH.items():
            r = df[(df.lat == la) & (df.lon == lo)].iloc[0]
            row[f"{name}: class"] = f"{r.aridity_class_today or '-'} -> {r.aridity_class or '-'}"
            row[f"{name}: precip %"] = r.precipitation_change_pct
            row[f"{name}: warming K"] = r.air_temp_change_K
        rows.append(row)
    if rows:
        pd.DataFrame(rows).sort_values("year").to_csv(OUT / f"summary_{ssp}.csv", index=False)


def main():
    if "--res" in sys.argv:
        return main_fine(float(sys.argv[sys.argv.index("--res") + 1]))
    import warnings
    warnings.simplefilter("ignore")
    today = pd.read_csv(p.READY / "earth_1deg.csv", keep_default_na=False, na_values=[""])
    land = (today["is_land"] == 1).values.reshape(180, 360)
    repo = REPO
    for ssp_dir in sorted(d for d in ROOT.iterdir() if d.is_dir()):
        ssp = ssp_dir.name
        if ONLY_SSP and ssp != ONLY_SSP:
            continue
        for period, year in PERIOD_YEAR.items():
            if ONLY_PERIOD and period != ONLY_PERIOD:
                continue
            fields = [m for m in (model_fields(md, md.name, ssp, period) for md in sorted(ssp_dir.iterdir()) if md.is_dir()) if m]
            if not fields:
                print(f"{ssp} {period}: no complete model found, skipped")
                continue
            ens = {k: np.nanmean([m[k] for m in fields], 0) for k in fields[0] if not k.startswith("_")}
            tmin = np.nanmean([m["_tmin"] for m in fields], 0)
            tmax = np.nanmean([m["_tmax"] for m in fields], 0)
            prec = np.nanmean([m["_prec"] for m in fields], 0)
            ens["aridity_index"], ens["aridity_class"] = ci.aridity(tmin, tmax, prec)
            spread = np.nanstd([m["precipitation_mm_yr"] for m in fields], 0)

            df = today.copy()
            for k, v in ens.items():
                v = np.where(land, v, np.nan if v.dtype != object else "")
                df[k] = v.ravel() if v.dtype == object else np.round(v.ravel().astype(float), 4)
            for k in ("soil_moisture_pct", "vapour_pressure_kPa"):
                df[k] = np.nan
            df["n_models"] = len(fields)
            df["air_temp_change_K"] = np.round(df["air_temp_mean_K"] - today["air_temp_mean_K"], 3)
            with np.errstate(all="ignore"):
                df["precipitation_change_pct"] = np.round(100 * (df["precipitation_mm_yr"] / today["precipitation_mm_yr"] - 1), 1)
            df["precipitation_spread_mm_yr"] = np.round(np.where(land, spread, np.nan).ravel(), 1)
            df["aridity_class_today"] = today["aridity_class"].fillna("")
            df["scenario"], df["period"] = ssp, period
            out = OUT / ssp / f"earth_1deg_{year}.csv"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(out, index=False)
            print(f"{ssp} {period} -> {out}  ({len(fields)} models)")

        if (OUT / ssp).exists():
            write_summary(ssp, today)
            (OUT / ssp / "SOURCE.txt").write_text(
                f"Earth grid files for {ssp}, one per 20-year period (file year = middle of the period).\n"
                "Climate columns = multi-model ensemble mean of WorldClim 2.1 CMIP6 projections (see\n"
                "data/earth/future/SOURCE.txt); all other columns as in ../../earth_1deg.csv (no projection).\n"
                "Built by prepare_future.py. Column list and rules: docstring of prepare_future.py.\n", encoding="utf-8")
            if repo.exists():
                dst = repo / ssp
                dst.mkdir(exist_ok=True)
                for f in (OUT / ssp).glob("*"):
                    shutil.copy(f, dst / f.name)
                print(f"copied to {dst}")
    (OUT / "SOURCE.txt").write_text(
        "Future Earth grids (year slider). See <scenario>/SOURCE.txt and summary_<scenario>.csv.\n"
        "Source: WorldClim 2.1 CMIP6 projections, processed by prepare_future.py.\n", encoding="utf-8")


if __name__ == "__main__":
    main()
