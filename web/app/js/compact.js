/* Planalogy — compact 11 km data for the Finder.
 * The 11 km Earth grid has 2.1 M land cells; the page ships only the 268 k cells that are Mars-like dry land in
 * some year, packed as base64 typed arrays (cells.json), plus the Data team's 1° climate changes per projected
 * year (deltas.json). This module rebuilds the Finder's usual tables ({columns, rows}) from them, and future years
 * with the same bilinear delta method as the local tool (hires_tool/planalogy_hires.py). Mars: 11 km terrain,
 * albedo and thermal inertia (mars_fine_*.json) over the 1° table for everything else. */
(function (root) {
  'use strict';
  const ROCKS = ['', 'volcanic', 'ancient_crust', 'sedimentary', 'evaporite_salt', 'ice', 'impact', 'water'];
  const MINERALS = ['basaltic', 'felsic', 'clays_hydrated', 'sulfates_salts', 'carbonates', 'iron_oxides'];

  function b64(s, t) {
    const bin = atob(s), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return t === 'u16' ? new Uint16Array(u.buffer) : t === 'i16' ? new Int16Array(u.buffer) : u;
  }

  function init(manifest, cellsJ, deltasJ) {
    const C = { n: cellsJ.n, keys: cellsJ.keys, scale: cellsJ.scale };
    for (const [k, v] of Object.entries(cellsJ.cols)) C[k] = b64(v.b64, v.t);
    const s = C.scale, n = C.n;
    const f = (arr, i, sc, miss) => arr[i] === miss ? null : arr[i] / sc;
    const minCache = new Map();
    const minerals = (mask, known) => {
      if (!known) return null;
      if (!minCache.has(mask)) minCache.set(mask, MINERALS.filter((_, j) => (mask >> j) & 1));
      return minCache.get(mask);
    };
    const columns = ['id', 'lat', 'lon'].concat(manifest.features.map(x => x.id), ['dry_bare', 'aridity_index', 'cold_desert']);
    const ix = {}; columns.forEach((c, i) => { ix[c] = i; });
    const now = {
      sswing: Float64Array.from({ length: n }, (_, i) => C.sswing[i] === -32768 ? NaN : C.sswing[i] / s.sswing),
      smin: Float64Array.from({ length: n }, (_, i) => C.smin[i] === -32768 ? NaN : C.smin[i] / s.smin),
      aswing: Float64Array.from({ length: n }, (_, i) => C.aswing[i] === -32768 ? NaN : C.aswing[i] / s.aswing),
      arid: Float64Array.from({ length: n }, (_, i) => C.arid[i] === -32768 ? NaN : C.arid[i] / s.arid),
    };
    const num = x => (Number.isFinite(x) ? x : null);
    const bit = (i, key) => (C.dry[i] >> C.keys.indexOf(key)) & 1;

    function rowsFor(key, cl) {
      const rows = new Array(n);
      for (let i = 0; i < n; i++) {
        const lat = +(90 - (C.r[i] + 0.5) * 0.1).toFixed(2), lon = +(-180 + (C.c[i] + 0.5) * 0.1).toFixed(2);
        const r = new Array(columns.length);
        r[0] = 'c' + C.r[i] + '_' + C.c[i]; r[1] = lat; r[2] = lon;
        for (const feat of manifest.features) {
          let v = null;
          switch (feat.id) {
            case 'slope_deg': v = f(C.slope, i, s.slope, 65535); break;
            case 'roughness_m': v = f(C.rough, i, s.rough, 65535); break;
            case 'relief_m': v = f(C.relief, i, s.relief, 65535); break;
            case 'albedo': v = f(C.albedo, i, s.albedo, 65535); break;
            case 'ati_percentile': v = f(C.ati, i, s.ati, 65535); break;
            case 'surface_temp_swing_K': v = num(cl.sswing[i]); break;
            case 'surface_temp_min_K': v = num(cl.smin[i]); break;
            case 'air_temp_swing_K': v = num(cl.aswing[i]); break;
            case 'mineral_groups': v = minerals(C.minerals[i], C.flags[i] & 4); break;
            case 'rock_group': v = ROCKS[C.rock[i]] || null; break;
            case 'inside_impact_structure': v = (C.flags[i] & 1) === 1; break;
            case 'ground_ice_flag': v = (C.flags[i] & 2) === 2; break;
          }
          r[ix[feat.id]] = v;
        }
        const dry = bit(i, key) === 1, ai = num(cl.arid[i]);
        r[ix.dry_bare] = dry; r[ix.aridity_index] = ai; r[ix.cold_desert] = dry && !(ai !== null && ai <= 0.2);
        rows[i] = r;
      }
      return { columns, rows };
    }

    function bilinear(grid, sc) {
      const out = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        const lat = 90 - (C.r[i] + 0.5) * 0.1, lon = -180 + (C.c[i] + 0.5) * 0.1;
        const fy = Math.min(179, Math.max(0, 89.5 - lat)), y0 = Math.floor(fy), y1 = Math.min(y0 + 1, 179), wy = fy - y0;
        const fx = ((lon + 179.5) % 360 + 360) % 360, x0 = Math.floor(fx) % 360, x1 = (x0 + 1) % 360, wx = fx - Math.floor(fx);
        let nm = 0, dn = 0;
        for (const [yy, a] of [[y0, 1 - wy], [y1, wy]]) for (const [xx, b] of [[x0, 1 - wx], [x1, wx]]) {
          const v = grid[yy * 360 + xx]; if (v !== -32768) { nm += (v / sc) * a * b; dn += a * b; }
        }
        if (dn > 0.15) out[i] = nm / dn;
        else {
          const pi = Math.min(179, Math.max(0, Math.floor(90 - lat))), pj = Math.min(359, Math.max(0, Math.floor(lon + 180)));
          const v = grid[pi * 360 + pj]; out[i] = v === -32768 ? NaN : v / sc;
        }
      }
      return out;
    }

    const base = rowsFor('now', now);
    const lru = new Map();
    function year(key) {
      if (key === 'now') return base;
      if (lru.has(key)) { const t = lru.get(key); lru.delete(key); lru.set(key, t); return t; }
      const d = deltasJ.years[key], D = deltasJ.scale.d, R = deltasJ.scale.r;
      const g = (name, sc) => bilinear(b64(d[name], 'i16'), sc);
      const dAs = g('dAswing', D), dTn = g('dTmin', D), rA = g('rAI', R);
      const cl = {
        sswing: now.sswing.map((v, i) => v + dAs[i]), smin: now.smin.map((v, i) => v + dTn[i]),
        aswing: now.aswing.map((v, i) => v + dAs[i]), arid: now.arid.map((v, i) => v * rA[i]),
      };
      const t = rowsFor(key, cl);
      lru.set(key, t); while (lru.size > 3) lru.delete(lru.keys().next().value);  // memory: ~100 MB per table
      return t;
    }
    return { base, year, n };
  }

  /** Mars target values at 11 km: terrain, albedo and ATI from the fine grid, the rest from the 1° table. */
  function marsCell(manifest, PS, mars1, fineA, fineB, lat, lon) {
    const g = manifest.grid.mars, c = PS.containingCell(g, lat, lon);
    if (!c) return null;
    const one = { grid: { mars: { lat_step: 1, lon_step: 1, lat0: -89.5, lon0: -179.5, n_lat: 180, n_lon: 360, decimals: 1 } }, features: manifest.features };
    const coarse = PS.marsCell(one, mars1, lat, lon);
    if (!coarse) return null;
    const values = Object.assign({}, coarse.values);
    const r = Math.round((90 - c.lat) / g.lat_step - 0.5), col = Math.round((c.lon + 180) / g.lon_step - 0.5), k = r * g.n_lon + col;
    for (const F of [fineA, fineB]) {
      if (!F._arr) { F._arr = {}; for (const [name, s] of Object.entries(F.cols)) F._arr[name] = b64(s, 'u16'); }
      for (const [name, arr] of Object.entries(F._arr)) { const v = arr[k]; values[name] = v === 65535 ? null : v / F.scale[name]; }
    }
    return { lat: c.lat, lon: c.lon, values };
  }

  root.PlanalogyCompact = { init, marsCell };
})(typeof self !== 'undefined' ? self : this);
