"""Page data for the Analog Atlas: the auditor's finalists and verified known losers, with every number
recomputed by the tool (score, rank, dry status per scenario), plus layer metadata, the known-analog
catalog, validation figures and method notes.

usage: python -I build_atlas.py <audit.json> <layers.json> <out atlas.json>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np  # noqa: E402

import planalogy_hires as H  # noqa: E402
from hires_common import cell_of  # noqa: E402

audit = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
layers = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
idx = np.load(H.TAB / "index2d.npy", mmap_mode="r")
MARS_POINTS = {"oxia": (18.16, -24.33), "deuteronilus": (43.9, 24.4), "phlegra": (40.0, 165.0), "erebus": (36.0, -170.0)}
LABEL = {"rover_navigation": "Rover navigation (Gale)", "sample_science": "Sample science (Jezero)",
         "thermal_environment": "Thermal testing (Gale)", "ice_prospecting": "Ground-ice ISRU (Arcadia)"}
runs = {}


def run_for(preset, mars_target):
    mp = None
    t = (mars_target or "").lower()
    for k, v in MARS_POINTS.items():
        if k in t:
            mp = v
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)", t)
    if mp is None and m and "mars" in t:
        mp = (float(m.group(1)), float(m.group(2)))
    key = (preset, mp)
    if key not in runs:
        runs[key] = H.Run(preset, mp)
    return runs[key], mp


def numbers(preset, lat, lon, mars_target=None):
    run, mp = run_for(preset, mars_target)
    r, c = cell_of("earth", lat, lon)
    i = int(idx[r, c])
    if i < 0:
        return None
    d = run.describe(i)
    label = LABEL.get(preset, preset)
    if mp is not None:
        label = label.split(" (")[0] + f" (Mars point {mp[0]}, {mp[1]})"
    return {"score_today": d["score_today"], "rank_today": d["rank_today"], "of_today": d["of_today"],
            "trajectory": d["trajectory"], "nearest_known_analog": d["nearest_known_analog"],
            "mission_label": label, "mars_target_label": run.label}


def text(x):
    if x is None:
        return None
    if isinstance(x, list):
        return " ".join(text(v) for v in x if v)
    if isinstance(x, dict):
        return "; ".join(f"{k}: {text(v)}" for k, v in x.items() if v)
    return str(x)


fins = []
for f in audit.get("finalists", []):
    n = numbers(f["preset"], float(f["lat"]), float(f["lon"]), f.get("mars_target"))
    if n is None:
        continue
    fins.append({
        "name": f["name"], "lat": float(f["lat"]), "lon": float(f["lon"]), "country": f.get("country"),
        "preset": f["preset"], "mars_target": n["mars_target_label"], "mission_label": n["mission_label"],
        "score_today": n["score_today"], "rank_today": n["rank_today"], "of_today": n["of_today"],
        "trajectory": n["trajectory"], "nearest_known_analog": n["nearest_known_analog"],
        "what_is_there": text(f.get("what_is_there")), "mission_value": text(f.get("mission_value")),
        "climate_story": text(f.get("climate_story")), "novelty_evidence": text(f.get("novelty_evidence")),
        "caveats": text(f.get("caveats")), "verdict": text(f.get("verdict")), "confidence": f.get("confidence"),
        "sources": [s for s in (f.get("sources") or []) if isinstance(s, str) and s.startswith("http")],
    })

def mechanism(tr):
    """Plain-language reason a site stops counting, from its numbers."""
    now = tr["now"]
    for k, label in (("ssp245_2050", "2050, moderate"), ("ssp585_2050", "2050, high emissions"),
                     ("ssp245_2090", "2090, moderate"), ("ssp585_2090", "2090, high emissions")):
        t = tr[k]
        if now["dry"] and not t["dry"]:
            bits = []
            if now["T_mean_C"] is not None and t["T_mean_C"] is not None and now["T_mean_C"] < 0 <= t["T_mean_C"]:
                bits.append(f"mean air temperature {now['T_mean_C']:+.1f} °C → {t['T_mean_C']:+.1f} °C, past 0 °C")
            if now["precip_mm"] is not None and t["precip_mm"] is not None and now["precip_mm"] < 250 <= t["precip_mm"]:
                bits.append(f"precipitation {now['precip_mm']:.0f} → {t['precip_mm']:.0f} mm, past 250 mm")
            if now["aridity"] is not None and t["aridity"] is not None and now["aridity"] <= 0.2 < t["aridity"]:
                bits.append(f"aridity {now['aridity']:.3f} → {t['aridity']:.3f}, past 0.20")
            return f"First lost in {label}: " + ("; ".join(bits) if bits else "no longer meets the dry-land rule") + "."
    return ""


KNOWN_LOSERS = [  # catalogued analogs that the corrected 11 km tool shows losing dry-land status
    ("Kara-Kul crater, Pamir (Tajikistan)", 39.0, 73.4, "rover_navigation"),
    ("Tso Moriri, Ladakh (India)", 32.9, 78.3, "thermal_environment"),
    ("Tso Kar, Ladakh (India), region of ISRO's HOPE station", 33.3, 78.0, "rover_navigation"),
]
losers = []
for name, lat, lon, preset in KNOWN_LOSERS:
    n = numbers(preset, lat, lon)
    if n is None:
        continue
    losers.append({"name": name, "where": f"{lat:.2f}°, {lon:.2f}°", "mission": LABEL[preset],
                   "trajectory": n["trajectory"], "mechanism": mechanism(n["trajectory"])})

SIGNAL = [  # top ice-prospecting cells (trained weights, >50 km from catalogued analogs); regional signal
    ("Ashikule volcanic basin, West Kunlun (finalist)", 35.75, 81.65),
    ("Northern Tibetan Plateau", 36.25, 88.85),
    ("Northern Tibetan Plateau", 34.85, 89.15),
    ("North Baffin Island (Nunavut)", 70.25, -84.75),
    ("Mongolian Altai foreland", 46.65, 99.75),
]
signal = []
for name, lat, lon in SIGNAL:
    n = numbers("ice_prospecting", lat, lon)
    if n is None:
        continue
    signal.append({"name": name, "where": f"{lat:.2f}°, {lon:.2f}°", "mission": LABEL["ice_prospecting"],
                   "trajectory": n["trajectory"], "mechanism": mechanism(n["trajectory"]) or "Stays a cold desert through 2090 in both scenarios."})

known = json.loads(H.KNOWN.read_text(encoding="utf-8"))
land_cells = int((idx >= 0).sum())
atlas = {
    "layers": layers,
    "finalists": fins,
    "finalists_intro": ("Ten agents proposed 42 candidates; three audit rounds re-ran the engine on every candidate, checked "
                        "neighbouring cells and searched the literature in several languages. The last round used 11 km rock type, "
                        "ground ice, craters and re-trained weights. Four sites hold, one per mission, plus the clearest climate gain "
                        "and the clearest climate loss. None is a sure thing; each card shows its caveats."),
    "known_losers": losers,
    "known_losers_intro": "Sites already used as Mars analogs, checked with the same 11 km grid. Ranks are among dry cells for that "
                          "mission; 'not dry' means the site no longer meets Science's dry-land rule that year.",
    "known": [{"name": k["name"], "lat": k["lat"], "lon": k["lon"]} for k in known],
    "candidates": [{"name": f["name"], "scout": "", "status": "finalist", "reason": text(f.get("verdict"))} for f in audit.get("finalists", [])]
                  + [{"name": r.get("name"), "scout": r.get("scout", ""), "status": "rejected", "reason": text(r.get("reason"))}
                     for r in audit.get("rejected", [])],
    "signal": signal,
    "signal_intro": ("With ground ice required (Obu 2019 permafrost at 1 km) and the trained weights, the best Earth analogs for "
                     "Arcadia Planitia are high cold deserts on permafrost in the Kunlun and northern Tibet, plus Arctic Canada. "
                     "They count as Mars-like only as cold deserts. The engine keeps permafrost as today in future years, so a thaw "
                     "of the ground itself is not modelled; the table shows when each site stops meeting the cold-desert rule."),
    "stats": [[f"{land_cells/1e6:.2f} M", "Earth land cells at 11 km"], [f"{land_cells/25628:.0f}×", "more cells than the 1° grid"],
              [f"{layers['dry_now']:,}", "cells count as Mars-like dry land today"], ["10 + 3", "search agents and audit rounds"], ["4", "mission profiles trained at 11 km"],
              [str(len(fins)), "audited finalists"]],
    "method": [
        {"title": "Data at 11 km", "items": [
            "Earth 0.1° cells, Mars 0.1875° cells: about 11 km on both planets.",
            "Terrain from WorldClim 2.1 30″ elevation (Earth) and the MOLA 463 m DEM averaged to 926 m (Mars): mean slope, roughness and relief inside each cell.",
            "Air temperature, rainfall and aridity (P / Hargreaves PET) from WorldClim 2.1 2.5′ monthly normals, 1970-2000.",
            "Ground day-night temperature from MODIS MOD11A2 1 km medians 2000-2017 (OpenLandMap); 1° values south of 62° S.",
            "Albedo from the MODIS blue-sky climatology at 0.05° (60° S-60° N); NDVI from 5 km MODIS/AVHRR 2019, gaps filled from neighbours; Natural Earth lakes masked out.",
            "Mars albedo from the TES mosaic; Mars temperatures from the Data team's 1° grid (the climate model is ~200 km).",
            "Rock type and mineral proxy from the GLiM vector map (1.2 M polygons); Earth ground ice from Obu 2019 permafrost at 1 km (Northern Hemisphere).",
            "Mars geology from the SIM 3292 vector map; Mars craters from Robbins & Hynek 2012 (384,343 craters, inside a rim); Mars ice from Odyssey GRS plus polar units.",
            "TES thermal inertia is mapped but not scored: Earth has no physical thermal-inertia map, so both planets use the same apparent thermal inertia, (1 - albedo) / day-night swing."]},
        {"title": "Checked against the 1° grid", "items": [
            "Aggregated back to 1°, the new layers match the Data team's grid: air temperature and swing r = 1.000, rainfall r = 0.999, aridity r = 0.999 (dry class agrees on 99.97 % of cells).",
            "Ground swing r = 0.998, coldest night r = 1.000, NDVI r = 0.96 (rescaled to the 1° scale), albedo r = 0.955 between 60° S and 60° N.",
            "Rock group agrees with the 1° grid on 92.5 % of land cells (Earth) and 96.9 % (Mars); permafrost r = 0.936.",
            "Terrain is scale dependent: at 11 km the similarity scales for slope, roughness and relief are rescaled by the measured ratio on both planets (provisional)."]},
        {"title": "Same engine, same rules", "items": [
            "Adapted Gower similarity with the app's mission profiles and weights.",
            "Mars targets are the rovers' landing sites (Bradbury in Gale, Octavia E. Butler in Jezero) and Arcadia Planitia for ice.",
            "Dry land is Science's rule: NDVI below 0.2, not ice or water, and aridity 0.20 or less or a cold desert (below 0 °C, under 250 mm).",
            "Future years apply the CMIP6 changes from the Data team's projections (SSP2-4.5, SSP5-8.5) to the 11 km climate; vegetation stays as today."]},
        {"title": "Mission profiles trained at 11 km", "items": [
            "Weights were re-trained on known analogs: Science's sites plus catalogued sites of the matching kind (rover test sites, evaporite basins, high or hyper-arid deserts, polar sites).",
            "A known site is a 20 km area, and it only has to reach the top 5 % of cells (a soft target), not beat every cell.",
            "Training stays anchored to Science's weights and is accepted only if hidden known sites improve in leave-one-out validation: rover +8 % (19 sites), samples +33 % (32), thermal +26 % (17), ice +29 % (6).",
            "The 11 km rock, ice and crater layers alone already rank the known analogs higher under Science's weights, before any training.",
            "Large shifts for Science to review: sample science nearly drops rock type (the evaporite-basin labels are classed as evaporites, Jezero as sedimentary), ice relies on the coldest ground temperature and rock type."]},
        {"title": "Search and audit", "items": [
            "Ten agents each searched one slice (rover, samples and thermal by continent; ice for crewed missions; ESA's Oxia Planum; climate gains; climate losses).",
            "Each kept 3-5 candidates after web searches for prior Mars-analog use and checks of what is actually in the cell; candidates within 50 km of 245 catalogued analogs were dropped.",
            "An auditor re-ran 29 candidate cells (all reproduced), checked neighbours and local-language literature and rejected 28. A second audit re-checked about 30 cells under the trained weights and rejected 20 more.",
            "The audit found a gap-handling bug (cells without NDVI counted as bare ground). It is fixed: every number on this page comes from the corrected run."]},
        {"title": "Limits", "items": [
            "Rock type, minerals and ground ice come from 1° data, so they do not vary inside a 110 km block.",
            "Ranks change a lot from one cell to the next: read a finalist as the peak of a good area, not a unique spot.",
            "The catalog of known analogs was compiled by an agent and is incomplete; novelty means no prior Mars-analog use was found, not proven absent.",
            "No field visit or imagery check has been made yet."]},
    ],
    "footer": ["Planalogy, NASA Space Apps Challenge 2026. Data: WorldClim 2.1, MODIS (OpenLandMap; Zenodo 1435938, 6350821, 4305975), MOLA and TES (USGS Astrogeology), Natural Earth, Data team 1° grid and CMIP6 projections.",
               "Search agents and auditor ran on Claude; every figure was recomputed with the local 11 km tool (hires_tool/planalogy_hires.py)."],
}
Path(sys.argv[3]).parent.mkdir(parents=True, exist_ok=True)
Path(sys.argv[3]).write_text(json.dumps(atlas, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(fins), "finalists,", len(losers), "known losers")
