"""
Planalogy - NASA Space Apps Challenge 2026

Module: Engine Service
Purpose: Connect the analogue engine (similarity model) to the app. Run a
mission preset on the Data team's 1-degree grid and return everything the
frontend needs in one JSON payload: ranked sites with site cards, a heat map
of every scored cell, map points, the calibration verdict, declared
limitations and, when yearly Earth files exist, the year slider.

Data: data/grid_1deg/ (earth_1deg.csv, mars_1deg.csv, parameters.csv).
Any other regular grid works the same way: put one earth_<name>.csv and one
mars_<name>.csv in a folder (e.g. data/grid_50km/earth_50km.csv with 0.45 deg
cells and mars_50km.csv with 0.84 deg cells) and pass --data <folder>. Cell
size is read from the files (backend/grid_data.py).
Yearly files for the slider: earth_<name>_<year>.csv next to earth_<name>.csv.

Command line:
    python -m backend.engine_service                  # all presets
    python -m backend.engine_service rover_navigation --top 20
    python -m backend.engine_service --data <folder> --years
Writes data/results/<preset>.json (and <preset>_years.json).
"""

from __future__ import annotations

import json
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from analogue_engine import calibrate_weights, explain, rank, rank_over_years, to_json

from backend import grid_data as g
from backend.analog_presets import CELLS, EARTH, PRESETS, analog_id, build_profile, target_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GRID_DIR = PROJECT_ROOT / "data" / "grid_1deg"
PROFILE_CACHE = PROJECT_ROOT / "data" / "preset_profiles.json"
RESULTS_DIR = PROJECT_ROOT / "data" / "results"


class DataNotFound(RuntimeError):
    """The grid files are not where the service expects them."""


# --------------------------------------------------------------------------- data


_BASE_FILE = re.compile(r"(earth|mars)_([^_]+)\.csv")


def grid_files(data_dir: Path) -> tuple[str, str]:
    """Names of the Earth and Mars grid files in a folder (earth_<name>.csv, mars_<name>.csv).

    earth_1deg.csv / mars_1deg.csv win if present; otherwise the folder must
    hold exactly one base file per planet (yearly files are not counted).
    """
    found: dict[str, list[str]] = {"earth": [], "mars": []}
    for p in sorted(data_dir.glob("*.csv")) if data_dir.is_dir() else []:
        m = _BASE_FILE.fullmatch(p.name)
        if m:
            found[m.group(1)].append(p.name)
    names = []
    for planet in ("earth", "mars"):
        files = found[planet]
        if f"{planet}_1deg.csv" in files:
            names.append(f"{planet}_1deg.csv")
        elif len(files) == 1:
            names.append(files[0])
        elif not files:
            raise DataNotFound(
                f"No {planet}_<grid>.csv found in {data_dir}. Put the Data team's grid in data/grid_1deg/ "
                "(branch data-grid-1deg) or pass --data <folder>."
            )
        else:
            raise DataNotFound(f"Several {planet} grids in {data_dir} ({files}); keep one per folder.")
    return names[0], names[1]


@lru_cache(maxsize=8)
def load_grid(data_dir: str, earth_file: str | None = None) -> dict[str, Any]:
    """Load and prepare the grid once per (folder, Earth file); about 3 s at 1 degree."""
    path = Path(data_dir)
    earth, mars = grid_files(path)
    return g.build(path, earth_file or earth, mars)


def yearly_files(data_dir: Path) -> list[tuple[int, str]]:
    """(year, file) for earth_<name>_<year>.csv files next to the base Earth file."""
    try:
        earth, _ = grid_files(data_dir)
    except DataNotFound:
        return []
    stem = earth[: -len(".csv")]
    found = []
    for p in data_dir.glob(f"{stem}_*.csv"):
        m = re.fullmatch(re.escape(stem) + r"_(\d{4})\.csv", p.name)
        if m:
            found.append((int(m.group(1)), p.name))
    return sorted(found)


# --------------------------------------------------------------------------- presets


def list_presets() -> list[dict[str, Any]]:
    """Metadata for the preset buttons."""
    return [
        {"id": p["id"], "name": p["name"], "mission": p["mission"], "target": p["target"],
         "target_point": dict(zip(("lat", "lon"), CELLS[p["target"]])), "why": p["why"],
         "known_analogs": p["known_analogs"]}
        for p in PRESETS
    ]


def _preset(preset_id: str) -> dict[str, Any]:
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    raise ValueError(f"Unknown preset '{preset_id}'. Available: {[p['id'] for p in PRESETS]}")


def _target(preset: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Engine Site of the Mars cell that contains the preset's target."""
    key = target_key(data, preset["target"])
    if key is None or key not in data["mars"]:
        raise DataNotFound(f"No Mars grid cell contains {preset['target']} {CELLS[preset['target']]}")
    return g.cell_site("mars", data["mars"], key, data["mars_ati"], spec=data["mars_spec"], support=data["support"])


def preset_profile(
    preset_id: str,
    data_dir: Path = GRID_DIR,
    *,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Profile to use for a preset, plus calibration info.

    Calibration (about 20 s) is cached in data/preset_profiles.json. The
    calibrated weights are used only if they pass the engine's validation gate
    (hidden known analogs must improve); otherwise Science's weights are used.
    """
    preset = _preset(preset_id)
    data = load_grid(str(data_dir))
    start = build_profile(preset, data)
    if not calibrate:
        return start, {"weights_used": "science (start)", "verdict": "not_run", "verdict_reason": "calibration off"}

    cache: dict[str, Any] = {}
    if cache_file is not None and cache_file.exists() and not refresh:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        hit = cache.get(preset_id)
        # entries written before the grid was recorded come from the 1-degree grid
        if (hit and hit.get("start_version") == start["version"]
                and hit.get("grid", g.SUPPORT) == data["support"]):
            return hit["profile"], hit["info"]

    target = _target(preset, data)
    ids = {s["id"] for s in data["earth_sites"]}
    known = [analog_id(data, n) for n in preset["known_analogs"]]
    present = [k for k in known if k in ids]
    if not present:
        info = {"weights_used": "science (start)", "verdict": "not_validated",
                "verdict_reason": "none of the known analogs are among the candidate cells"}
        return start, info
    cal = calibrate_weights(target, data["earth_sites"], start, g.feature_definitions(), present)
    names = {analog_id(data, k): k for k in EARTH}
    info = {
        "weights_used": "calibrated" if cal.verdict == "accepted" else "science (start)",
        "verdict": cal.verdict, "verdict_reason": cal.verdict_reason,
        "start_category_weights": cal.start_dimension_weights,
        "calibrated_category_weights": cal.calibrated_dimension_weights,
        "known_analog_ranks_start": {names.get(c, c): r for c, r in cal.start_summary.ranks.items()},
        "known_analog_ranks_calibrated": {names.get(c, c): r for c, r in cal.calibrated_summary.ranks.items()},
        "leave_one_out": [{"held_out": names.get(r.held_out, r.held_out), "start": r.rank_with_start_weights,
                           "calibrated_without_it": r.rank_with_calibrated_weights} for r in cal.leave_one_out],
        "warnings": list(cal.warnings),
    }
    profile = cal.recommended_profile
    if cache_file is not None:
        cache[preset_id] = {"start_version": start["version"], "grid": data["support"], "profile": profile, "info": info}
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(to_json(cache) + "\n", encoding="utf-8")
    return profile, info


# --------------------------------------------------------------------------- runs


def _latlon(cid: str) -> tuple[float, float]:
    _, la, lo = cid.split("_")
    return float(la), float(lo)


def run_preset(
    preset_id: str,
    *,
    data_dir: Path = GRID_DIR,
    top_n: int = 20,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
) -> dict[str, Any]:
    """Rank all dry, bare Earth cells for one mission preset."""
    preset = _preset(preset_id)
    data = load_grid(str(data_dir))
    target = _target(preset, data)
    profile, info = preset_profile(preset_id, data_dir, calibrate=calibrate, cache_file=cache_file)
    result = rank(target, data["earth_sites"], profile, g.feature_definitions())
    known = {analog_id(data, k): k for k in EARTH}

    sites = []
    for e in result.ranked[:top_n]:
        card = explain(e.result)
        lat, lon = _latlon(e.result.candidate_id)
        card.update({"position": e.position, "lat": lat, "lon": lon, "known_analog": known.get(e.result.candidate_id)})
        sites.append(card)

    heatmap = [[*_latlon(e.result.candidate_id), round(100 * e.result.score_observed, 1)] for e in result.ranked]
    map_points = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": {"type": "Point", "coordinates": [s["lon"], s["lat"]]},
             "properties": {"position": s["position"], "score": s["score_0_100"], "headline": s["headline"],
                            "known_analog": s["known_analog"]}}
            for s in sites
        ],
    }
    lat, lon = target_key(data, preset["target"])
    pt_lat, pt_lon = CELLS[preset["target"]]
    espec = data["earth_spec"]
    return {
        "project": "Planalogy",
        "preset": {k: preset[k] for k in ("id", "name", "mission", "why")},
        "target": {"name": preset["target"], "body": "Mars", "lat": lat, "lon": lon,
                   "point": {"lat": pt_lat, "lon": pt_lon}},
        "grid": {"earth": espec.as_dict(), "mars": data["mars_spec"].as_dict(), "spatial_support": data["support"]},
        "calibration": info,
        "profile_used": profile,
        "counts": {"ranked": len(result.ranked), "partial": len(result.partial), "excluded": len(result.excluded)},
        "sites": sites,
        "heatmap": {"columns": ["lat", "lon", "score_0_100"], "cell_size_deg": espec.lat_step,
                    "cell_size_lon_deg": espec.lon_step, "rows": heatmap},
        "map_data": map_points,
        "declared_limitations": list(result.declared_limitations),
        "warnings": list(result.warnings),
        "data_mode": result.data_mode,
        "model": f"{result.model_id}@{result.model_version}",
        "validation_status": "Preliminary - requires validation",
    }


def run_preset_over_years(
    preset_id: str,
    *,
    data_dir: Path = GRID_DIR,
    top_k: int = 20,
    calibrate: bool = True,
    cache_file: Path | None = PROFILE_CACHE,
) -> dict[str, Any]:
    """Year slider: same preset and profile against each yearly Earth file."""
    years = yearly_files(data_dir)
    if len(years) < 2:
        return {"preset": preset_id, "years": [y for y, _ in years],
                "message": "Put at least two earth_<grid>_<year>.csv files in the data folder to use the year slider."}
    preset = _preset(preset_id)
    profile, info = preset_profile(preset_id, data_dir, calibrate=calibrate, cache_file=cache_file)
    base = load_grid(str(data_dir))
    target = _target(preset, base)
    sites_by_year = {y: load_grid(str(data_dir), f)["earth_sites"] for y, f in years}
    watch = [analog_id(base, n) for n in preset["known_analogs"]]
    tl = rank_over_years(target, sites_by_year, profile, g.feature_definitions(), watch=watch, top_k=top_k)
    out = json.loads(tl.to_json())
    out["preset"] = preset_id
    out["calibration"] = info
    return out


def export(payload: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(payload) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- CLI


def main(argv: list[str]) -> None:
    args = list(argv)
    data_dir = GRID_DIR
    top_n = 20
    if "--data" in args:
        i = args.index("--data")
        data_dir = Path(args[i + 1])
        del args[i:i + 2]
    if "--top" in args:
        i = args.index("--top")
        top_n = int(args[i + 1])
        del args[i:i + 2]
    with_years = "--years" in args
    no_cal = "--no-calibration" in args
    ids = [a for a in args if not a.startswith("--")] or [p["id"] for p in PRESETS]

    for pid in ids:
        t0 = time.time()
        payload = run_preset(pid, data_dir=data_dir, top_n=top_n, calibrate=not no_cal)
        path = export(payload, RESULTS_DIR / f"{pid}.json")
        best = payload["sites"][0] if payload["sites"] else None
        print(f"{pid}: {payload['counts']['ranked']} ranked, weights {payload['calibration']['weights_used']}, "
              f"#1 {best['lat']:+.1f},{best['lon']:+.1f} score {best['score_0_100']} ({time.time() - t0:.0f}s) -> {path.name}")
        if with_years:
            yp = export(run_preset_over_years(pid, data_dir=data_dir, calibrate=not no_cal),
                        RESULTS_DIR / f"{pid}_years.json")
            print(f"  years -> {yp.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
