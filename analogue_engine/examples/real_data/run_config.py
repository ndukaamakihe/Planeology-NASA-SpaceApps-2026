"""Run the engine from a settings file (analysis_config.json) - the entry point for the GUI.

    python examples/real_data/run_config.py <data_dir> [config.json]

In the config every parameter has ``use`` (1 = scored, 0 = ignored), ``weight``
and, for numbers, ``tau`` (the difference at which similarity reaches 0). The
defaults are the Science P1-P10 recommendation from grid_1deg.profile().

From the GUI (Python backend):

    from run_config import load_config, run
    cfg = load_config()                          # defaults
    cfg["parameters"]["albedo"]["use"] = 0       # switch a parameter off
    cfg["parameters"]["slope_deg"]["weight"] = 3 # or change its weight
    result = run(cfg, Path("data/grid_1deg"))    # plain dict, JSON-safe

``result["ranking"]`` has one entry per ranked Earth cell (lat, lon, score
0-100, coverage, score per dimension) for the heat map; ``result["timeline"]``
is filled when ``timeline.use = 1`` and the yearly files exist.

Writes, next to this script (CLI only):
  output_config_ranking.json   the result dict
  output_config_scores.csv     lat, lon, position, score_0_100, coverage, dim_* (heat map)
"""

from __future__ import annotations

import copy
import csv
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
sys.path.insert(0, str(HERE))

from analogue_engine import rank, rank_over_years  # noqa: E402
import grid_1deg as g  # noqa: E402

DEFAULT_CONFIG = HERE / "analysis_config.json"
TARGETS = {"gale": (-5.5, 137.5), "jezero": (18.5, 77.5), "arcadia": (46.5, -167.5)}


# ----------------------------------------------------------------- settings
def load_config(path: Path | str | None = None) -> dict[str, Any]:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as handle:
        return json.load(handle)


def validate(cfg: dict[str, Any]) -> list[str]:
    """Problems that would make the run meaningless; empty list = fine."""
    defs = {d["id"]: d for d in g.feature_definitions()}
    errors = []
    used = 0
    for fid, p in cfg.get("parameters", {}).items():
        if fid not in defs:
            errors.append(f"unknown parameter '{fid}'")
            continue
        if p.get("use") not in (0, 1):
            errors.append(f"{fid}: use must be 0 or 1")
        if not p.get("use"):
            continue
        used += 1
        if not isinstance(p.get("weight"), (int, float)) or p["weight"] < 0:
            errors.append(f"{fid}: weight must be a number >= 0")
        if defs[fid]["kind"] == "scalar" and not (isinstance(p.get("tau"), (int, float)) and p["tau"] > 0):
            errors.append(f"{fid}: tau must be a number > 0")
    if used == 0:
        errors.append("no parameter has use = 1")
    for dim, w in cfg.get("dimension_weights", {}).items():
        if not isinstance(w, (int, float)) or w < 0:
            errors.append(f"dimension '{dim}': weight must be a number >= 0")
    return errors


def target_cell(cfg: dict[str, Any]) -> tuple[float, float]:
    t = cfg.get("target", "gale")
    if isinstance(t, dict):
        return float(t["lat"]), float(t["lon"])
    return TARGETS[str(t).lower()]


def build_profile(cfg: dict[str, Any], target_id: str) -> dict[str, Any]:
    """Engine profile from the settings: only parameters with use = 1."""
    defs = {d["id"]: d for d in g.feature_definitions()}
    used = {fid: p for fid, p in cfg["parameters"].items() if p.get("use") == 1 and fid in defs}
    features = []
    for fid, p in used.items():
        item = {"feature_id": fid, "weight": p["weight"]}
        if defs[fid]["kind"] == "scalar":
            item["tau"], item["tau_unit"] = p["tau"], defs[fid]["canonical_unit"]
        features.append(item)
    dims = sorted({g.DIMENSION_OF[f] for f in used})
    dw = cfg.get("dimension_weights", {})
    switched_off = sorted(f for f, p in cfg["parameters"].items() if p.get("use") == 0)
    return {
        "id": "gui_config", "version": str(cfg.get("version", "1.0.0")), "target_id": target_id,
        "calibration_status": "provisional",
        "description": "Profile built from analysis_config.json (defaults = Science P1-P10 recommendation).",
        "dimension_weights": {d: dw.get(d, 1) for d in dims},
        "features": features, "required_features": [], "constraints": [],
        "declared_limitations": list(g.COMMON_LIMITATIONS)
        + ([f"Switched off in the settings: {', '.join(switched_off)}."] if switched_off else []),
    }


# ----------------------------------------------------------------- data
def passes_filter(r: dict, flt: dict[str, Any]) -> bool:
    """Earth candidate filter from the settings. Empty values pass."""
    if r.get("is_land") != "1.0":
        return False
    if not flt.get("use", 1):
        return True
    if r.get("rock_group", "") in set(flt.get("exclude_rock_groups", [])) | {""}:
        return False
    num = lambda k: g._num(r, k)  # noqa: E731
    checks = [("precipitation_mm_yr", "max_precipitation_mm_yr"), ("ndvi", "max_ndvi"),
              ("aridity_index", "max_aridity_index")]
    for col, key in checks:
        limit, value = flt.get(key), num(col)
        if limit is not None and value is not None and value >= limit:
            return False
    return True


def earth_sites(data_dir: Path, earth_file: str, flt: dict[str, Any]) -> list[dict]:
    earth = g.load_grid(data_dir / earth_file)
    ati = g._percentile_table(earth, land_only=True)
    return [g.cell_site("earth", earth, k, ati) for k, r in earth.items() if passes_filter(r, flt)]


def _cell_of(candidate_id: str) -> tuple[float, float]:
    la, lo = candidate_id.split("_")[1:]
    return float(la), float(lo)


def _sid(planet: str, lat: float, lon: float) -> str:
    return f"{planet}_{lat:+05.1f}_{lon:+06.1f}"


# ----------------------------------------------------------------- run
def run(cfg: dict[str, Any], data_dir: Path | str) -> dict[str, Any]:
    data_dir = Path(data_dir)
    cfg = copy.deepcopy(cfg)
    errors = validate(cfg)
    if errors:
        return {"ok": False, "errors": errors}

    mars = g.load_grid(data_dir / "mars_1deg.csv")
    lat, lon = target_cell(cfg)
    target = g.cell_site("mars", mars, (lat, lon), g._percentile_table(mars, land_only=False))
    profile = build_profile(cfg, target["id"])
    defs = g.feature_definitions()
    flt = cfg.get("earth_filter", {})
    sites = earth_sites(data_dir, cfg.get("earth_file", "earth_1deg.csv"), flt)
    result = rank(target, sites, profile, defs)

    ranking = []
    for e in result.ranked:
        r = e.result
        la, lo = _cell_of(r.candidate_id)
        ranking.append({
            "lat": la, "lon": lo, "position": e.position, "score_0_100": round(100 * r.score_observed, 2),
            "coverage": round(r.coverage, 3),
            "dimensions": {d.dimension: (None if d.score_observed is None else round(100 * d.score_observed, 2))
                           for d in r.dimensions},
        })
    not_ranked = [{"lat": _cell_of(r.candidate_id)[0], "lon": _cell_of(r.candidate_id)[1],
                   "category": r.category, "reasons": list(r.reasons)} for r in result.partial + result.excluded]
    pos = {(i["lat"], i["lon"]): i for i in ranking}
    watched = {name: pos.get((la, lo), {"lat": la, "lon": lo, "position": None, "note": "not ranked or filtered out"})
               for name, (la, lo) in cfg.get("watch", {}).items()}

    out = {
        "ok": True,
        "target": {"name": cfg.get("target"), "cell": [lat, lon],
                   "values": {m["feature_id"]: m["value"] for m in target["measurements"]}},
        "earth_file": cfg.get("earth_file", "earth_1deg.csv"),
        "profile": profile,
        "counts": {"candidates": len(sites), "ranked": len(result.ranked), "not_ranked": len(not_ranked)},
        "ranking": ranking,
        "not_ranked": not_ranked,
        "watched": watched,
        "timeline": None,
    }

    tl_cfg = cfg.get("timeline", {})
    if tl_cfg.get("use"):
        files = {int(tl_cfg.get("baseline_year", 1985)): cfg.get("earth_file", "earth_1deg.csv")}
        missing = []
        for year in tl_cfg.get("years", []):
            name = f"{tl_cfg.get('scenario', 'ssp245')}/earth_1deg_{year}.csv"
            (files.__setitem__(int(year), name) if (data_dir / name).exists() else missing.append(name))
        if len(files) >= 2:
            by_year = {y: earth_sites(data_dir, f, flt) for y, f in files.items()}
            watch_ids = [_sid("earth", la, lo) for la, lo in cfg.get("watch", {}).values()]
            tl = rank_over_years(target, by_year, profile, defs, watch=watch_ids, top_k=int(tl_cfg.get("top_k", 20)))
            out["timeline"] = {"scenario": tl_cfg.get("scenario"), "files": {str(y): f for y, f in files.items()},
                               "missing_files": missing, **json.loads(tl.to_json())}
        else:
            out["timeline"] = {"error": "no yearly files found", "missing_files": missing}
    return out


def main(data_dir: Path, config_path: Path | None) -> None:
    cfg = load_config(config_path)
    res = run(cfg, data_dir)
    if not res["ok"]:
        print("Settings problems:", *res["errors"], sep="\n  ")
        sys.exit(1)
    used = [f for f, p in cfg["parameters"].items() if p.get("use") == 1]
    print(f"Target {res['target']['name']} {res['target']['cell']}; parameters used: {', '.join(used)}")
    print(f"Earth candidates {res['counts']['candidates']}, ranked {res['counts']['ranked']}")
    for item in res["ranking"][:10]:
        print(f"  #{item['position']:<4d} ({item['lat']:+.1f}, {item['lon']:+.1f})  {item['score_0_100']:5.1f}")
    print("Watched sites:")
    for name, item in res["watched"].items():
        print(f"  {name:22s} #{item.get('position')}  score {item.get('score_0_100')}")
    if res["timeline"]:
        tl = res["timeline"]
        if "error" in tl:
            print("Timeline:", tl["error"], tl["missing_files"])
        else:
            print(f"Timeline {tl['scenario']} years {tl['years']}: emerging {len(tl['emerging'])}, fading {len(tl['fading'])}")
            for t in tl["watched"]:
                print(f"  {t['candidate_id']:22s} {t['status']:10s} change {t['change']}")

    (HERE / "output_config_ranking.json").write_text(json.dumps(res, allow_nan=False) + "\n", encoding="utf-8")
    dims = list(res["ranking"][0]["dimensions"]) if res["ranking"] else []
    with (HERE / "output_config_scores.csv").open("w", newline="", encoding="utf-8") as h:
        w = csv.writer(h)
        w.writerow(["lat", "lon", "position", "score_0_100", "coverage"] + [f"dim_{d}" for d in dims])
        for i in res["ranking"]:
            w.writerow([i["lat"], i["lon"], i["position"], i["score_0_100"], i["coverage"]] + [i["dimensions"][d] for d in dims])
    print("written output_config_ranking.json, output_config_scores.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
