"""presets_trained_11km.json from calibration_soft_11km.json: the accepted method with the largest gain per
mission, in the app's format (category weight = sum of its features' trained weights, feature weight = its weight)."""
import json
from pathlib import Path

HERE = Path(__file__).parent
R = json.loads((HERE / "calibration_soft_11km.json").read_text(encoding="utf-8"))
P = json.loads((HERE / "presets.json").read_text(encoding="utf-8"))
cat = {f["id"]: f["category"] for f in P["features"]}
out = {"note": "Mission weights trained on the 11 km grid (calibrate_soft.py): known analogs as 20 km areas, soft top-5 % target "
               "or shared-feature weighting, anchored to Science's weights and accepted by leave-one-out validation.", "presets": {}}
for pid, r in R.items():
    if r.get("chosen", "science") == "science":
        continue
    m = r["methods"][r["chosen"]]
    cw = {c["id"]: 0.0 for c in P["categories"]}
    fw = {f["id"]: 0.0 for f in P["features"]}
    for f, v in m["weights"].items():
        cw[cat[f]] += v
        fw[f] = v
    out["presets"][pid] = {
        "method": r["chosen"], "sites": len(r["sites_used"]),
        "validation": f"hidden known analogs: mean rank {m['mean_hidden_rank_start']} -> {m['mean_hidden_rank_trained']} "
                      f"({100 * m['gain']:+.1f}%), {m['improved']}/{m['of']} improved",
        "category_weights": {k: round(v, 6) for k, v in cw.items()},
        "feature_weights": {k: round(v, 6) for k, v in fw.items()}}
(HERE / "presets_trained_11km.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
for pid, p in out["presets"].items():
    print(pid, p["method"], p["validation"])
