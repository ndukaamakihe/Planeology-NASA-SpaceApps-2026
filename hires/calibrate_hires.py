"""Train (calibrate) the mission profiles on the 11 km grid.

Same method as analogue_engine.calibration.calibrate_weights, vectorised with numpy so it runs on all
~259,000 dry cells (the engine's pure-Python loop over pairs would take hours):

  * complete candidates under the starting profile score S_i(w) = sum_j w_j s_ij (w on the simplex);
  * loss = mean over (known p, other n) of softplus(-(S_p - S_n) / T) + lambda * KL(w || w0);
  * exponentiated-gradient (proximal mirror) steps with the KL anchor solved exactly, T = 0.05,
    lambda = 1, step 0.05, 400 iterations (the engine's defaults);
  * validation gate: leave-one-out. Each known analog is hidden in turn, the weights are re-tuned on the
    others, and the hidden site's rank is compared with its rank under the starting weights. The weights
    are accepted only if the mean hidden rank improves by >= 5 % and at least half the hidden sites improve.

The starting weights are Science's (science_presets.json). Two label sets per mission:
  science   the preset's known analogs (Science documents)
  extended  those plus catalogued sites (known_analogs.json) of the matching kind; see LABELS below.
Only labels that fall in a dry, complete cell are used.

usage: python -I calibrate_hires.py [preset ...]   -> calibration_11km.json, presets_11km.json
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import expit

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import planalogy_hires as H  # noqa: E402
from hires_common import cell_of  # noqa: E402

SCI = json.loads((HERE / "science_presets.json").read_text(encoding="utf-8"))
T, LAM, STEP, ITERS, MIN_GAIN = 0.05, 1.0, 0.05, 400, 0.05


def catalog_labels(pid):
    """Catalogued known analogs used as extra labels for a mission (kind / description rules)."""
    K = json.loads(H.KNOWN.read_text(encoding="utf-8"))
    out = []
    for k in K:
        kind, txt = k.get("kind", ""), (k.get("analog_for", "") + " " + k.get("name", "")).lower()
        if pid == "rover_navigation" and (kind in ("field_test", "station") or re.search(r"rover|eva\b", txt)):
            out.append(k)
        elif pid == "sample_science" and (kind == "evaporite" or re.search(r"paleolake|delta|lacustrine|clay", txt)):
            out.append(k)
        elif pid == "thermal_environment" and (re.search(r"hyper-?arid|high-altitude|thermal|polar desert|dry valley", txt)):
            out.append(k)
        elif pid == "ice_prospecting" and (kind == "polar" or re.search(r"permafrost|ground ice|ice-rich", txt)):
            out.append(k)
    return out


def optimise(P, N, w0):
    w = w0.copy()
    lw0 = np.log(w0)
    n_pairs = len(P) * len(N)
    for _ in range(ITERS):
        sp, sn = P @ w, N @ w
        M = expit(-(sp[:, None] - sn[None, :]) / T) / T
        grad = (-(M.sum(1) @ P) + (M.sum(0) @ N)) / n_pairs
        logits = (np.log(w) - STEP * grad + STEP * LAM * lw0) / (1 + STEP * LAM)
        e = np.exp(logits - logits.max())
        w = e / e.sum()
    return w


def positions(S, w):
    sc = S @ w
    order = np.argsort(-np.round(sc, 12), kind="stable")
    pos = np.empty(len(sc), np.int64)
    pos[order] = np.arange(1, len(sc) + 1)
    return pos


def train(pid, labels_mode):
    sp = next(p for p in SCI["presets"] if p["id"] == pid)
    preset = {"id": pid, "category_weights": sp["dimension_weights"], "feature_weights": sp["feature_weights"],
              "requirements": [{"feature": r["feature_id"], "equals": r["value"]} for r in sp.get("requirements", [])]}
    run = H.Run.__new__(H.Run)
    tp = H.TARGET_POINTS[next(p for p in H.manifest()["presets"] if p["id"] == pid)["target"]]
    run.p, run.label, run.tv, run.c = preset, tp[2], H.target_values(tp[0], tp[1]), {}
    Y = run.year("now")
    w_eff = H.effective_weights(preset["category_weights"], preset["feature_weights"])
    tunable = [f for f, v in w_eff.items() if v > 0]
    cand = np.nonzero(Y["pool"] & np.isfinite(Y["score"]))[0]
    sims = H.score(preset, run.tv, Y["cl"])[1]
    S = np.column_stack([sims[f][cand] for f in tunable])
    w0 = np.array([w_eff[f] for f in tunable])
    w0 = w0 / w0.sum()
    where = {int(c): j for j, c in enumerate(cand)}
    idx = np.load(H.TAB / "index2d.npy", mmap_mode="r")

    labels = [{"name": n, "lat": la, "lon": lo, "source": "science"} for n, (la, lo) in SCI["known_points"].items() if n in sp["known_analogs"]]
    if labels_mode == "extended":
        labels += [{"name": k["name"], "lat": k["lat"], "lon": k["lon"], "source": "catalog"} for k in catalog_labels(pid)]
    used, unusable, seen = [], [], set()
    for lb in labels:
        r, c = cell_of("earth", lb["lat"], lb["lon"])
        i = int(idx[r, c])
        j = where.get(i)
        if j is None:
            unusable.append(lb["name"])
        elif j not in seen:
            seen.add(j)
            used.append((lb["name"], j))
    out = {"preset": pid, "labels": labels_mode, "candidates": int(len(cand)), "tunable": tunable,
           "used": [u[0] for u in used], "unusable": unusable}
    if len(used) < 2:
        out.update(verdict="not_validated", reason="fewer than 2 usable known analogs", start_weights=dict(zip(tunable, w0.round(4))))
        return out, None
    pidx = np.array([j for _, j in used])
    mask = np.ones(len(cand), bool)
    mask[pidx] = False
    t0 = time.time()
    w = optimise(S[pidx], S[mask], w0)
    pos0, pos1 = positions(S, w0), positions(S, w)
    loo = []
    for name, j in used:
        others = np.array([k for _, k in used if k != j])
        m2 = np.ones(len(cand), bool)
        m2[others] = False
        wh = optimise(S[others], S[m2], w0)
        loo.append({"held_out": name, "start": int(pos0[j]), "calibrated_without_it": int(positions(S, wh)[j])})
    before = np.mean([x["start"] for x in loo])
    after = np.mean([x["calibrated_without_it"] for x in loo])
    improved = sum(x["calibrated_without_it"] < x["start"] for x in loo)
    gain = (before - after) / before if before > 0 else 0.0
    ok = gain >= MIN_GAIN and improved * 2 >= len(loo)
    dims = {f: next(x["category"] for x in H.manifest()["features"] if x["id"] == f) for f in tunable}
    dimw = lambda ww: {d: round(float(sum(v for f, v in zip(tunable, ww) if dims[f] == d)), 4) for d in sorted(set(dims.values()))}
    out.update({
        "verdict": "accepted" if ok else "rejected",
        "reason": f"hidden analogs: mean rank {before:.0f} -> {after:.0f} ({100 * gain:+.1f}%), {improved}/{len(loo)} improved; "
                  f"threshold {100 * MIN_GAIN:.0f}% and half improved",
        "start_weights": dict(zip(tunable, w0.round(4).tolist())), "calibrated_weights": dict(zip(tunable, w.round(4).tolist())),
        "start_dimension_weights": dimw(w0), "calibrated_dimension_weights": dimw(w),
        "ranks_start": {n: int(pos0[j]) for n, j in used}, "ranks_calibrated": {n: int(pos1[j]) for n, j in used},
        "mean_top_percent_start": round(float(np.mean([pos0[j] for _, j in used]) / len(cand) * 100), 2),
        "mean_top_percent_calibrated": round(float(np.mean([pos1[j] for _, j in used]) / len(cand) * 100), 2),
        "leave_one_out": loo, "seconds": round(time.time() - t0)})
    # profile in the app's format: category weight = sum of its features' weights, feature weight = its weight
    prof = {"id": pid, "category_weights": {c["id"]: 0.0 for c in H.manifest()["categories"]},
            "feature_weights": {f["id"]: 0.0 for f in H.manifest()["features"]}}
    for f, v in zip(tunable, w):
        prof["category_weights"][dims[f]] += float(v)
        prof["feature_weights"][f] = float(v)
    prof["category_weights"] = {k: round(v, 6) for k, v in prof["category_weights"].items()}
    prof["feature_weights"] = {k: round(v, 6) for k, v in prof["feature_weights"].items()}
    return out, prof


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pids = sys.argv[1:] or [p["id"] for p in SCI["presets"]]
    report, profiles = {}, {}
    rp = HERE / "calibration_11km.json"
    if rp.exists():
        report = json.loads(rp.read_text(encoding="utf-8"))
    for pid in pids:
        for mode in ("science", "extended"):
            out, prof = train(pid, mode)
            report[f"{pid}/{mode}"] = out
            print(pid, mode, out["verdict"], "|", out.get("reason"), "| used", len(out["used"]), "unusable", len(out["unusable"]), flush=True)
            if prof is not None:
                profiles[f"{pid}/{mode}"] = prof
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    pp = HERE / "calibrated_profiles_11km.json"
    old = json.loads(pp.read_text(encoding="utf-8")) if pp.exists() else {}
    old.update(profiles)
    pp.write_text(json.dumps(old, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
