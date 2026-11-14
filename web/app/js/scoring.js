/* Planalogy — the analogue engine's scoring, reproduced in the browser for any regular grid
 * (1°, 50 km, …; each planet's grid comes from manifest.grid).
 *
 * Similarity per feature, with the engine's comparators and fixed scales (from the manifest):
 *   clipped_linear_v1:      s = 1 − min(1, |x − t| / τ)
 *   categorical / boolean:  s = 1 if x == t else 0
 *   missing value:          no similarity (never 0)
 * Score of a cell: Σ w_j s_j / Σ w_j, with the engine's effective weights
 *   w_j = (W_g / Σ W) · (a_j / Σ_{k in g} a_k).
 * Same rules as the Python engine:
 *   - a cell with no value for a feature that has positive weight (or is required) is "partial";
 *   - a failed requirement ("equals") excludes the cell, whatever its score;
 *   - order: score (rounded to 12 decimals) descending, then cell id ascending.
 * Values come unrounded from backend/web_export.py, so similarities match the engine bit for bit
 * and scores to ~1e-16 (the engine sums with math.fsum); the order is identical
 * (checked by backend/tests/test_web_export.py under Node.js).
 * Works as a browser global (window.PlanalogyScoring) and as a CommonJS module.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlanalogyScoring = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const colIndex = table => { const ix = {}; table.columns.forEach((c, i) => { ix[c] = i; }); return ix; };

  /** A planet's grid from the manifest (step, origin, size); old manifests: 1° global grid. */
  function gridOf(manifest, body) {
    if (manifest.grid && manifest.grid[body]) return manifest.grid[body];
    const s = manifest.grid_deg || 1;
    return { lat_step: s, lon_step: s, lat0: -90 + s / 2, lon0: -180 + s / 2, n_lat: Math.round(180 / s),
             n_lon: Math.round(360 / s), decimals: 1, cell_km: null };
  }

  /** Centre of the grid cell containing (lat, lon), or null outside the grid —
   *  same rule as GridSpec.containing in backend/grid_data.py (never snaps to an edge cell). */
  function containingCell(grid, lat, lon) {
    const wrapLon = x => ((x + 180) % 360 + 360) % 360 - 180;
    const round6 = x => Number(x.toFixed(6));
    const fi = (lat - (grid.lat0 - grid.lat_step / 2)) / grid.lat_step;
    const fj = (wrapLon(lon) - (grid.lon0 - grid.lon_step / 2)) / grid.lon_step;
    let i = Math.floor(fi + 1e-9), j = Math.floor(fj + 1e-9);
    if (i === grid.n_lat && fi <= grid.n_lat + 1e-9) i -= 1; // on the outer edge (e.g. the pole)
    if (Math.abs(grid.n_lon * grid.lon_step - 360) < 1e-6) j = ((j % grid.n_lon) + grid.n_lon) % grid.n_lon;
    else if (j === grid.n_lon && fj <= grid.n_lon + 1e-9) j -= 1;
    if (i < 0 || i >= grid.n_lat || j < 0 || j >= grid.n_lon) return null;
    return { lat: round6(grid.lat0 + i * grid.lat_step), lon: round6(grid.lon0 + j * grid.lon_step) };
  }

  /** Feature values of the Mars cell that contains (lat, lon); null if no cell or no data there. */
  function marsCell(manifest, mars, lat, lon) {
    const c = containingCell(gridOf(manifest, 'mars'), lat, lon);
    if (!c) return null;
    const ix = colIndex(mars);
    if (!mars._byKey) { mars._byKey = new Map(); mars.rows.forEach(r => mars._byKey.set(r[ix.lat] + ',' + r[ix.lon], r)); }
    const row = mars._byKey.get(c.lat + ',' + c.lon);
    if (!row) return null;
    const values = {};
    manifest.features.forEach(f => { values[f.id] = row[ix[f.id]]; });
    return { lat: c.lat, lon: c.lon, values };
  }

  /** Short label for a planet's cells: "1° cell" or "0.45° cell (≈50 km)". */
  function cellLabel(manifest, body) {
    const g = gridOf(manifest, body);
    if (g.lat_step === 1 && g.lon_step === 1) return '1° cell';
    return g.lat_step + '° cell' + (g.cell_km ? ' (≈' + Math.round(g.cell_km) + ' km)' : '');
  }

  /** Earth table for a year: the base table with the yearly file's columns (climate-dependent) replaced. */
  function earthForYear(base, yearTable) {
    if (!yearTable || !yearTable.base) return yearTable || base;
    const bi = colIndex(base), yi = colIndex(yearTable);
    const cols = yearTable.columns.filter(c => c !== 'id');
    const byId = new Map(yearTable.rows.map(r => [r[yi.id], r]));
    const rows = [];
    for (const r of base.rows) {
      const y = byId.get(r[bi.id]);
      if (!y) continue; // cell absent that year
      const out = r.slice();
      cols.forEach(c => { out[bi[c]] = y[yi[c]]; });
      rows.push(out);
    }
    return { columns: base.columns, rows };
  }

  /** Similarity of every Earth cell to a target, feature by feature. */
  function similarities(manifest, earth, targetValues) {
    const ix = colIndex(earth);
    const feats = manifest.features;
    const byId = {};
    const targetMissing = feats.filter(f => targetValues[f.id] === null || targetValues[f.id] === undefined).map(f => f.id);
    for (const row of earth.rows) {
      const s = new Array(feats.length);
      for (let j = 0; j < feats.length; j++) {
        const f = feats[j], x = row[ix[f.id]], t = targetValues[f.id];
        if (x === null || x === undefined || t === null || t === undefined) { s[j] = null; continue; }
        if (f.comparator === 'clipped_linear_v1') { const d = Math.min(1.0, Math.abs(x - t) / f.tau); s[j] = 1.0 - d; }
        else s[j] = x === t ? 1.0 : 0.0;
      }
      byId[row[ix.id]] = s;
    }
    return { columns: feats.map(f => f.id), by_id: byId, targetMissing };
  }

  /** Effective weights per feature from category weights and in-category feature weights. */
  function effectiveWeights(features, categoryWeights, featureWeights) {
    const cats = {};
    features.forEach(f => { (cats[f.category] = cats[f.category] || []).push(f.id); });
    let totalW = 0;
    Object.keys(cats).forEach(c => {
      const W = +(categoryWeights[c] || 0);
      if (!(W >= 0) || !isFinite(W)) throw new Error('Category weight must be a finite number >= 0: ' + c);
      totalW += W;
    });
    if (!(totalW > 0)) throw new Error('At least one category needs a positive weight.');
    const w = {};
    Object.keys(cats).forEach(c => {
      const W = +(categoryWeights[c] || 0) / totalW;
      const ids = cats[c];
      const inner = ids.reduce((s, id) => s + Math.max(0, +(featureWeights[id] ?? 1)), 0);
      ids.forEach(id => {
        const a = Math.max(0, +(featureWeights[id] ?? 1));
        w[id] = W > 0 && inner > 0 ? W * a / inner : 0;
      });
    });
    return w;
  }

  /** Score every Earth cell. Returns {ranked, partial, excluded, skipped}; ranked carries position. */
  function scoreCells(manifest, earth, sims, settings) {
    const features = manifest.features;
    const fIndex = {};
    sims.columns.forEach((f, i) => { fIndex[f] = i; });
    const cIndex = colIndex(earth);
    const w = effectiveWeights(features, settings.categoryWeights, settings.featureWeights || {});
    const required = new Set(settings.requiredFeatures || []);
    (settings.requirements || []).forEach(r => required.add(r.feature));
    const reqs = settings.requirements || [];
    const onlyDry = settings.onlyDryBare !== false && cIndex.dry_bare !== undefined;
    const ranked = [], partial = [], excluded = [];
    let skipped = 0;

    for (const row of earth.rows) {
      if (onlyDry && !row[cIndex.dry_bare]) { skipped++; continue; }
      const id = row[cIndex.id];
      const s = sims.by_id[id];
      if (!s) continue;
      let num = 0, den = 0, blocked = false;
      const missing = [];
      for (const f of features) {
        const sv = s[fIndex[f.id]], wf = w[f.id];
        if (sv === null || sv === undefined) {
          if (wf > 0 || required.has(f.id)) { blocked = true; missing.push(f.id); }
          continue;
        }
        num += wf * sv; den += wf;
      }
      const failed = [];
      let unevaluable = false;
      for (const r of reqs) {
        const v = row[cIndex[r.feature]];
        if (v === null || v === undefined) unevaluable = true;
        else if (v !== r.equals) failed.push(r);
      }
      const item = { id, lat: row[cIndex.lat], lon: row[cIndex.lon], score: den > 0 ? num / den : null,
                     missing, failed, row, sims: s, dryBare: cIndex.dry_bare !== undefined ? !!row[cIndex.dry_bare] : true };
      if (failed.length) excluded.push(item);
      else if (blocked || unevaluable) partial.push(item);
      else ranked.push(item);
    }
    const key = x => Math.round(x.score * 1e12) / 1e12;
    ranked.sort((a, b) => (key(b) - key(a)) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    ranked.forEach((x, i) => { x.position = i + 1; });
    return { ranked, partial, excluded, skipped, weights: w };
  }

  /** Category scores for one cell (weighted by in-category feature weights). */
  function categoryScores(manifest, item, featureWeights) {
    const out = {};
    const fIndex = {};
    manifest.features.forEach((f, i) => { fIndex[f.id] = i; });
    manifest.categories.forEach(c => {
      let num = 0, den = 0;
      manifest.features.filter(f => f.category === c.id).forEach(f => {
        const sv = item.sims[fIndex[f.id]], a = Math.max(0, +((featureWeights || {})[f.id] ?? 1));
        if (sv !== null && sv !== undefined && a > 0) { num += a * sv; den += a; }
      });
      out[c.id] = den > 0 ? num / den : null;
    });
    return out;
  }

  /** A site card: what matches, partly, does not; missing data. */
  function card(manifest, item, settings) {
    const t = manifest.thresholds || { strong_at_least: 75, weak_at_most: 40 };
    const cs = categoryScores(manifest, item, settings.featureWeights);
    const active = c => +(settings.categoryWeights[c] || 0) > 0;
    const groups = { matches: [], partial: [], mismatches: [] };
    manifest.categories.forEach(c => {
      const v = cs[c.id];
      if (v === null || !active(c.id)) return;
      const pct = Math.round(v * 1000) / 10;
      const g = pct >= t.strong_at_least ? 'matches' : pct > t.weak_at_most ? 'partial' : 'mismatches';
      groups[g].push({ id: c.id, label: c.label, score: pct });
    });
    Object.values(groups).forEach(a => a.sort((x, y) => y.score - x.score));
    return { score: item.score === null ? null : Math.round(item.score * 1000) / 10, categories: cs, ...groups,
             missing: item.missing, failed: item.failed };
  }

  return { gridOf, containingCell, marsCell, cellLabel, earthForYear, similarities, effectiveWeights, scoreCells,
           categoryScores, card };
});
