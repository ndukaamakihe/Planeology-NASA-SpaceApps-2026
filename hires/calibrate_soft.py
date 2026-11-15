"""Softer training of the mission profiles on the 11 km grid ("look alike", not "rank first").

Known analogs were chosen for many reasons (access, one special feature, history), so asking each one to
beat all ~259,000 dry cells is too strict and the point may fall in an unrepresentative 11 km cell.
Three changes against calibrate_hires.py:

  1. A site is an AREA: every complete dry cell within RADIUS_KM of the site's point (a bag of cells).
     The site's score is a soft maximum over its cells (the best place for a campaign there).
  2. SOFT TARGET: a site only has to be among the good cells. Loss per site =
     softplus((q - s_site) / T), where q is the score of the top-TOP_FRACTION cell under the current weights.
  3. SHARED FEATURES ("what the analogs have in common with Mars"): a second, closed-form method.
     For each feature, z = (mean similarity of the sites - mean over all candidates) / (spread among the
     sites + 0.1); weights w ∝ w0 · exp(BETA · z). Features on which the known analogs consistently look
     like the Mars target gain weight; features on which they disagree lose it.

Both are anchored to Science's weights (KL(w || w0) with lambda = 1 for method 1; BETA keeps method 2 close),
and both pass the same leave-one-out gate as the engine: hide each site, train on the others, compare the
hidden site's rank (its best cell) with its rank under Science's weights; accept if the mean hidden rank
improves by >= 5 % and at least half of the hidden sites improve. Labels: Science's known analogs plus the
catalogued sites of the matching kind (calibrate_hires.catalog_labels).

usage: python -I calibrate_soft.py [preset ...]   -> calibration_soft_11km.json (+ profiles)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import expit, softmax

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import planalogy_hires as H  # noqa: E402
from calibrate_hires import SCI, catalog_labels  # noqa: E402

RADIUS_KM, TOP_FRACTION, T, LAM, STEP, ITERS, MIN_GAIN, BETA, BAG_T = 20.0, 0.05, 0.05, 1.0, 0.05, 300, 0.05, 1.0, 0.02


def setup(pid):
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
    w0 = np.array([w_eff[f] for f in tunable]); w0 /= w0.sum()
    lat, lon = np.asarray(H.static()["lat"])[cand], np.asarray(H.static()["lon"])[cand]
    labels = [{"name": n, "lat": la, "lon": lo, "source": "science"} for n, (la, lo) in SCI["known_points"].items() if n in sp["known_analogs"]]
    labels += [{"name": k["name"], "lat": k["lat"], "lon": k["lon"], "source": "catalog"} for k in catalog_labels(pid)]
    bags, used, unusable = [], [], []
    for lb in labels:
        near = np.nonzero((np.abs(lat - lb["lat"]) < 0.3) & (np.abs(((lon - lb["lon"] + 180) % 360) - 180) < 0.6))[0]
        near = near[H.hav_km(lb["lat"], lb["lon"], lat[near], lon[near]) <= RADIUS_KM]
        if len(near) == 0:
            unusable.append(lb["name"])
            continue
        key = tuple(sorted(near.tolist()))
        if any(key == tuple(sorted(b.tolist())) for b in bags):
            continue
        bags.append(near); used.append(lb["name"])
    return dict(preset=preset, run=run, tunable=tunable, cand=cand, S=S, w0=w0, bags=bags, used=used, unusable=unusable)


def site_rank(S, w, bag):
    sc = S @ w
    best = sc[bag].max()
    return int((sc > best).sum() + 1)


def soft_optimise(S, bags, w0):
    """Method 1: soft top-fraction loss on soft-max site scores + lambda * KL(w || w0)."""
    w, lw0 = w0.copy(), np.log(w0)
    k_top = max(1, int(len(S) * TOP_FRACTION))
    for _ in range(ITERS):
        sc = S @ w
        qi = np.argpartition(-sc, k_top)[k_top]
        q, gq = sc[qi], S[qi]
        grad = np.zeros_like(w)
        for bag in bags:
            a = softmax(sc[bag] / BAG_T)
            s_site = BAG_T * np.log(np.exp((sc[bag] - sc[bag].max()) / BAG_T).sum()) + sc[bag].max()
            g_site = a @ S[bag]
            c = expit((q - s_site) / T) / T
            grad += c * (gq - g_site)
        grad /= len(bags)
        logits = (np.log(w) - STEP * grad + STEP * LAM * lw0) / (1 + STEP * LAM)
        e = np.exp(logits - logits.max()); w = e / e.sum()
    return w


def shared_features(S, bags, w0):
    """Method 2: weight features by how consistently the known sites look like the Mars target."""
    best = [bag[np.argmax(S[bag] @ w0)] for bag in bags]
    P = S[best]
    z = (P.mean(0) - S.mean(0)) / (P.std(0) + 0.1)
    w = w0 * np.exp(BETA * z)
    return w / w.sum(), z


def validate(S, bags, w0, fit):
    loo = []
    for h in range(len(bags)):
        others = [b for j, b in enumerate(bags) if j != h]
        w = fit(S, others, w0)
        w = w[0] if isinstance(w, tuple) else w
        loo.append((site_rank(S, w0, bags[h]), site_rank(S, w, bags[h])))
    before, after = np.mean([a for a, _ in loo]), np.mean([b for _, b in loo])
    improved = sum(b < a for a, b in loo)
    gain = (before - after) / before if before > 0 else 0.0
    ok = gain >= MIN_GAIN and improved * 2 >= len(loo)
    return ok, gain, improved, loo, before, after


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pids = sys.argv[1:] or [p["id"] for p in SCI["presets"]]
    rp = HERE / "calibration_soft_11km.json"
    report = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    for pid in pids:
        t0 = time.time()
        d = setup(pid)
        S, w0, bags, tun = d["S"], d["w0"], d["bags"], d["tunable"]
        out = {"preset": pid, "candidates": int(len(S)), "sites_used": d["used"], "sites_unusable": d["unusable"],
               "start_weights": dict(zip(tun, w0.round(4).tolist()))}
        if len(bags) < 2:
            out["verdict"] = "not_validated"
            report[pid] = out
            print(pid, "not enough sites", flush=True)
            continue
        n = len(S)
        out["sites_in_top5pct_start"] = sum(site_rank(S, w0, b) <= n * 0.05 for b in bags)
        methods = {}
        for name, fit in (("soft_rank", soft_optimise), ("shared_features", shared_features)):
            ok, gain, imp, loo, before, after = validate(S, bags, w0, fit)
            w = fit(S, bags, w0)
            z = None
            if isinstance(w, tuple):
                w, z = w
            methods[name] = {"accepted": bool(ok), "gain": round(float(gain), 4), "improved": int(imp), "of": len(loo),
                             "mean_hidden_rank_start": round(float(before)), "mean_hidden_rank_trained": round(float(after)),
                             "weights": dict(zip(tun, w.round(4).tolist())),
                             "sites_in_top5pct": int(sum(site_rank(S, w, b) <= n * 0.05 for b in bags)),
                             "feature_z": None if z is None else dict(zip(tun, z.round(3).tolist()))}
            print(pid, name, "accepted" if ok else "rejected", f"{100 * gain:+.1f}% {imp}/{len(loo)} improved;",
                  f"hidden mean rank {before:.0f}->{after:.0f}; sites in top 5%: {out['sites_in_top5pct_start']}->{methods[name]['sites_in_top5pct']} of {len(bags)}", flush=True)
        out["methods"] = methods
        acc = [(m["gain"], k) for k, m in methods.items() if m["accepted"]]
        out["chosen"] = max(acc)[1] if acc else "science"
        out["seconds"] = round(time.time() - t0)
        report[pid] = out
        rp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
