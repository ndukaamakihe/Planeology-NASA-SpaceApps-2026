/* Planalogy — Analog Finder, one screen with two globes.
   Click anywhere on Mars: the area around the click (100 km radius) is averaged and every Earth land cell is
   ranked against it. Earth flies to the best match, a thin arc links the two places, the match opens.
   The year runs from today to 2090 one year at a time; years between the projections are interpolated.
   Every Earth land cell is ranked against the Mars cell with the analogue engine's comparators, reproduced in
   js/scoring.js on raw values exported by backend/web_export.py (data/planalogy/*.json). */
(function(){
const TT = window.TT, h = TT.h, PS = window.PlanalogyScoring;
const DATA = 'data/planalogy/';
const TOP = 8;
const REGION = {
  '-23.5,-68.5': 'Atacama Desert, Chile', '34.5,76.5': 'Ladakh / Aksai Chin', '37.5,75.5': 'Pamir, Xinjiang',
  '40.5,78.5': 'Tarim Basin margin', '38.5,76.5': 'Kashgar, Tarim Basin', '31.5,-5.5': 'Pre-Saharan Morocco',
  '41.5,79.5': 'Northern Tarim Basin', '14.5,40.5': 'Danakil Depression', '30.5,69.5': 'Balochistan',
  '30.5,81.5': 'Ngari, western Tibet', '44.5,83.5': 'Junggar Basin', '30.5,84.5': 'Tibetan Plateau',
  '30.5,87.5': 'Tibetan Plateau', '31.5,81.5': 'Western Tibetan Plateau', '30.5,83.5': 'Tibetan Plateau',
  '67.5,177.5': 'Chukotka', '70.5,-54.5': 'West Greenland', '37.5,45.5': 'Lake Urmia basin, Iran',
  '-24.5,-69.5': 'Atacama Desert, Chile', '-24.5,-67.5': 'Salar de Arizaro', '39.5,73.5': 'Kara-Kul, Pamir',
  '-77.5,161.5': 'McMurdo Dry Valleys', '75.5,-89.5': 'Devon Island (Haughton)', '39.5,99.5': 'Hexi Corridor, Gansu'
};
/* Moon: planned and proposed sites (same records as the team's site database). Shown as a preview, not scored. */
const MOON_SITES = [
  {id:'m1', name:'Shackleton crater rim', lat:-89.67, lon:129.78, kind:'base', note:'Proposed outpost location'},
  {id:'m2', name:'Malapert Massif', lat:-86.0, lon:0.3, kind:'landing', note:'Artemis III candidate region'},
  {id:'m3', name:'Haworth', lat:-86.9, lon:-4.0, kind:'landing', note:'Artemis III candidate region'},
  {id:'m4', name:'Mons Mouton', lat:-84.6, lon:31.0, kind:'landing', note:'Artemis III candidate region'},
  {id:'m5', name:'Nobile rim', lat:-85.28, lon:53.27, kind:'landing', note:'Artemis III candidate region'},
  {id:'m6', name:'de Gerlache rim', lat:-88.5, lon:-87.1, kind:'landing', note:'Artemis III candidate region'},
  {id:'m7', name:'Mare Tranquillitatis pit', lat:8.3355, lon:33.222, kind:'base', note:'Lava tube skylight'},
  {id:'m8', name:'Marius Hills Hole', lat:14.1, lon:-56.738, kind:'base', note:'Lava tube skylight'}
];
const DEFAULT_FW = {slope_deg:1, roughness_m:1, relief_m:1, surface_temp_swing_K:2, surface_temp_min_K:1, air_temp_swing_K:1, ati_percentile:1, albedo:1, mineral_groups:1, rock_group:1, inside_impact_structure:1, ground_ice_flag:1};
const cache = {};
/* .json.gz files: unpack in the browser when the server sends them as plain bytes */
async function readJson(r){
  const buf = new Uint8Array(await r.arrayBuffer());
  if (buf[0] === 0x1f && buf[1] === 0x8b){
    const s = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(s).text());
  }
  return JSON.parse(new TextDecoder().decode(buf));
}
const load = f => cache[f] || (cache[f] = fetch(DATA + f).then(r => { if (!r.ok) throw new Error(f + ': ' + r.status); return readJson(r); }));
const pct = x => x == null ? '–' : Math.round(x * 100);
const region = it => REGION[(Math.floor(it.lat) + .5) + ',' + (Math.floor(it.lon) + .5)];
const sspName = s => String(s).replace(/^ssp(\d)(\d)(\d)$/, 'SSP$1-$2.$3');
const words = s => String(s).replace(/_/g, ' ');

/* score -> colour (stretched over the current ranking) */
const STOPS = [[0, [40, 70, 150, .08]], [.4, [64, 128, 220, .3]], [.65, [96, 190, 240, .48]], [.82, [250, 210, 110, .62]], [1, [255, 110, 60, .74]]];
function ramp(t){
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < STOPS.length; i++){
    const [t1, c1] = STOPS[i]; const [t0, c0] = STOPS[i - 1];
    if (t <= t1){ const k = (t - t0) / (t1 - t0); return c0.map((v, j) => v + (c1[j] - v) * k); }
  }
  return STOPS[STOPS.length - 1][1];
}
const rgba = c => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${c[3].toFixed(3)})`;

/* one feature value of a cell, written for people */
function show(f, v){
  if (v == null || (Array.isArray(v) && !v.length)) return null;
  if (f.kind === 'boolean') return v ? 'yes' : 'no';
  if (f.kind === 'set') return v.map(words).join(', ');
  if (f.kind === 'categorical') return words(v);
  if (f.id === 'ati_percentile') return Math.round(v * 100) + ' % rank';
  if (f.unit === 'K') return (/swing/.test(f.id) ? (+v).toFixed(1) : (v - 273.15).toFixed(1)) + ' °C';  /* a swing is a difference: same number */
  const a = Math.abs(v), d = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return (+v).toFixed(d) + (f.unit && f.unit !== '1' ? ' ' + (f.unit === 'deg' ? '°' : f.unit) : '');
}

const SHORT = {'Rover navigation and mobility':'Rover driving', 'Sample science and geology':'Sample science', 'Thermal environment testing':'Thermal testing', 'Ground-ice prospecting (ISRU)':'Ice prospecting'};
const AREA_KM = 100;                 /* radius of the area you pick on Mars */
const R_KM = {earth: 6371, mars: 3389.5, moon: 1737.4};
const PXD = 8;                       /* overlay pixels per degree (2880 x 1440 texture) */
const Y0 = 2025, Y1 = 2090;          /* the year slider: today, then one year at a time */
const START = {lat:18.4, lon:77.5, label:'Jezero crater'};
const YEAR_SCALAR = ['surface_temp_swing_K', 'surface_temp_min_K', 'air_temp_swing_K', 'ati_percentile'];
const toRad = d => d * Math.PI / 180;
function distKm(body, la1, lo1, la2, lo2){
  const p1 = toRad(la1), p2 = toRad(la2), dp = p2 - p1, dl = toRad(lo2 - lo1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R_KM[body] * Math.asin(Math.min(1, Math.sqrt(a)));
}
const colIx = t => { const o = {}; t.columns.forEach((c, i) => { o[c] = i; }); return o; };
/* colours as 32-bit pixels (little endian: alpha, blue, green, red) */
const px32 = (r, g, b, a) => ((Math.round(a * 255) << 24) | (b << 16) | (g << 8) | r) >>> 0;
const LUT_SIM = new Uint32Array(256), LUT_DIV = new Uint32Array(256);
for (let k = 0; k < 256; k++){
  const c = ramp(k / 255); LUT_SIM[k] = px32(c[0] | 0, c[1] | 0, c[2] | 0, c[3]);
  const t = k / 127.5 - 1, q = Math.abs(t), end = t >= 0 ? [70, 150, 255] : [255, 150, 40], grey = [150, 150, 160];
  const d = grey.map((g, i) => g + (end[i] - g) * q | 0); LUT_DIV[k] = px32(d[0], d[1], d[2], .14 + .56 * q);
}
const PX_LOST = px32(255, 75, 75, .9), PX_FRESH = px32(92, 240, 160, .9);

TT.pages.finder = function(root){
  const st = {m:null, preset:null, cw:{}, on:{}, fw:Object.assign({}, DEFAULT_FW), req:[], reqF:[], dry:true,
              year:Y0, scen:null, pair:'mars', area:null, sel:-1, moonSel:null, show:'change', playing:false};
  let dead = false, gL = null, gE = null, ui = {}, E = null, S0 = null, OK0 = null, S = null, OK = null, Vnow = null;
  let anchors = {}, top = [], nOk = 0, lo = 0, hi = 1, dmax = .03, stats = null, markerKey = '';

  /* ---------- skeleton ---------- */
  const scroll = h('div', {class:'fp-scroll'});
  const orbs = h('div', {class:'orbs', role:'radiogroup', 'aria-label':'Planets'});
  const panel = h('aside', {class:'fpanel', 'aria-label':'Controls'}, scroll, orbs);
  const status = h('div', {class:'s-status', role:'status', 'aria-live':'polite'});
  const legend = h('div', {class:'s-legend'});
  const band = h('div', {class:'s-band'});
  const cvL = h('canvas', {class:'view', role:'application', 'aria-label':'Mars globe. Click to pick an area, drag to turn.'});
  const cvE = h('canvas', {class:'view', role:'application', 'aria-label':'Earth globe. Drag to turn; click a marker to open a match.'});
  const tagL = h('div', {class:'g-tag'}), tagE = h('div', {class:'g-tag'});
  const wrapL = h('div', {class:'g-wrap'}, cvL, tagL), wrapE = h('div', {class:'g-wrap'}, cvE, tagE);
  const link = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); link.setAttribute('class', 'g-link'); link.setAttribute('aria-hidden', 'true');
  const globes = h('div', {class:'s-globes'}, wrapL, wrapE, link);
  const stage = h('div', {class:'stage'}, h('div', {class:'s-info'}, status, legend), globes, band);
  root.appendChild(h('div', {class:'finder'}, panel, stage));

  if (TT.webgl){
    gL = TT.createGlobe(cvL, {body:'mars', markerPx:20, dist:3.35, onPin: (la, lo) => pickArea(la, lo), onPick: () => {}});
    gE = TT.createGlobe(cvE, {body:'earth', markerPx:20, dist:3.35, onPick: it => it.body === 'earth' && select(+it.id, true)});
    gL.setPinMode(true); gE.setPinMode(false);  /* Earth only turns; its markers open a match */
  } else stage.appendChild(h('p', {class:'no-gl'}, 'The globes need WebGL, which this browser has switched off.'));

  /* ---------- weights ---------- */
  const cats = () => st.m.categories;
  function applyPreset(p){
    st.preset = p.id;
    const mx = Math.max(...Object.values(p.category_weights));
    st.cw = {}; st.on = {};
    cats().forEach(c => { const w = mx > 0 ? (p.category_weights[c.id] || 0) * 5 / mx : 0; st.cw[c.id] = Math.round(w * 10) / 10; st.on[c.id] = w > 0; });
    st.fw = Object.assign({}, DEFAULT_FW, p.feature_weights);
    st.req = p.requirements || []; st.reqF = p.required_features || [];
  }
  const missingT = () => st.area ? st.m.features.filter(f => st.area.values[f.id] == null).map(f => f.id) : [];
  const noData = c => { const miss = new Set(missingT()); return st.m.features.filter(f => f.category === c.id).every(f => miss.has(f.id)); };
  function effectiveCW(){ const cw = {}; cats().forEach(c => { cw[c.id] = st.on[c.id] && !noData(c) ? (st.cw[c.id] || 0) : 0; }); return cw; }
  function effectiveFW(){ const fw = Object.assign({}, st.fw); missingT().forEach(f => { fw[f] = 0; }); return fw; }

  /* ---------- Earth as columns: fast enough to rescore every year while the slider moves ---------- */
  function buildEarth(t){
    const ix = colIx(t), n = t.rows.length, g = PS.gridOf(st.m, 'earth');
    const o = {n, step: g.lat_step, ids: new Array(n), lat: new Float32Array(n), lon: new Float32Array(n), col: {}, codes: {}, dry: new Uint8Array(n),
               x: new Uint16Array(n), y: new Uint16Array(n), hash: new Float32Array(n), byId: new Map()};
    const nlat = Math.round(180 / g.lat_step), nlon = Math.round(360 / g.lon_step);
    o.grid = new Int32Array(nlat * nlon).fill(-1); o.nlat = nlat; o.nlon = nlon;
    const keyIx = {};
    st.m.features.forEach(f => {
      if (f.kind === 'scalar') o.col[f.id] = new Float32Array(n);
      else if (f.kind === 'boolean') o.col[f.id] = new Int8Array(n);
      else { o.col[f.id] = new Int16Array(n); o.codes[f.id] = []; keyIx[f.id] = new Map(); }
    });
    for (let i = 0; i < n; i++){
      const r = t.rows[i], la = r[ix.lat], lo = r[ix.lon];
      o.ids[i] = r[ix.id]; o.byId.set(r[ix.id], i); o.lat[i] = la; o.lon[i] = lo; o.dry[i] = r[ix.dry_bare] ? 1 : 0;
      o.x[i] = Math.round((lo - g.lon_step / 2 + 180) * PXD); o.y[i] = Math.round((90 - la - g.lat_step / 2) * PXD);
      const gr = Math.round((90 - la) / g.lat_step - .5), gc = Math.round((lo + 180) / g.lon_step - .5); o.grid[gr * nlon + gc] = i;
      const s = Math.sin(i * 12.9898 + 78.233) * 43758.5453; o.hash[i] = s - Math.floor(s);
      for (const f of st.m.features){
        const v = r[ix[f.id]];
        if (f.kind === 'scalar') o.col[f.id][i] = v == null ? NaN : v;
        else if (f.kind === 'boolean') o.col[f.id][i] = v == null ? -1 : v ? 1 : 0;
        else if (v == null) o.col[f.id][i] = -1;
        else { const k = JSON.stringify(v); let c = keyIx[f.id].get(k); if (c === undefined){ c = o.codes[f.id].length; keyIx[f.id].set(k, c); o.codes[f.id].push(v); } o.col[f.id][i] = c; }
      }
    }
    o.px = Math.max(1, Math.round(g.lat_step * PXD));
    return o;
  }
  /* one projected year: today's columns with the climate columns of that file */
  function buildAnchor(t){
    const ix = colIx(t), a = {ice: Int8Array.from(E.col.ground_ice_flag), dry: Uint8Array.from(E.dry)};
    YEAR_SCALAR.forEach(c => { a[c] = Float32Array.from(E.col[c]); });
    for (const r of t.rows){
      const i = E.byId.get(r[ix.id]); if (i === undefined) continue;
      YEAR_SCALAR.forEach(c => { if (ix[c] !== undefined){ const v = r[ix[c]]; a[c][i] = v == null ? NaN : v; } });
      if (ix.ground_ice_flag !== undefined){ const v = r[ix.ground_ice_flag]; a.ice[i] = v == null ? -1 : v ? 1 : 0; }
      if (ix.dry_bare !== undefined) a.dry[i] = r[ix.dry_bare] ? 1 : 0;
    }
    return a;
  }
  const scens = () => st.m.scenarios ? st.m.scenarios.map(x => x.id) : Object.keys(st.m.files.earth_by_scenario || {});
  const scenFiles = id => { const si = (st.m.scenarios || []).find(x => x.id === id); return (si && si.files) || (st.m.files.earth_by_scenario || {})[id] || {}; };
  function loadScenario(id){
    if (anchors[id]) return anchors[id];
    const files = scenFiles(id), years = Object.keys(files).map(Number).sort((a, b) => a - b);
    anchors[id] = Promise.all(years.map(y => fetch(DATA + files[y]).then(r => { if (!r.ok) throw new Error(files[y]); return readJson(r); })
      .then(t => ({year: y, data: buildAnchor(t)})))).then(list => [{year: Y0, data: null}].concat(list));
    return anchors[id];
  }

  /* the Earth of any year: linear between the projections; a yes/no value flips at a random moment in between,
     so cells drop out or appear one by one instead of all at once */
  const cur = {};
  function viewAt(year, list){
    if (!cur.ice){ YEAR_SCALAR.forEach(c => { cur[c] = new Float32Array(E.n); }); cur.ice = new Int8Array(E.n); cur.dry = new Uint8Array(E.n); }
    const base = {ice: E.col.ground_ice_flag, dry: E.dry}; YEAR_SCALAR.forEach(c => { base[c] = E.col[c]; });
    let a = list[0], b = list[0];
    for (let k = 0; k < list.length - 1; k++) if (year >= list[k].year){ a = list[k]; b = list[k + 1]; }
    if (year >= list[list.length - 1].year){ a = b = list[list.length - 1]; }
    const A = a.data || base, B = b.data || base, f = b.year > a.year ? (year - a.year) / (b.year - a.year) : 0;
    const n = E.n, H = E.hash;
    YEAR_SCALAR.forEach(c => { const x = A[c], y = B[c], o = cur[c]; for (let i = 0; i < n; i++) o[i] = x[i] + (y[i] - x[i]) * f; });
    for (let i = 0; i < n; i++){ const flip = f > H[i]; cur.ice[i] = flip ? B.ice[i] : A.ice[i]; cur.dry[i] = flip ? B.dry[i] : A.dry[i]; }
    /* what changed since today, for the line above the globes */
    let thaw = 0, wet = 0, dry = 0, dT = 0, nT = 0;
    const t0 = E.col.surface_temp_min_K, t1 = cur.surface_temp_min_K, i0 = E.col.ground_ice_flag;
    for (let i = 0; i < n; i++){
      if (i0[i] === 1 && cur.ice[i] === 0) thaw++;
      if (E.dry[i] && !cur.dry[i]) wet++; else if (!E.dry[i] && cur.dry[i]) dry++;
      const d = t1[i] - t0[i]; if (d === d){ dT += d; nT++; }
    }
    stats = {thaw, wet, dry, warm: nT ? dT / nT : 0};
    const col = Object.assign({}, E.col); YEAR_SCALAR.forEach(c => { col[c] = cur[c]; }); col.ground_ice_flag = cur.ice;
    return {col, dry: cur.dry};
  }
  const todayView = () => ({col: E.col, dry: E.dry});

  /* every cell scored against the Mars area (same comparators as js/scoring.js and the engine) */
  function plan(){
    const fw = effectiveFW(), w = PS.effectiveWeights(st.m.features, effectiveCW(), fw), req = new Set(st.reqF.filter(f => st.area.values[f] != null));
    st.req.forEach(r => req.add(r.feature));
    return st.m.features.map(f => {
      const t = st.area.values[f.id], p = {id: f.id, kind: f.kind, w: w[f.id] || 0, need: req.has(f.id), t};
      if (f.kind === 'scalar'){ p.tau = f.tau; }
      else if (f.kind === 'boolean'){ p.tb = t == null ? -1 : t ? 1 : 0; }
      else {
        p.lut = new Float32Array(E.codes[f.id].length);
        E.codes[f.id].forEach((v, k) => {
          if (t == null) p.lut[k] = NaN;
          else if (f.kind === 'set'){ const A = new Set(v), B = new Set(t); let sh = 0; A.forEach(x => { if (B.has(x)) sh++; }); const u = A.size + B.size - sh; p.lut[k] = u ? sh / u : 1; }
          else p.lut[k] = v === t ? 1 : 0;
        });
      }
      return p;
    });
  }
  function simOf(p, V, i){
    if (p.t == null) return NaN;
    const c = V.col[p.id], v = c[i];
    if (p.kind === 'scalar') return v !== v ? NaN : 1 - Math.min(1, Math.abs(v - p.t) / p.tau);
    if (p.kind === 'boolean') return v < 0 ? NaN : v === p.tb ? 1 : 0;
    return v < 0 ? NaN : p.lut[v];
  }
  const NUM = {}, DEN = {}, BAD = {};
  function scoreInto(V, out, ok, P){
    const n = E.n;
    if (!NUM.a){ NUM.a = new Float32Array(n); DEN.a = new Float32Array(n); BAD.a = new Uint8Array(n); }
    const num = NUM.a, den = DEN.a, bad = BAD.a; num.fill(0); den.fill(0); bad.fill(0);
    /* one tight loop per parameter (much faster than one call per cell and parameter) */
    for (const p of P){
      if (!(p.w > 0) && !p.need) continue;
      const c = V.col[p.id], w = p.w > 0 ? p.w : 0;
      if (p.t == null){ bad.fill(1); continue; }
      if (p.kind === 'scalar'){ const t = p.t, k = 1 / p.tau;
        for (let i = 0; i < n; i++){ const v = c[i]; if (v !== v){ bad[i] = 1; continue; } let d = (v > t ? v - t : t - v) * k; if (d > 1) d = 1; num[i] += w * (1 - d); den[i] += w; } }
      else if (p.kind === 'boolean'){ const t = p.tb;
        for (let i = 0; i < n; i++){ const v = c[i]; if (v < 0){ bad[i] = 1; continue; } if (v === t) num[i] += w; den[i] += w; } }
      else { const L = p.lut;
        for (let i = 0; i < n; i++){ const v = c[i]; if (v < 0){ bad[i] = 1; continue; } const x = L[v]; if (x !== x){ bad[i] = 1; continue; } num[i] += w * x; den[i] += w; } }
    }
    const ice = V.col.ground_ice_flag, dry = V.dry, dryOn = st.dry;
    const iceReq = st.req.filter(r => r.feature === 'ground_ice_flag').map(r => r.equals ? 1 : 0);
    for (let i = 0; i < n; i++){
      let b = bad[i];
      for (let k = 0; k < iceReq.length; k++) if (ice[i] !== iceReq[k]) b = 1;
      const d = den[i];
      out[i] = d > 0 ? num[i] / d : NaN;
      ok[i] = !b && d > 0 && (!dryOn || dry[i]) ? 1 : 0;
    }
  }
  function rankOf(score, ok, j){ let r = 1; const s = score[j]; for (let i = 0; i < E.n; i++) if (ok[i] && score[i] > s) r++; return r; }
  function topOf(score, ok, k){
    const best = []; let n = 0, mn = Infinity;
    for (let i = 0; i < E.n; i++){
      if (!ok[i]) continue; n++; const s = score[i]; if (s < mn) mn = s;
      if (best.length < k || s > score[best[best.length - 1]]){
        let p = best.length; while (p > 0 && score[best[p - 1]] < s) p--;
        best.splice(p, 0, i); if (best.length > k) best.pop();
      }
    }
    return {best, n, min: mn};
  }

  /* ---------- area on Mars ---------- */
  function areaValues(table, lat, lon){
    const ix = colIx(table), rows = [], dLat = AREA_KM / R_KM.mars * 180 / Math.PI;
    for (const r of table.rows){ const la = r[ix.lat]; if (Math.abs(la - lat) > dLat) continue; if (distKm('mars', lat, lon, la, r[ix.lon]) <= AREA_KM) rows.push(r); }
    if (!rows.length) return null;
    const values = {};
    st.m.features.forEach(f => {
      const vs = rows.map(r => r[ix[f.id]]).filter(v => v !== null && v !== undefined);
      if (!vs.length){ values[f.id] = null; return; }
      if (f.kind === 'scalar') values[f.id] = vs.reduce((a, b) => a + b, 0) / vs.length;
      else if (f.kind === 'boolean') values[f.id] = vs.filter(Boolean).length * 2 >= vs.length;
      else { const c = new Map(); vs.forEach(v => { const k = JSON.stringify(v); c.set(k, (c.get(k) || 0) + 1); }); values[f.id] = JSON.parse([...c.entries()].sort((a, b) => b[1] - a[1])[0][0]); }
    });
    return {values, n: rows.length};
  }
  async function pickArea(lat, lon, label){
    if (st.pair !== 'mars' || !E) return;
    const v = areaValues(await load(st.m.files.mars), lat, lon);
    if (!v){ TT.toast('No Mars data there. Pick another spot.', true); return; }
    st.area = {lat, lon, values: v.values, n: v.n, label: label || null}; st.sel = -1;
    gL.focus(lat, lon, {dist:3.35});
    paintMars(); rescoreToday(); drawArea(); drawSliders();
    update(true);
    const b = top[0]; if (b !== undefined) gE.focus(E.lat[b], E.lon[b], {dist:3.35});
    restartLink();
    const a = st.area;
    setTimeout(() => { if (!dead && st.area === a && st.sel < 0 && top[0] !== undefined) select(top[0], false, true); }, TT.reduced() ? 0 : 1150);
  }


  /* today's scores: the reference for "change since today" and the colour scale */
  let P = null;
  function rescoreToday(){
    if (!st.area) return;
    try { P = plan(); } catch(e){ P = null; status.textContent = 'Switch on at least one parameter.'; return; }
    S0 = S0 || new Float32Array(E.n); OK0 = OK0 || new Uint8Array(E.n); S = S || new Float32Array(E.n); OK = OK || new Uint8Array(E.n);
    scoreInto(todayView(), S0, OK0, P);
    const t = topOf(S0, OK0, 1); hi = t.best.length ? S0[t.best[0]] : 1; lo = t.n ? t.min : 0;
    dmax = .02;
    const list = anchors[st.scen] && anchors[st.scen].done;
    if (list){  /* scale of the change colours: 95th percentile of the change by 2090 */
      const V = viewAt(Y1, list), s = new Float32Array(E.n), ok = new Uint8Array(E.n); scoreInto(V, s, ok, P);
      const ds = []; for (let i = 0; i < E.n; i += 7) if (ok[i] && OK0[i]) ds.push(Math.abs(s[i] - S0[i]));
      ds.sort((a, b) => a - b); if (ds.length) dmax = Math.max(.005, ds[Math.floor(ds.length * .95)]);
    }
  }

  /* ---------- one frame of the year ---------- */
  let raf = 0;
  const requestUpdate = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; update(false); }); };
  function update(full){
    if (dead || !E || !st.area || !P) return;
    const list = anchors[st.scen] && anchors[st.scen].done;
    if (st.year !== Y0 && !list){ loadScenario(st.scen).then(l => { anchors[st.scen].done = l; rescoreToday(); update(true); }); status.textContent = 'Loading the climate projections…'; return; }
    if (st.year === Y0){ S.set(S0); OK.set(OK0); stats = null; Vnow = todayView(); }
    else { Vnow = viewAt(st.year, list); scoreInto(Vnow, S, OK, P); }
    const t = topOf(S, OK, TOP); top = t.best; nOk = t.n;
    paintEarth(); pushMarkers(); drawStatus(); drawLegend(); drawYear();
    drawResults();
  }

  /* ---------- painting ---------- */
  const ovL = document.createElement('canvas'), ovE = document.createElement('canvas');
  [ovL, ovE].forEach(c => { c.width = 360 * PXD; c.height = 180 * PXD; });
  const xE = ovE.getContext('2d'), img = xE.createImageData(ovE.width, ovE.height), buf = new Uint32Array(img.data.buffer);
  function ring(x, body, lat, lon, km, stroke, fill){
    const d = km / R_KM[body], p1 = toRad(lat), l1 = toRad(lon), pts = [];
    for (let b = 0; b <= 360; b += 4){
      const br = toRad(b), p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(br));
      const l2 = l1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
      pts.push([((l2 * 180 / Math.PI + 540) % 360) * PXD, (90 - p2 * 180 / Math.PI) * PXD]);
    }
    const W = 360 * PXD, wraps = pts.some(p => p[0] < W * .25) && pts.some(p => p[0] > W * .75);
    const q = wraps ? pts.map(p => [p[0] < W / 2 ? p[0] + W : p[0], p[1]]) : pts;
    [0, -W].forEach(sh => { x.beginPath(); q.forEach(([px, py], i) => { if (!i) x.moveTo(px + sh, py); else x.lineTo(px + sh, py); }); x.closePath();
      if (fill){ x.fillStyle = fill; x.fill(); } x.lineWidth = 3; x.strokeStyle = stroke; x.stroke(); });
  }
  function paintMars(){
    const x = ovL.getContext('2d'); x.clearRect(0, 0, ovL.width, ovL.height);
    if (st.area && st.pair === 'mars') ring(x, 'mars', st.area.lat, st.area.lon, AREA_KM, 'rgba(255,190,120,.95)', 'rgba(255,170,90,.18)');
    if (gL) gL.setOverlay(st.pair, ovL);
  }
  function paintEarth(){
    buf.fill(0);
    const n = E.n, W = ovE.width, s = E.px, change = st.year !== Y0 && st.show === 'change', span = (hi - lo) || 1;
    for (let i = 0; i < n; i++){
      let c = 0;
      if (change){
        if (OK[i] && OK0[i]){ const k = Math.round(((S[i] - S0[i]) / dmax + 1) * 127.5); c = LUT_DIV[k < 0 ? 0 : k > 255 ? 255 : k]; }
        else if (OK[i]) c = PX_FRESH; else if (OK0[i]) c = PX_LOST;
      } else if (OK[i]){ const k = Math.round((S[i] - lo) / span * 255); c = LUT_SIM[k < 0 ? 0 : k > 255 ? 255 : k]; }
      if (!c) continue;
      const o = E.y[i] * W + E.x[i];
      for (let dy = 0; dy < s; dy++){ const r = o + dy * W; for (let dx = 0; dx < s; dx++) buf[r + dx] = c; }
    }
    xE.putImageData(img, 0, 0);
    const j = st.sel >= 0 ? st.sel : top[0];
    if (j !== undefined && j >= 0) ring(xE, 'earth', E.lat[j], E.lon[j], 60, 'rgba(255,255,255,.95)', null);
    if (gE) gE.setOverlay('earth', ovE);
  }
  function drawLegend(){
    TT.clear(legend);
    if (!st.area || st.pair !== 'mars') return;
    const fut = st.year !== Y0;
    if (fut){
      const seg = h('div', {class:'seg s-mode', role:'radiogroup', 'aria-label':'Map shows'});
      [['change', 'Change since today'], ['score', 'Similarity']].forEach(([id, label]) => seg.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': st.show === id,
        onclick: () => { st.show = id; update(true); }}, label)));
      legend.appendChild(seg);
    }
    if (fut && st.show === 'change'){
      const bar = h('span', {class:'f-ramp', style:{background:'linear-gradient(90deg,rgb(255,150,40),rgba(150,150,160,.5),rgb(70,150,255))'}});
      legend.append(h('span', null, 'less like Mars'), bar, h('span', null, 'more like Mars'));
    } else {
      const bar = h('span', {class:'f-ramp', style:{background:`linear-gradient(90deg,${[0, .4, .65, .82, 1].map(t => rgba(ramp(t)).replace(/,[\d.]+\)$/, ',1)')).join(',')})`}});
      legend.append(h('span', null, 'Similarity'), h('span', null, Math.round(lo * 100)), bar, h('span', null, Math.round(hi * 100)));
    }
    if (fut){
      let lost = 0, fresh = 0; for (let i = 0; i < E.n; i++){ if (OK0[i] && !OK[i]) lost++; else if (!OK0[i] && OK[i]) fresh++; }
      legend.append(h('span', {class:'lg-key lost'}, lost.toLocaleString() + ' test sites lost'), h('span', {class:'lg-key fresh'}, fresh.toLocaleString() + ' new'));
    }
  }

  /* ---------- markers and the arc between the globes ---------- */
  function pushMarkers(){
    if (!gE) return;
    const key = top.join(',') + '|' + st.sel;
    if (key === markerKey) return; markerKey = key;
    gE.setMarkers(top.map(i => ({id: String(i), lat: E.lat[i], lon: E.lon[i], body:'earth', kind:'analog'})));
    gE.setSelection(String(st.sel >= 0 ? st.sel : top[0]), []);
  }
  let linkT0 = 0, linkRaf = 0;
  const NS = 'http://www.w3.org/2000/svg';
  const pathEl = document.createElementNS(NS, 'path'), dotA = document.createElementNS(NS, 'circle'), dotB = document.createElementNS(NS, 'circle'), spark = document.createElementNS(NS, 'circle');
  pathEl.setAttribute('class', 'lk-path'); [dotA, dotB].forEach(d => { d.setAttribute('r', '4'); d.setAttribute('class', 'lk-dot'); }); spark.setAttribute('r', '3.5'); spark.setAttribute('class', 'lk-spark');
  link.append(pathEl, dotA, dotB, spark);
  function linkFrame(){
    linkRaf = 0; if (dead) return;
    const j = st.sel >= 0 ? st.sel : top[0];
    if (!st.area || j === undefined || st.pair !== 'mars' || !gL){ link.style.opacity = '0'; linkRaf = requestAnimationFrame(linkFrame); return; }
    const box = globes.getBoundingClientRect();
    const at = (g, cv, la, lo) => { const s = g.screenOf(la, lo), r = cv.getBoundingClientRect(); return {x: r.left - box.left + s.x, y: r.top - box.top + s.y, v: s.visible}; };
    const a = at(gL, cvL, st.area.lat, st.area.lon), b = at(gE, cvE, E.lat[j], E.lon[j]), t = (performance.now() - linkT0) / 1000;
    if (!a.v || !b.v) link.style.opacity = '0';
    else {
      link.style.opacity = '1';
      const mx = (a.x + b.x) / 2, my = Math.min(a.y, b.y) - 90 - Math.abs(b.x - a.x) * .08;
      pathEl.setAttribute('d', `M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`);
      const len = pathEl.getTotalLength(), k = Math.min(1, t / 1.1), e = 1 - Math.pow(1 - k, 3);
      pathEl.style.strokeDasharray = len; pathEl.style.strokeDashoffset = String(len * (1 - e));
      dotA.setAttribute('cx', a.x); dotA.setAttribute('cy', a.y); dotB.setAttribute('cx', b.x); dotB.setAttribute('cy', b.y);
      dotB.style.opacity = String(Math.max(0, (k - .85) / .15));
      const sp = pathEl.getPointAtLength(len * ((t * .45) % 1)); spark.setAttribute('cx', sp.x); spark.setAttribute('cy', sp.y);
      spark.style.opacity = k < 1 ? '0' : '.9';
    }
    linkRaf = requestAnimationFrame(linkFrame);
  }
  function restartLink(){ linkT0 = performance.now(); if (!linkRaf) linkRaf = requestAnimationFrame(linkFrame); }

  function select(i, fly, keepLink){
    if (!(i >= 0)) return;
    st.sel = i; markerKey = ''; pushMarkers(); paintEarth(); drawResults();
    if (fly) gE.focus(E.lat[i], E.lon[i], {dist:2.6});
    if (!keepLink) restartLink();
  }

  /* ---------- panel ---------- */
  function build(){
    ui = {};
    ui.areaBox = h('div', {class:'area'});
    ui.results = h('div', {class:'list'}); ui.resHead = h('h3', null, 'Best matches on Earth');
    ui.presetBox = h('div', {class:'f-presets sm'}); ui.verdict = h('p', {class:'note one'});
    ui.sliders = h('div', {class:'prs'});
    const dryInp = h('input', {type:'checkbox', class:'ck', id:'f-dry', checked: st.dry, onchange: e => { st.dry = e.target.checked; rescoreToday(); update(true); }});
    TT.clear(scroll);
    scroll.append(ui.areaBox, h('section', {class:'fsec', id:'f-results'}, ui.resHead, ui.results),
      h('details', {class:'fsec tune'}, h('summary', null, 'Mission and weights'),
        ui.presetBox, ui.verdict, ui.sliders,
        h('label', {class:'f-switch', for:'f-dry'}, dryInp, h('span', null, 'Only dry, bare land on Earth'))));
  }
  function drawArea(){
    TT.clear(ui.areaBox);
    if (st.pair === 'moon'){
      ui.areaBox.append(h('div', {class:'kicker k-moon'}, 'Moon preview'), h('h1', null, 'Lunar base sites'),
        h('p', {class:'lede'}, 'The Moon has no data grid yet, so it cannot be compared. Planned and proposed sites:'));
      const list = h('div', {class:'list'});
      MOON_SITES.forEach(s => list.appendChild(h('button', {class:'f-site moon', type:'button', 'aria-current': st.moonSel === s.id ? 'true' : null,
        onclick: () => { st.moonSel = s.id; gL.focus(s.lat, s.lon, {dist:2.2}); gL.setMarkers(MOON_SITES.map(m => ({id: m.id, lat: m.lat, lon: m.lon, body:'moon', kind: m.kind}))); gL.setSelection(s.id, []); drawArea(); }},
        h('span', {class:'f-name'}, h('span', {class:'f-nm'}, s.name), h('span', {class:'f-why'}, s.note + ', ' + TT.fmtCoord(s.lat, s.lon, 1))))));
      ui.areaBox.append(list); return;
    }
    const a = st.area;
    if (!a){ ui.areaBox.append(h('h1', null, 'Pick an area on Mars'), h('p', {class:'lede'}, 'Click anywhere on Mars. Earth shows where it is most alike.')); return; }
    ui.areaBox.append(h('div', {class:'kicker k-mars'}, 'Your area on Mars'), h('h1', null, a.label || TT.fmtCoord(a.lat, a.lon, 1)),
      h('p', {class:'lede'}, (a.label ? TT.fmtCoord(a.lat, a.lon, 1) + '. ' : '') + 'The ground within ' + AREA_KM + ' km is averaged and compared with every place on Earth. Click elsewhere on Mars to compare another area.'));
  }
  function drawPresets(){
    TT.clear(ui.presetBox);
    st.m.presets.forEach(p => ui.presetBox.appendChild(h('button', {class:'chip', type:'button', 'aria-pressed': st.preset === p.id, title: p.name + '. ' + p.mission,
      onclick: () => { applyPreset(p); st.sel = -1; drawPresets(); drawSliders(); rescoreToday(); update(true); }}, SHORT[p.name] || p.name)));
    const p = st.m.presets.find(x => x.id === st.preset);
    ui.verdict.textContent = !p ? 'Your own weights.' : p.name + (p.weights_used === 'calibrated' ? ', tuned on known analogs.' : ', science team weights.');
  }
  const retune = TT.debounce(() => { rescoreToday(); update(true); }, 60);
  function drawSliders(){
    TT.clear(ui.sliders);
    cats().forEach(c => {
      const id = 'w-' + c.id, na = !!st.area && noData(c), on = st.on[c.id] && !na;
      const val = h('output', {for:id}, na ? 'n/a' : on ? (st.cw[c.id] || 0).toFixed(1) : 'off');
      const box = h('input', {type:'checkbox', class:'ck', id:'on-' + c.id, checked: on, disabled: na, 'aria-label':'Use ' + c.label,
        onchange: e => { st.on[c.id] = e.target.checked; if (e.target.checked && !(st.cw[c.id] > 0)) st.cw[c.id] = 2.5; st.preset = null; drawPresets(); drawSliders(); retune(); }});
      const inp = h('input', {id, type:'range', min:'0', max:'5', step:'0.5', value:String(on ? st.cw[c.id] || 0 : 0), class:'f-range', disabled: na, 'aria-label': c.label + ' weight',
        oninput: e => { const v = +e.target.value; st.cw[c.id] = v; st.on[c.id] = v > 0; box.checked = v > 0; val.textContent = v > 0 ? v.toFixed(1) : 'off'; row.classList.toggle('off', !(v > 0));
          if (st.preset){ st.preset = null; drawPresets(); } retune(); }});
      const row = h('div', {class:'pr' + (on ? '' : ' off'), title: na ? 'No data in this area' : null}, box, h('label', {for:'on-' + c.id}, c.label), inp, val);
      ui.sliders.appendChild(row);
    });
  }
  function placeName(i){ return REGION[(Math.floor(E.lat[i]) + .5) + ',' + (Math.floor(E.lon[i]) + .5)] || TT.fmtCoord(E.lat[i], E.lon[i], 1); }
  function moveTag(i, rank){
    if (st.year === Y0) return null;
    if (!OK0[i]) return h('span', {class:'mv up'}, 'new');
    const was = rankOf(S0, OK0, i), d = was - rank;
    return d ? h('span', {class:'mv ' + (d > 0 ? 'up' : 'down'), title:'Rank ' + was + ' today'}, (d > 0 ? '▲' : '▼') + Math.abs(d)) : h('span', {class:'mv'}, '=');
  }
  function siteRow(i, pos){
    return h('button', {class:'f-site', type:'button', 'aria-current': st.sel === i ? 'true' : null, onclick: () => select(i, true)},
      h('span', {class:'f-pos'}, pos),
      h('span', {class:'f-name'}, h('span', {class:'f-nm'}, placeName(i), !OK0[i] && st.year !== Y0 ? h('span', {class:'badge derived'}, 'new') : null),
        h('span', {class:'f-bar'}, h('i', {style:{width: pct(S[i]) + '%'}}))),
      h('span', {class:'f-score'}, pct(S[i]), moveTag(i, pos)));
  }
  function drawResults(){
    TT.clear(ui.results);
    if (st.pair === 'moon'){ ui.resHead.textContent = ''; return; }
    if (!st.area || !E){ ui.resHead.textContent = 'Best matches on Earth'; ui.results.append(h('p', {class:'note'}, 'Loading…')); return; }
    if (st.sel >= 0){ ui.resHead.textContent = 'Selected place on Earth'; drawCard(st.sel); return; }
    ui.resHead.textContent = 'Best matches on Earth' + (st.year === Y0 ? '' : ' in ' + st.year);
    if (!top.length){ ui.results.append(h('p', {class:'note'}, 'No place passes. Switch a parameter back on or allow all land (Mission and weights).')); return; }
    top.slice(0, 5).forEach((i, k) => ui.results.appendChild(siteRow(i, k + 1)));
  }
  function drawCard(i){
    if (!P) return;
    const ok = OK[i], rank = ok ? rankOf(S, OK, i) : null, V = Vnow || todayView();
    const cw = effectiveCW(), fwE = effectiveFW(), th = st.m.thresholds || {strong_at_least:75, weak_at_most:40};
    const catScore = {};
    cats().forEach(c => { let num = 0, den = 0; P.forEach(p => { const f = st.m.features.find(x => x.id === p.id); if (f.category !== c.id) return;
      const s = simOf(p, V, i), a = Math.max(0, +(fwE[p.id] ?? 1)); if (s === s && a > 0){ num += a * s; den += a; } }); catScore[c.id] = den ? num / den : null; });
    const bars = cats().filter(c => cw[c.id] > 0 && catScore[c.id] != null).map(c => { const s = catScore[c.id] * 100;
      return h('div', {class:'f-cat'}, h('span', null, c.label), h('span', {class:'f-bar ' + (s >= th.strong_at_least ? 'good' : s > th.weak_at_most ? 'mid' : 'low')}, h('i', {style:{width: Math.max(2, s) + '%'}})), h('span', null, Math.round(s))); });
    const valOf = (f) => { const c = V.col[f.id], v = c[i];
      if (f.kind === 'scalar') return v !== v ? null : v; if (f.kind === 'boolean') return v < 0 ? null : v === 1; return v < 0 ? null : E.codes[f.id][v]; };
    const rows = st.m.features.map(f => { const a = show(f, st.area.values[f.id]), b = show(f, valOf(f));
      return (a == null && b == null) ? null : h('tr', null, h('td', null, f.label.replace(' (proxy)', '').replace(' (rank within planet)', '')), h('td', null, a == null ? '–' : a), h('td', null, b == null ? '–' : b)); }).filter(Boolean);
    const why = !ok ? (OK0[i] && st.year !== Y0 ? 'No longer a test site in ' + st.year + ': ' + (!V.dry[i] ? 'too wet or green.' : 'its ground ice is gone.') : (!V.dry[i] ? 'Not dry, bare land.' : 'Missing data or no ground ice.')) : null;
    const fresh = ok && !OK0[i] && st.year !== Y0;
    TT.append(ui.results, [
      h('button', {class:'btn ghost sm back', type:'button', onclick: () => { st.sel = -1; markerKey = ''; pushMarkers(); paintEarth(); drawResults(); restartLink(); }}, 'All matches'),
      h('div', {class:'f-card-head'},
        h('div', null, h('h4', null, placeName(i)),
          h('div', {class:'meta'}, (rank ? 'Rank ' + rank + ' of ' + nOk.toLocaleString() + ', ' : '') + TT.fmtCoord(E.lat[i], E.lon[i], 2))),
        h('div', {class:'f-big'}, h('b', null, pct(S[i])), h('span', null, '/100'))),
      st.year !== Y0 && OK0[i] ? h('p', {class:'meta'}, 'Today ' + pct(S0[i]) + ', in ' + st.year + ' ' + pct(S[i]) + '.') : null,
      why ? h('span', {class:'badge derived'}, why) : null,
      fresh ? h('span', {class:'badge measured'}, 'New test site by ' + st.year) : null,
      h('div', {class:'f-group'}, h('div', {class:'meta'}, 'Match by parameter'), bars),
      rows.length ? h('table', {class:'cmp'}, h('thead', null, h('tr', null, h('th', null, ''), h('th', null, 'Mars area'), h('th', null, st.year === Y0 ? 'This place' : 'Here in ' + st.year))), h('tbody', null, rows)) : null,
      hiresBlock(E.lat[i], E.lon[i])]);
  }
  function hiresBlock(lat, lon){
    const site = st.hires && st.hires.sites.find(s => Math.abs(s.lat - lat) <= .5 && Math.abs(s.lon - lon) <= .5);
    if (!site || !site.today) return null;
    const ss = Object.keys(site.scenarios || {}); if (!ss.length) return null;
    const sc = ss.includes(st.scen) ? st.scen : ss[0], yrs = Object.keys(site.scenarios[sc]).sort();
    const cols = [['Today', site.today]].concat(yrs.map(y => [y, site.scenarios[sc][y]]));
    const f = (v, d) => v == null ? '–' : (+v).toFixed(d);
    const row = (label, key, d, unit) => h('tr', null, h('td', null, label), cols.map(([, v], k) => h('td', {class: k && v[key] != null && cols[0][1][key] != null ? (v[key] > cols[0][1][key] ? 'up' : v[key] < cols[0][1][key] ? 'down' : '') : ''}, f(v[key], d) + (unit || ''))));
    const map = site.maps && site.maps[sc], nm = cols[cols.length - 1][1].n_models;
    return h('div', {class:'hr'},
      h('h4', null, 'Inside this area', h('span', {class:'km'}, '1 km')),
      h('p', {class:'meta'}, 'Today and projected, ' + sspName(sc) + (nm ? ', mean of ' + nm + ' model' + (nm > 1 ? 's' : '') : '') + '.'),
      h('table', null, h('thead', null, h('tr', null, h('th', null, ''), cols.map(([y]) => h('th', null, y)))),
        h('tbody', null, row('Air temperature', 'tmean_C', 1, ' °C'), row('Day–night swing', 'air_temp_swing_K', 1, ' °C'), row('Rain per year', 'precip_mm_yr', 0, ' mm'),
          site.today.tmean_C < 0 ? row('Cold-desert share', 'share_cold_desert_pct', 0, ' %') : row('Hyper-arid share', 'share_hyperarid_pct', 0, ' %'),
          row('Dry enough for Mars', 'share_mars_dry_pct', 0, ' %'))),
      map ? h('a', {href: DATA + 'hires/' + map, target:'_blank', rel:'noopener'}, h('img', {src: DATA + 'hires/' + map, alt:'1-km maps of temperature and aridity, today and projected', loading:'lazy'})) : null);
  }

  /* ---------- planets at the foot of the panel ---------- */
  function drawOrbs(){
    TT.clear(orbs);
    [['mars', 'Mars'], ['moon', 'Moon']].forEach(([id, name]) => orbs.appendChild(
      h('button', {type:'button', role:'radio', class:'orb-b', 'aria-checked': (id === st.pair), title: id === 'mars' ? 'Mars' : 'Moon preview',
        onclick: () => setPair(id)}, h('i', {class:'orb orb-' + id}), h('span', null, name))));
  }
  function setPair(id){
    if (id === st.pair) return;
    st.pair = id;
    if (id === 'moon'){ gL.setBody('moon'); gL.focus(-60, 20, {dist:3.35}); gL.setMarkers(MOON_SITES.map(m => ({id: m.id, lat: m.lat, lon: m.lon, body:'moon', kind: m.kind}))); }
    else { gL.setBody('mars'); gL.setMarkers([]); if (st.area) gL.focus(st.area.lat, st.area.lon, {dist:3.35}); }
    paintMars(); drawOrbs(); drawArea(); drawResults(); drawStatus(); drawLegend();
    link.style.opacity = '0';
  }

  /* ---------- the year: a ratchet from today to 2090 ---------- */
  function drawBand(){
    TT.clear(band);
    const ticks = h('div', {class:'yr-ticks', 'aria-hidden':'true'});
    for (let y = Y0; y <= Y1; y++){ const major = y % 10 === 0 || y === Y0;
      ticks.appendChild(h('i', {class: major ? 'mj' : '', style:{left: ((y - Y0) / (Y1 - Y0) * 100) + '%'}}, major ? h('span', null, y === Y0 ? 'Today' : y) : null)); }
    ui.range = h('input', {type:'range', class:'yr-range', min:String(Y0), max:String(Y1), step:'1', value:String(st.year), 'aria-label':'Year on Earth',
      oninput: e => setYear(+e.target.value)});
    ui.play = h('button', {class:'yr-play', type:'button', 'aria-label':'Play the years', onclick: togglePlay});
    ui.yearBig = h('div', {class:'yr-big'});
    const seg = h('div', {class:'tl-scen', role:'radiogroup', 'aria-label':'Climate scenario'});
    scens().forEach(s => seg.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': s === st.scen, title: ((st.m.scenarios || []).find(x => x.id === s) || {}).label || s,
      onclick: () => { st.scen = s; drawBand(); rescoreToday(); update(true); loadScenario(s).then(l => { anchors[s].done = l; rescoreToday(); update(true); }); }}, sspName(s))));
    const track = h('div', {class:'yr-track'}, ticks, ui.range);
    band.append(h('div', {class:'yr'}, ui.play, ui.yearBig, track, seg));
    band.onwheel = e => { e.preventDefault(); setYear(st.year + (e.deltaY > 0 || e.deltaX > 0 ? 1 : -1)); };
    drawYear();
  }
  function drawYear(){
    if (!ui.yearBig) return;
    ui.yearBig.textContent = st.year === Y0 ? 'Today' : st.year;
    ui.yearBig.classList.toggle('future', st.year !== Y0);
    if (+ui.range.value !== st.year) ui.range.value = String(st.year);
    ui.range.style.setProperty('--p', ((st.year - Y0) / (Y1 - Y0) * 100) + '%');
    ui.play.classList.toggle('on', st.playing);
    tagE.textContent = 'Earth' + (st.year === Y0 ? ' today' : ' in ' + st.year);
  }
  function setYear(y){
    y = Math.max(Y0, Math.min(Y1, Math.round(y)));
    if (y === st.year) return;
    st.year = y; drawYear(); requestUpdate();
  }
  let playT = 0;
  function togglePlay(){
    st.playing = !st.playing; drawYear();
    if (!st.playing) return;
    if (st.year >= Y1) setYear(Y0);
    let last = performance.now();
    const step = now => {
      if (!st.playing || dead) return;
      if (now - last >= 110){ last = now; if (st.year >= Y1){ st.playing = false; drawYear(); return; } setYear(st.year + 1); }
      playT = requestAnimationFrame(step);
    };
    playT = requestAnimationFrame(step);
  }

  function drawStatus(){
    tagL.textContent = st.pair === 'moon' ? 'Moon (preview)' : 'Mars';
    if (st.pair === 'moon'){ status.textContent = 'Moon, ' + MOON_SITES.length + ' candidate base sites'; return; }
    if (!st.area){ status.textContent = ''; return; }
    const n = nOk.toLocaleString() + (st.dry ? ' dry, bare' : '') + ' places on Earth ranked against ' + (st.area.label || 'your area') + '.';
    if (st.year === Y0 || !stats){ status.textContent = n; return; }
    const c = stats;
    status.textContent = 'Earth in ' + st.year + ' (' + sspName(st.scen) + '): the coldest ground is ' + c.warm.toFixed(1) + ' °C warmer on average, permafrost thaws in ' + c.thaw.toLocaleString()
      + ' places, ' + c.wet.toLocaleString() + ' become too wet and ' + c.dry.toLocaleString() + ' turn dry. ' + n;
  }

  /* hook for the demo recorder and tests */
  TT.finder = {pickArea, setYear, select: i => select(i, true), play: togglePlay, state: st, top: () => top};

  /* ---------- start ---------- */
  build(); drawOrbs();
  load('manifest.json').then(async m => {
    if (dead) return; st.m = m; st.scen = m.scenario || scens()[0] || null;
    applyPreset(m.presets[0]);
    E = buildEarth(await load(m.files.earth.now)); delete cache[m.files.earth.now];
    drawPresets(); drawSliders(); drawBand();
    await pickArea(START.lat, START.lon, START.label);
    if (m.files.hires) load(m.files.hires).then(d => { st.hires = d; if (st.sel >= 0) drawResults(); }).catch(() => {});
    loadScenario(st.scen).then(l => { anchors[st.scen].done = l; rescoreToday(); if (st.year !== Y0) update(true); }).catch(e => console.error(e));
  }).catch(e => { console.error(e); TT.clear(scroll); scroll.append(h('h1', null, 'No data'), h('p', {class:'lede'}, 'The analog data could not be loaded. Start the app with the start file.')); });

  return { destroy(){ dead = true; TT.finder = null; st.playing = false; if (linkRaf) cancelAnimationFrame(linkRaf); if (raf) cancelAnimationFrame(raf); gL && gL.dispose(); gE && gE.dispose(); } };
};
})();
