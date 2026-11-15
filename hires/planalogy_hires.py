"""Planalogy high-resolution analog search (local tool, ~11 km cells on both planets).

Same similarity as the app and engine (adapted Gower: clipped-linear, categorical, boolean, Jaccard;
two-level category/feature weights; the app's mission presets), applied to every Earth land cell at
0.1 deg (~11 km) against a Mars target cell at 0.1875 deg (~11 km). Dry land = Science's rule v2.

Commands (run with the project's Python, -I):
  search  best dry cells today       --preset P [--bbox la0,la1,lo0,lo1] [--top N] [--exclude-known-km 50]
  shift   cells that change status   --preset P --scenario ssp245|ssp585 --year 2030|2050|2070|2090 --kind gain|loss
  cell    one Earth location         --preset P --at lat,lon
  known   catalogued known analogs   --near lat,lon [--km 300]
Options: --mars-point lat,lon (other Mars target), --hyper-arid, --min-sep-km (default 60), --brief.

Each result has: score (0-100) and rank among dry cells, the dry-land status and rank in 2050 and 2090
under both scenarios, per-feature similarity, Earth values, and the nearest catalogued known analog.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from hires_common import OUT, cell_of, centres  # noqa: E402

TAB = OUT / "table"
MANIFEST = HERE / "presets.json"  # features, categories and mission presets (1-degree app manifest)
KNOWN = HERE / "known_analogs.json"  # catalogued known Mars analogs (compiled, unverified; see README)
MINERALS = ["basaltic", "felsic", "clays_hydrated", "sulfates_salts", "carbonates", "iron_oxides"]
TARGET_POINTS = {  # where the rovers actually operate (landing sites); Arcadia as in the app
    "gale": (-4.5895, 137.4417, "Gale crater, Curiosity landing site (Bradbury Landing)"),
    "jezero": (18.4447, 77.4508, "Jezero crater, Perseverance landing site (Octavia E. Butler)"),
    "arcadia": (46.5, -167.5, "Arcadia Planitia (approx., shallow ground ice)"),
}
# Terrain statistics depend on cell and pixel size: the app's tau values were set for 110 km cells on
# ~10 km pixels; here cells are 11 km on ~0.93 km pixels. Each terrain tau is multiplied by the ratio of
# means (11 km / 1 degree) measured on both planets' data (provisional).
USE_TES_TI = False  # see target_values
TAU_SCALE = {"slope_deg": 2.59, "roughness_m": 0.373, "relief_m": 0.390}  # geometric mean of Earth (3.38, 0.380, 0.377) and Mars (1.98, 0.366, 0.401)
DRY_MAX_ARIDITY, HYPER_ARID_BELOW, MAX_NDVI = 0.20, 0.05, 0.2
MAX_LAKE_FRACTION = 0.10  # cells with 10 % or more lake water (Natural Earth) are not dry land
COLD_T, COLD_P, COLD_ALB = 273.15, 250.0, 0.6
SCEN = {"ssp245": "moderate (SSP2-4.5)", "ssp585": "high emissions (SSP5-8.5)"}
TRAJ = ["now", "ssp245_2050", "ssp245_2090", "ssp585_2050", "ssp585_2090"]


def col(name):
    return np.load(TAB / f"{name}.npy", mmap_mode="r")


@lru_cache(maxsize=1)
def manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def static():
    S = {k: col(k) for k in ("lat", "lon", "elevation_m", "slope_deg", "roughness_m", "relief_m", "albedo", "ndvi",
                              "apparent_thermal_inertia", "ground_ice_flag", "inside_impact", "ndvi_source", "water_frac")}
    V = json.loads((TAB / "vocab.json").read_text(encoding="utf-8"))
    S["rocks"] = V["rocks"]
    S["rock_code"] = np.asarray(col("rock_code"))
    S["minerals"] = np.asarray(col("mineral_mask"))
    S["mineral_known"] = np.asarray(col("mineral_known")) > 0
    ati = np.asarray(S["apparent_thermal_inertia"], np.float64)
    tab = np.sort(ati[np.isfinite(ati)])
    pct = np.full(ati.shape, np.nan)
    ok = np.isfinite(ati)
    pct[ok] = np.searchsorted(tab, ati[ok], side="right") / len(tab)
    S["ati_percentile"] = pct
    bad = [S["rocks"].index(x) for x in ("ice", "water", "")]
    base = ~np.isin(S["rock_code"], bad)
    nd = np.asarray(S["ndvi"])
    # bare ground: NDVI < 0.2. Where no NDVI exists at all (after gap filling) only Antarctica counts as bare.
    S["bare"] = base & np.where(np.isfinite(nd), nd < MAX_NDVI, np.asarray(S["lat"]) < -60)
    S["bare"] &= ~(np.asarray(S["water_frac"]) >= MAX_LAKE_FRACTION)  # lake shores (Caspian, Aral, salt lakes) are not dry land
    return S


@lru_cache(maxsize=10)
def climate(key):
    return {k: np.asarray(col(f"{key}__{k}"), np.float32) for k in
            ("air_temp_mean_K", "air_temp_min_K", "air_temp_swing_K", "surface_temp_swing_K", "surface_temp_min_K",
             "precipitation_mm_yr", "aridity_index")}


def dry(cl):
    S = static()
    ai, t, p, alb = cl["aridity_index"], cl["air_temp_mean_K"], cl["precipitation_mm_yr"], np.asarray(S["albedo"])
    arid = np.isfinite(ai) & (ai <= DRY_MAX_ARIDITY)
    cold = np.isfinite(t) & np.isfinite(p) & (t < COLD_T) & (p < COLD_P) & ~(np.isfinite(alb) & (alb >= COLD_ALB))
    return S["bare"] & (arid | cold), S["bare"] & cold & ~arid


@lru_cache(maxsize=1)
def mars():
    with np.load(OUT / "mars_grid.npz") as z:
        return {k: z[k] for k in z.files}


def target_values(lat, lon):
    M = mars()
    r, c = cell_of("mars", lat, lon)
    v = {f: float(M[f][r, c]) for f in ("slope_deg", "roughness_m", "relief_m", "surface_temp_swing_K",
                                         "surface_temp_min_K", "air_temp_swing_K", "albedo")}
    # The scored thermal-inertia feature uses the same formula on both planets, (1 - albedo) / ground day-night swing:
    # Earth has no physical thermal-inertia map, and a Mars TES percentile is not comparable with an Earth ATI
    # percentile (on Earth ATI is almost the inverse of the swing). TES thermal inertia stays in the grid for display.
    if USE_TES_TI and "ti_percentile" in M:
        x = float(M["ti_percentile"][r, c])
        v["ati_percentile"] = x if math.isfinite(x) else None
    else:
        a = M["apparent_thermal_inertia"].astype(np.float64)
        tab = np.sort(a[np.isfinite(a)])
        x = float(a[r, c])
        v["ati_percentile"] = float(np.searchsorted(tab, x, side="right") / len(tab)) if math.isfinite(x) else None
    v["rock_group"] = str(M["rock_group"][r, c]) or None
    mg = str(M["mineral_groups"][r, c])
    v["mineral_groups"] = sorted(mg.split("|")) if mg else None
    v["inside_impact_structure"] = bool(M["inside_crater"][r, c]) if "inside_crater" in M else bool(M["crater_count_1deg"][r, c] > 0)
    v["ground_ice_flag"] = bool(M["ground_ice_flag"][r, c] >= 0.5)
    la, lo = centres("mars")
    v["_cell"] = (round(float(la[r]), 4), round(float(lo[c]), 4))
    return v


WEIGHTS = {"mode": "trained"}  # "trained" (11 km, presets_trained_11km.json, if present) or "app" (1-degree manifest weights)


def preset(pid):
    for p in manifest()["presets"]:
        if p["id"] == pid:
            tf = HERE / "presets_trained_11km.json"
            if WEIGHTS["mode"] == "trained" and tf.exists():
                t = json.loads(tf.read_text(encoding="utf-8"))["presets"].get(pid)
                if t:
                    return {**p, "category_weights": t["category_weights"], "feature_weights": t["feature_weights"], "weights_used": "trained at 11 km"}
            return p
    raise SystemExit(f"unknown preset {pid}; choose from {[p['id'] for p in manifest()['presets']]}")


def effective_weights(cat_w, feat_w):
    cats = {}
    for f in manifest()["features"]:
        cats.setdefault(f["category"], []).append(f["id"])
    tot = sum(float(cat_w.get(c, 0)) for c in cats)
    w = {}
    for c, ids in cats.items():
        W = float(cat_w.get(c, 0)) / tot
        inner = sum(max(0.0, float(feat_w.get(i, 1))) for i in ids)
        for i in ids:
            w[i] = W * max(0.0, float(feat_w.get(i, 1))) / inner if W > 0 and inner > 0 else 0.0
    return w


POP = np.array([bin(i).count("1") for i in range(256)], np.float64)


def score(p, tv, cl):
    S = static()
    w = effective_weights(p["category_weights"], p["feature_weights"])
    n = len(S["lat"])
    num, den, blocked = np.zeros(n), np.zeros(n), np.zeros(n, bool)
    sims = {}
    for f in manifest()["features"]:
        fid, comp, t = f["id"], f["comparator"], tv.get(f["id"])
        if t is None:
            s = np.full(n, np.nan)
        elif comp == "clipped_linear_v1":
            x = S["ati_percentile"] if fid == "ati_percentile" else (cl[fid] if fid in cl else np.asarray(S[fid], np.float64))
            s = 1.0 - np.minimum(1.0, np.abs(x - t) / (f["tau"] * TAU_SCALE.get(fid, 1.0)))
        elif comp == "jaccard_v1":
            tm = sum(1 << i for i, m in enumerate(MINERALS) if m in t)
            inter, uni = POP[S["minerals"] & tm], POP[S["minerals"] | tm]
            s = np.where(uni == 0, 1.0, inter / np.maximum(uni, 1))
            s[~S["mineral_known"]] = np.nan
        elif fid == "rock_group":
            s = (S["rock_code"] == (S["rocks"].index(t) if t in S["rocks"] else -1)).astype(np.float64)
            s[S["rock_code"] == 0] = np.nan
        else:
            x = np.asarray(S["inside_impact"] if fid == "inside_impact_structure" else S[fid], np.float64)
            s = np.where(np.isfinite(x), ((x >= 0.5) == bool(t)).astype(np.float64), np.nan)
        sims[fid] = s
        wf = w.get(fid, 0.0)
        if wf > 0:
            miss = ~np.isfinite(s)
            blocked |= miss
            num += np.where(miss, 0, wf * s)
            den += np.where(miss, 0, wf)
    with np.errstate(all="ignore"):
        sc = num / den
    sc[blocked] = np.nan
    for r in p.get("requirements") or []:
        x = np.asarray(S[r["feature"]], np.float64)
        sc[~((x >= 0.5) == bool(r["equals"]))] = np.nan
    return sc, sims


def hav_km(la1, lo1, la2, lo2):
    p1, p2 = np.radians(la1), np.radians(la2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(np.asarray(lo2) - lo1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(np.minimum(1, a)))


@lru_cache(maxsize=1)
def known():
    try:
        K = json.loads(KNOWN.read_text(encoding="utf-8"))
    except FileNotFoundError:
        K = []
    return K, np.array([k["lat"] for k in K], float), np.array([k["lon"] for k in K], float)


def nearest_known(la, lo):
    K, kl, ko = known()
    if not K:
        return None
    d = hav_km(la, lo, kl, ko)
    i = int(np.argmin(d))
    return {"name": K[i]["name"], "country": K[i].get("country"), "km": round(float(d[i]))}


class Run:
    def __init__(self, pid, mars_point=None):
        self.p = preset(pid)
        la, lo, label = TARGET_POINTS[self.p["target"]] if mars_point is None else (*mars_point, f"Mars point {mars_point}")
        self.label, self.tv, self.c = label, target_values(la, lo), {}

    def year(self, key):
        if key not in self.c:
            cl = climate(key)
            pool, cold = dry(cl)
            sc, sims = score(self.p, self.tv, cl)
            ok = pool & np.isfinite(sc)
            order = np.argsort(-np.where(ok, sc, -np.inf), kind="stable")
            rank = np.zeros(len(sc), np.int64)
            rank[order[:ok.sum()]] = np.arange(1, ok.sum() + 1)
            self.c[key] = {"cl": cl, "pool": pool, "cold": cold, "score": sc.astype(np.float32), "rank": rank.astype(np.int32),
                           "n": int(ok.sum()), "sims": {f: v.astype(np.float32) for f, v in sims.items()} if key == "now" else None}
        return self.c[key]

    def describe(self, i, brief=False):
        S, now = static(), self.year("now")
        la, lo = float(S["lat"][i]), float(S["lon"][i])
        traj = {}
        for k in TRAJ:
            Y = self.year(k)
            traj[k] = {"dry": bool(Y["pool"][i]), "rank": int(Y["rank"][i]) or None, "of": Y["n"],
                       "score": _r(Y["score"][i] * 100, 1), "aridity": _r(Y["cl"]["aridity_index"][i], 3),
                       "T_mean_C": _r(Y["cl"]["air_temp_mean_K"][i] - 273.15, 1), "precip_mm": _r(Y["cl"]["precipitation_mm_yr"][i], 0)}
        d = {"lat": round(la, 2), "lon": round(lo, 2), "score_today": _r(now["score"][i] * 100, 1),
             "rank_today": int(now["rank"][i]) or None, "of_today": now["n"], "dry_today": bool(now["pool"][i]),
             "dry_only_by_cold_desert_rule": bool(now["cold"][i]), "elevation_m": _r(S["elevation_m"][i], 0),
             "ndvi": _r(S["ndvi"][i], 3), "albedo": _r(S["albedo"][i], 3), "rock_group": S["rocks"][int(S["rock_code"][i])],
             "nearest_known_analog": nearest_known(la, lo)}
        if brief:
            d["trajectory"] = {k: f"{'dry' if v['dry'] else 'not dry'} #{v['rank']}/{v['of']}" if v["rank"] else ("dry" if v["dry"] else "not dry") for k, v in traj.items()}
            return d
        d["trajectory"] = traj
        d["similarity_by_feature"] = {f: _r(s[i], 2) for f, s in now["sims"].items()}
        d["earth_values"] = {
            "slope_deg": _r(S["slope_deg"][i], 2), "roughness_m": _r(S["roughness_m"][i], 0), "relief_m": _r(S["relief_m"][i], 0),
            "surface_temp_swing_K": _r(now["cl"]["surface_temp_swing_K"][i], 1), "surface_temp_min_K": _r(now["cl"]["surface_temp_min_K"][i], 1),
            "air_temp_swing_K": _r(now["cl"]["air_temp_swing_K"][i], 1), "ati_percentile": _r(S["ati_percentile"][i], 3),
            "mineral_groups": "|".join(m for j, m in enumerate(MINERALS) if int(S["minerals"][i]) >> j & 1), "inside_impact_structure": bool(S["inside_impact"][i]),
            "ground_ice_flag": bool(S["ground_ice_flag"][i] >= 0.5)}
        return d


def _r(x, n):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, n) if math.isfinite(x) else None


def pick(sc, mask, top, sep, excl, bbox):
    S = static()
    lat, lon = np.asarray(S["lat"]), np.asarray(S["lon"])
    s = np.where(mask & np.isfinite(sc), sc, -np.inf)
    if bbox:
        a, b, c, d = bbox
        s = np.where((lat >= a) & (lat <= b) & (lon >= c) & (lon <= d), s, -np.inf)
    K, kl, ko = known()
    chosen = []
    for i in np.argsort(-s, kind="stable"):
        if not np.isfinite(s[i]) or len(chosen) >= top:
            break
        if excl and len(K) and hav_km(lat[i], lon[i], kl, ko).min() < excl:
            continue
        if any(hav_km(lat[i], lon[i], lat[j], lon[j]) < sep for j in chosen):
            continue
        chosen.append(int(i))
    return chosen


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("search", "shift", "cell"):
        s = sub.add_parser(name)
        s.add_argument("--preset", required=True)
        s.add_argument("--mars-point")
        s.add_argument("--top", type=int, default=12)
        s.add_argument("--bbox")
        s.add_argument("--min-sep-km", type=float, default=60)
        s.add_argument("--exclude-known-km", type=float, default=0)
        s.add_argument("--hyper-arid", action="store_true")
        s.add_argument("--brief", action="store_true")
        s.add_argument("--weights", choices=["trained", "app"], default="trained",
                       help="trained: weights trained on the 11 km grid (default); app: the 1-degree app weights")
        if name == "shift":
            s.add_argument("--scenario", default="ssp585", choices=list(SCEN))
            s.add_argument("--year", type=int, default=2090, choices=[2030, 2050, 2070, 2090])
            s.add_argument("--kind", default="gain", choices=["gain", "loss"])
        if name == "cell":
            s.add_argument("--at", required=True)
    k = sub.add_parser("known")
    k.add_argument("--near", required=True)
    k.add_argument("--km", type=float, default=300)
    a = ap.parse_args(argv)
    if a.cmd == "known":
        la, lo = map(float, a.near.split(","))
        K, kl, ko = known()
        d = hav_km(la, lo, kl, ko)
        print(json.dumps([{"km": round(float(x)), **K[i]} for i, x in sorted(enumerate(d), key=lambda t: t[1]) if x <= a.km],
                         ensure_ascii=False, indent=1))
        return
    WEIGHTS["mode"] = a.weights
    run = Run(a.preset, tuple(map(float, a.mars_point.split(","))) if a.mars_point else None)
    now = run.year("now")
    head = {"preset": a.preset, "weights": run.p.get("weights_used", "app (1-degree)"), "mission": run.p.get("mission") or run.p.get("name"), "mars_target": run.label,
            "mars_cell": run.tv["_cell"], "mars_values": {k: v for k, v in run.tv.items() if not k.startswith("_")},
            "dry_cells_ranked_today": now["n"], "cells": "Earth 0.1 deg / Mars 0.1875 deg, ~11 km"}
    if a.cmd == "cell":
        la, lo = map(float, a.at.split(","))
        r, c = cell_of("earth", la, lo)
        i = int(np.load(TAB / "index2d.npy", mmap_mode="r")[r, c])
        print(json.dumps({**head, "result": None if i < 0 else run.describe(i)}, ensure_ascii=False, indent=1))
        return
    if a.cmd == "search":
        mask, sc = now["pool"].copy(), now["score"]
        if a.hyper_arid:
            ai = now["cl"]["aridity_index"]
            mask &= np.isfinite(ai) & (ai < HYPER_ARID_BELOW)
    else:
        fut = run.year(f"{a.scenario}_{a.year}")
        mask, sc = (fut["pool"] & ~now["pool"], fut["score"]) if a.kind == "gain" else (now["pool"] & ~fut["pool"], now["score"])
        head.update({"shift": f"{a.kind}: {'not dry today, dry' if a.kind == 'gain' else 'dry today, not dry'} in {a.year}, {SCEN[a.scenario]}",
                     "dry_cells_ranked_that_year": fut["n"], "cells_changing": int((mask & np.isfinite(sc)).sum()),
                     "ranked_by": "score in that year" if a.kind == "gain" else "score today"})
    bbox = tuple(map(float, a.bbox.split(","))) if a.bbox else None
    picks = pick(sc, mask, a.top, a.min_sep_km, a.exclude_known_km, bbox)
    print(json.dumps({**head, "results": [run.describe(i, a.brief) for i in picks]}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
