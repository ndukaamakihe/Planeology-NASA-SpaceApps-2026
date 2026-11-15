/* Planalogy — 3D globe (three.js) and 2D map (canvas) with the same small interface.
   Marker placement: x = cosφ·cosλ, y = sinφ, z = −cosφ·sinλ (equirectangular texture, longitude 0 at the centre). */
(function(){
const TT = window.TT, h = TT.h;
const D2R = Math.PI / 180;

const TEX = {
  earth:{map:'tex/earth_hd.jpg', bump:'tex/earth_bump.jpg', bumpScale:0.006, spec:'tex/earth_specular_2048.jpg', clouds:'tex/earth_clouds_1024.png', topo:'tex/earth_topo.jpg', glow:0x6EA8E8},
  moon:{map:'tex/moon_nasa.jpg', bump:'tex/moon_1024.jpg', bumpScale:0.012, glow:0x9FB0C8},
  mars:{map:'tex/mars_hd.jpg', bump:'tex/mars_bump_hd.jpg', bumpScale:0.012, glow:0xD18B55}
};
TT.TEX = TEX;

/* image cache shared by 3D and 2D */
const imgs = {};
TT.loadImage = function(url){
  if (!imgs[url]) imgs[url] = new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('Could not load ' + url)); i.src = url; });
  return imgs[url];
};
TT.webgl = (function(){ try { const c = document.createElement('canvas'); return !!(window.THREE && (c.getContext('webgl') || c.getContext('experimental-webgl'))); } catch(e){ return false; } })();

const ll2v = (lat, lon, r) => { const p = lat * D2R, l = lon * D2R; return new THREE.Vector3(r * Math.cos(p) * Math.cos(l), r * Math.sin(p), -r * Math.cos(p) * Math.sin(l)); };
const ease = t => t < .5 ? 4*t*t*t : 1 - Math.pow(-2*t + 2, 3) / 2;

/* ---------------- 3D ---------------- */
function mkTex(img, color, renderer){
  const t = new THREE.Texture(img); t.needsUpdate = true; if (color) t.encoding = THREE.sRGBEncoding;
  t.anisotropy = renderer ? renderer.capabilities.getMaxAnisotropy() : 4; return t;
}
const spriteCache = {};
function spriteMat(kind, dim, sel){
  const key = kind + (dim ? 'd' : '') + (sel ? 's' : '');
  if (!spriteCache[key]){
    const c = document.createElement('canvas'); c.width = c.height = 96; const x = c.getContext('2d');
    TT.drawMarker(x, kind, 48, 48, 22, {dim, selected: sel});
    const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding;
    spriteCache[key] = new THREE.SpriteMaterial({map: t, transparent: true, depthWrite: false, sizeAttenuation: false});
  }
  return spriteCache[key];
}

function makePlanet(body, renderer, onLoad){
  const cfg = TEX[body], g = new THREE.Group(); g.name = body;
  const mat = new THREE.MeshPhongMaterial({color: 0xffffff, shininess: body === 'earth' ? 14 : 2, specular: new THREE.Color(body === 'earth' ? 0x1c2736 : 0x050505)});
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 192, 96), mat); g.add(mesh);
  /* an optional 8k texture (tex/get_textures.py) replaces the built-in one when the graphics card can hold it */
  const hi = (window.PLANALOGY_HI || {})[body], big = renderer && renderer.capabilities.maxTextureSize >= 8192;
  const setMap = img => { mat.map = mkTex(img, true, renderer); mat.needsUpdate = true; onLoad && onLoad(body, 'map'); };
  TT.loadImage(cfg.map).then(img => { if (!mat.map) setMap(img); }).catch(e => onLoad && onLoad(body, 'error', e));
  if (hi && big) TT.loadImage(hi).then(setMap).catch(() => {});
  if (cfg.bump) TT.loadImage(cfg.bump).then(img => { mat.bumpMap = mkTex(img, false, renderer); mat.bumpScale = cfg.bumpScale; mat.needsUpdate = true; }).catch(() => {});
  if (cfg.spec) TT.loadImage(cfg.spec).then(img => { mat.specularMap = mkTex(img, false, renderer); mat.needsUpdate = true; }).catch(() => {});
  const glow = new THREE.Mesh(new THREE.SphereGeometry(1.14, 64, 32), new THREE.ShaderMaterial({
    uniforms: {c: {value: new THREE.Color(cfg.glow)}},
    vertexShader: 'varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
    fragmentShader: 'uniform vec3 c; varying vec3 vN; void main(){ float i = pow(max(0.0, 0.64 - dot(vN, vec3(0.0,0.0,1.0))), 3.2); gl_FragColor = vec4(c, 1.0) * i * 0.75; }',
    side: THREE.BackSide, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false}));
  g.add(glow);
  /* graticule */
  const pts = [];
  for (let lat = -60; lat <= 60; lat += 30) for (let l = 0; l < 360; l += 4){ pts.push(ll2v(lat, l, 1.002), ll2v(lat, l + 4, 1.002)); }
  for (let lon = 0; lon < 360; lon += 30) for (let la = -90; la < 90; la += 4){ pts.push(ll2v(la, lon, 1.002), ll2v(la + 4, lon, 1.002)); }
  const grid = new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({color: 0xA9C7E8, transparent: true, opacity: .22}));
  grid.visible = false; g.add(grid);
  g.userData = {mesh, mat, grid, markers: new THREE.Group(), cfg};
  g.add(g.userData.markers);
  return g;
}
TT.setEarthLayer = function(g, layer, renderer){
  const u = g.userData; if (g.name !== 'earth') return;
  const url = layer === 'topo' ? TEX.earth.topo : TEX.earth.map;
  TT.loadImage(url).then(img => { u.mat.map = mkTex(img, true, renderer); u.mat.needsUpdate = true; });
};
function fillMarkers(group, items, px, H, fov){
  while (group.children.length){ const c = group.children.pop(); }
  const sc = px / H * 2 * Math.tan(fov * D2R / 2);
  const map = new Map();
  items.forEach(it => {
    const s = new THREE.Sprite(spriteMat(it.kind, it.dim, false));
    s.position.copy(ll2v(it.lat, it.lon, 1.004)); s.scale.set(sc, sc, 1); s.renderOrder = 5; s.userData = it; group.add(s); map.set(it.id, s);
  });
  return map;
}
function stars(){
  const n = 1400, a = new Float32Array(n * 3);
  for (let i = 0; i < n; i++){ const v = new THREE.Vector3(Math.random()*2-1, Math.random()*2-1, Math.random()*2-1).normalize().multiplyScalar(40 + Math.random()*30); a.set([v.x, v.y, v.z], i*3); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(a, 3));
  return new THREE.Points(g, new THREE.PointsMaterial({color: 0xcfe0f7, size: .09, transparent: true, opacity: .75, depthWrite: false}));
}

TT.createGlobe = function(canvas, o){
  if (!TT.webgl) return null;
  o = Object.assign({body:'moon', auto:false, minDist:1.1, maxDist:6, dist:3.3, markerPx:30}, o || {});
  let renderer;
  try { renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true, powerPreference:'high-performance'}); } catch(e){ return null; }
  if (!renderer.getContext()) return null;
  renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(40, 1, .02, 200);
  scene.add(camera, stars());
  scene.add(new THREE.AmbientLight(0xaab6cc, .34));
  const sun = new THREE.DirectionalLight(0xfff6ea, 1.32); sun.position.set(-3.2, 1.9, 2.4); camera.add(sun);
  const fill = new THREE.DirectionalLight(0x6f86b0, .18); fill.position.set(3, -1, 1.2); camera.add(fill);
  const planets = {}; let cur = null, items = [], markerMap = new Map(), selId = null, hl = new Set(), W = 1, H = 1, alive = true, pinMode = false;
  const view = {lat: -30, lon: 0, dist: o.dist}; const spin = {lat: 0, lon: 0}; let tween = null, auto = o.auto, drag = null, hover = null, raf = 0;
  const rings = {sel: null, hl: []};
  const ringMat = new THREE.SpriteMaterial({map: (() => { const c = document.createElement('canvas'); c.width = c.height = 128; const x = c.getContext('2d'); x.strokeStyle = '#F4F6FA'; x.lineWidth = 6; x.beginPath(); x.arc(64, 64, 52, 0, 7); x.stroke(); const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; return t; })(), transparent: true, depthWrite: false, sizeAttenuation: false, opacity: .95});

  const api = {
    renderer, camera, view, kind: '3d',
    setBody(body){
      if (!planets[body]) { planets[body] = makePlanet(body, renderer, (b, what, e) => { o.onLoad && o.onLoad(b, what, e); }); scene.add(planets[body]); }
      Object.keys(planets).forEach(k => planets[k].visible = (k === body));
      cur = planets[body]; o.body = body; api.setMarkers(items, true);
    },
    setLayer(layer){ if (cur) TT.setEarthLayer(cur, layer, renderer); },
    setGrid(on){ if (cur) cur.userData.grid.visible = !!on; Object.values(planets).forEach(p => p.userData.grid.visible = !!on); },
    setAuto(b){ auto = b; },
    /* Planalogy: equirectangular canvas (lon -180..180 left to right, lat 90..-90 top to bottom) drawn over a body */
    setOverlay(body, cv){
      if (!planets[body]) { planets[body] = makePlanet(body, renderer, (b, what, e) => { o.onLoad && o.onLoad(b, what, e); }); planets[body].visible = planets[body] === cur; scene.add(planets[body]); }
      const u = planets[body].userData;
      if (cv && u.overlay && u.overlayCv === cv){ u.overlay.material.map.needsUpdate = true; return; }  /* same canvas: only upload the new pixels */
      if (u.overlay){ planets[body].remove(u.overlay); u.overlay.material.map && u.overlay.material.map.dispose(); u.overlay.material.dispose(); u.overlay = null; }
      if (!cv) return;
      const t = new THREE.CanvasTexture(cv); t.encoding = THREE.sRGBEncoding; t.anisotropy = renderer.capabilities.getMaxAnisotropy();
      const m = new THREE.Mesh(new THREE.SphereGeometry(1.0028, 128, 64), new THREE.MeshLambertMaterial({map: t, emissive: 0xffffff, emissiveMap: t, emissiveIntensity: .42, transparent: true, depthWrite: false}));
      m.renderOrder = 3; planets[body].add(m); u.overlay = m; u.overlayCv = cv;
    },
    setMarkers(list, keep){
      items = list; if (!cur) return;
      markerMap = fillMarkers(cur.userData.markers, items.filter(i => i.body === o.body), o.markerPx, H, camera.fov);
      api.setSelection(selId, hl);
    },
    setSelection(id, ids){
      selId = id; hl = new Set(ids || []);
      if (rings.sel){ rings.sel.parent && rings.sel.parent.remove(rings.sel); rings.sel = null; }
      rings.hl.forEach(r => r.parent && r.parent.remove(r)); rings.hl = [];
      if (!cur) return;
      const mk = (it, op) => { const s = new THREE.Sprite(ringMat.clone()); s.material.opacity = op; s.position.copy(ll2v(it.lat, it.lon, 1.0045)); s.renderOrder = 4; s.userData.base = (o.markerPx * 1.7) / H * 2 * Math.tan(camera.fov * D2R / 2); s.scale.set(s.userData.base, s.userData.base, 1); cur.userData.markers.add(s); return s; };
      const sel = items.find(i => i.id === selId && i.body === o.body); if (sel) rings.sel = mk(sel, .95);
      items.forEach(i => { if (hl.has(i.id) && i.id !== selId && i.body === o.body) rings.hl.push(mk(i, .7)); });
    },
    focus(lat, lon, f){
      f = f || {}; const dist = f.dist != null ? f.dist : view.dist;
      lat = Math.max(-89.5, Math.min(89.5, lat));
      let dl = ((lon - view.lon + 540) % 360) - 180;
      const dur = TT.reduced() ? 0 : (f.dur != null ? f.dur : 1100);
      if (!dur){ view.lat = lat; view.lon = view.lon + dl; view.dist = dist; tween = null; return; }
      tween = {t0: performance.now(), dur, a: {lat: view.lat, lon: view.lon, dist: view.dist}, b: {lat, lon: view.lon + dl, dist}};
    },
    zoomBy(k){ tween = null; view.dist = Math.max(o.minDist, Math.min(o.maxDist, view.dist * k)); },
    resetView(dur){ const b = o.body, f = {dist: 3.7, dur}; if (b === 'moon') api.focus(-70, 20, f); else if (b === 'mars') api.focus(15, 60, f); else api.focus(25, 10, f); },
    setPinMode(b){ pinMode = b; canvas.classList.toggle('pin', b); },
    screenOf(lat, lon){
      const v = ll2v(lat, lon, 1.004), vis = v.dot(camera.position) > 1.0005; const p = v.clone().project(camera);
      return {x: (p.x + 1) / 2 * W, y: (1 - p.y) / 2 * H, visible: vis};
    },
    resize(){
      const r = canvas.getBoundingClientRect(); W = Math.max(1, r.width); H = Math.max(1, r.height);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2)); renderer.setSize(W, H, false);
      camera.aspect = W / H; camera.updateProjectionMatrix();
      const sc = o.markerPx / H * 2 * Math.tan(camera.fov * D2R / 2);
      if (cur) cur.userData.markers.children.forEach(s => { const k = s.userData.base ? 1.7 : 1; s.scale.set(sc * k, sc * k, 1); if (s.userData.base) s.userData.base = sc * 1.7; });
    },
    dispose(){ alive = false; cancelAnimationFrame(raf); ro.disconnect(); renderer.dispose(); canvas.removeEventListener('wheel', onWheel); },
    pickAt(x, y, r){
      r = r || 22; let best = null, bd = r * r;
      items.forEach(it => {
        if (it.body !== o.body) return; const s = api.screenOf(it.lat, it.lon); if (!s.visible) return;
        const d = (s.x - x) ** 2 + (s.y - y) ** 2; if (d < bd){ bd = d; best = it; }
      });
      return best;
    },
    sphereAt(x, y){
      if (!cur) return null; const ray = new THREE.Raycaster(); ray.setFromCamera({x: x / W * 2 - 1, y: -(y / H * 2 - 1)}, camera);
      const hit = ray.intersectObject(cur.userData.mesh, false)[0]; if (!hit) return null;
      const p = hit.point; return {lat: Math.asin(p.y / p.length()) / D2R, lon: Math.atan2(-p.z, p.x) / D2R};
    }
  };

  /* interaction */
  const ptrs = new Map(); let pinch = 0, moved = 0, downT = 0;
  const degPerPx = () => Math.min(.3, 2 * (view.dist - 1) * Math.tan(camera.fov * D2R / 2) / H / D2R);
  canvas.addEventListener('pointerdown', e => {
    canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, {x: e.offsetX, y: e.offsetY}); moved = 0; downT = performance.now(); tween = null; spin.lat = spin.lon = 0;
    if (ptrs.size === 2){ const [a, b] = [...ptrs.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); }
    canvas.classList.add('grabbing');
  });
  canvas.addEventListener('pointermove', e => {
    const p = ptrs.get(e.pointerId);
    if (!p){
      if (e.pointerType === 'mouse'){ const it = api.pickAt(e.offsetX, e.offsetY, 16); if ((it && it.id) !== (hover && hover.id)){ hover = it; canvas.classList.toggle('hand', !!it); o.onHover && o.onHover(it, e.offsetX, e.offsetY); } else if (it) o.onHover && o.onHover(it, e.offsetX, e.offsetY); }
      return;
    }
    const dx = e.offsetX - p.x, dy = e.offsetY - p.y; moved += Math.abs(dx) + Math.abs(dy); p.x = e.offsetX; p.y = e.offsetY;
    if (ptrs.size === 2){ const [a, b] = [...ptrs.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y); if (pinch) api.zoomBy(pinch / d); pinch = d; return; }
    const k = degPerPx(); view.lon -= dx * k; view.lat = Math.max(-89.5, Math.min(89.5, view.lat + dy * k)); auto = false;
    spin.lon = spin.lon * .5 - dx * k * .5; spin.lat = spin.lat * .5 + dy * k * .5; p.t = performance.now();
  });
  const end = e => {
    const p = ptrs.get(e.pointerId); ptrs.delete(e.pointerId); pinch = 0; canvas.classList.remove('grabbing');
    if (!p || !p.t || performance.now() - p.t > 90 || TT.reduced()) spin.lat = spin.lon = 0;
    if (p && moved < 6 && performance.now() - downT < 600 && ptrs.size === 0){
      const it = api.pickAt(e.offsetX, e.offsetY, e.pointerType === 'touch' ? 30 : 22);
      if (it) o.onPick && o.onPick(it);
      else { const pt = api.sphereAt(e.offsetX, e.offsetY); if (pinMode && pt) o.onPin && o.onPin(pt.lat, pt.lon); else o.onBlank && o.onBlank(pt); }
    }
  };
  canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', () => { if (hover){ hover = null; canvas.classList.remove('hand'); o.onHover && o.onHover(null); } });
  const onWheel = e => { e.preventDefault(); api.zoomBy(Math.exp(e.deltaY * .0013)); };
  canvas.addEventListener('wheel', onWheel, {passive: false});
  canvas.setAttribute('tabindex', '0');
  canvas.addEventListener('keydown', e => {
    const k = degPerPx() * 24; tween = null; auto = false;
    if (e.key === 'ArrowLeft') view.lon -= k; else if (e.key === 'ArrowRight') view.lon += k;
    else if (e.key === 'ArrowUp') view.lat = Math.min(89.5, view.lat + k); else if (e.key === 'ArrowDown') view.lat = Math.max(-89.5, view.lat - k);
    else if (e.key === '+' || e.key === '=') api.zoomBy(.8); else if (e.key === '-') api.zoomBy(1.25); else return;
    e.preventDefault();
  });

  const ro = new ResizeObserver(() => api.resize()); ro.observe(canvas);
  let last = performance.now();
  function frame(now){
    if (!alive) return; raf = requestAnimationFrame(frame);
    const dt = Math.min(.1, (now - last) / 1000); last = now;
    if (tween){ const t = Math.min(1, (now - tween.t0) / tween.dur), e = ease(t); view.lat = tween.a.lat + (tween.b.lat - tween.a.lat) * e; view.lon = tween.a.lon + (tween.b.lon - tween.a.lon) * e;
      /* fly out a little in the middle of a long trip so the movement reads as travel */
      const arc = Math.abs(tween.b.lon - tween.a.lon) + Math.abs(tween.b.lat - tween.a.lat) > 40 ? Math.sin(Math.PI * e) * .5 : 0;
      view.dist = tween.a.dist + (tween.b.dist - tween.a.dist) * e + arc; if (t >= 1) tween = null; }
    else if (!ptrs.size && (Math.abs(spin.lon) + Math.abs(spin.lat)) > .002){
      const f = Math.pow(.04, dt); view.lon += spin.lon * dt * 60; view.lat = Math.max(-89.5, Math.min(89.5, view.lat + spin.lat * dt * 60)); spin.lon *= f; spin.lat *= f; }
    else if (auto && !TT.reduced()) view.lon += 4 * dt;
    view.dist = Math.max(o.minDist, Math.min(o.maxDist, view.dist));
    camera.position.copy(ll2v(view.lat, view.lon, view.dist)); camera.up.set(0, 1, 0); camera.lookAt(0, 0, 0);
    const pulse = 1 + Math.sin(now / 320) * .08;
    if (rings.sel) rings.sel.scale.set(rings.sel.userData.base * pulse, rings.sel.userData.base * pulse, 1);
    rings.hl.forEach(r => r.scale.set(r.userData.base * (1 + Math.sin(now / 260) * .12), r.userData.base * (1 + Math.sin(now / 260) * .12), 1));
    if (!document.hidden) renderer.render(scene, camera);
  }
  api.resize(); api.setBody(o.body); api.resetView(0);
  raf = requestAnimationFrame(frame);
  return api;
};

/* ---------------- hero (three planets, decorative) ---------------- */
TT.createHero = function(canvas, locs){
  if (!TT.webgl) return null;
  let renderer; try { renderer = new THREE.WebGLRenderer({canvas, antialias:true, alpha:true}); } catch(e){ return null; }
  renderer.outputEncoding = THREE.sRGBEncoding;
  const scene = new THREE.Scene(), cam = new THREE.PerspectiveCamera(32, 1, .1, 200); cam.position.set(0, 0, 9);
  scene.add(stars(), new THREE.AmbientLight(0xb8c6e0, .55)); const sun = new THREE.DirectionalLight(0xffffff, 1.15); sun.position.set(-4, 3, 6); scene.add(sun);
  const defs = {earth:{s: 1.7, spin: .035}, moon:{s: .5, spin: .02}, mars:{s: .75, spin: .03}};
  const P = {}; Object.keys(defs).forEach(b => { const g = makePlanet(b, renderer); g.scale.setScalar(defs[b].s); g.rotation.z = b === 'earth' ? .2 : -.1; scene.add(g); P[b] = g;
  });
  let W = 1, H = 1, alive = true, mx = 0, my = 0, raf = 0;
  function layout(){
    const portrait = W / H < 1.0;
    if (portrait){ P.earth.position.set(.5, 1.2, 0); P.moon.position.set(-1.6, -2.7, 1); P.mars.position.set(1.7, -2.9, 0); cam.position.z = 11; }
    else { P.earth.position.set(2.75, -.15, 0); P.mars.position.set(.7, 1.55, -1); P.moon.position.set(.55, -1.45, 0); cam.position.z = 9; }
  }
  const ro = new ResizeObserver(() => { const r = canvas.getBoundingClientRect(); W = Math.max(1, r.width); H = Math.max(1, r.height); renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2)); renderer.setSize(W, H, false); cam.aspect = W / H; cam.updateProjectionMatrix(); layout(); }); ro.observe(canvas);
  canvas.parentElement.addEventListener('pointermove', e => { const r = canvas.getBoundingClientRect(); mx = ((e.clientX - r.left) / r.width - .5); my = ((e.clientY - r.top) / r.height - .5); });
  let last = performance.now(), t0 = last;
  P.moon.rotation.y = 3.0; P.mars.rotation.y = 1.2; P.earth.rotation.y = 2.6;
  (function frame(now){
    if (!alive) return; raf = requestAnimationFrame(frame); const dt = Math.min(.1, (now - last) / 1000); last = now;
    if (!TT.reduced()) Object.keys(P).forEach(b => P[b].rotation.y += defs[b].spin * dt * 3);
    cam.position.x += (mx * .6 - cam.position.x) * .03; cam.position.y += (-my * .4 - cam.position.y) * .03; cam.lookAt(0, 0, 0);
    if (!document.hidden) renderer.render(scene, cam);
  })(last);
  return {dispose(){ alive = false; cancelAnimationFrame(raf); ro.disconnect(); renderer.dispose(); }};
};

/* ---------------- 2D map ---------------- */
function polarImage(img, south, ext, N){
  const sc = document.createElement('canvas'); sc.width = img.naturalWidth; sc.height = img.naturalHeight;
  const sx = sc.getContext('2d', {willReadFrequently: true}); sx.drawImage(img, 0, 0);
  const Wd = sc.width, Ht = sc.height, src = sx.getImageData(0, 0, Wd, Ht).data;
  const out = document.createElement('canvas'); out.width = out.height = N; const ox = out.getContext('2d'); const id = ox.createImageData(N, N), d = id.data;
  for (let j = 0; j < N; j++) for (let i = 0; i < N; i++){
    const x = (i + .5 - N / 2) / (N / 2), y = (N / 2 - (j + .5)) / (N / 2), rho = Math.hypot(x, y); if (rho > 1) continue;
    const colat = rho * ext, lat = south ? -90 + colat : 90 - colat, az = Math.atan2(x, y) / D2R, lon = south ? az : -az;
    const px = Math.min(Wd - 1, Math.max(0, Math.floor(((lon + 180) / 360) * Wd))), py = Math.min(Ht - 1, Math.max(0, Math.floor((90 - lat) / 180 * Ht)));
    const si = (py * Wd + px) * 4, di = (j * N + i) * 4; d[di] = src[si]; d[di+1] = src[si+1]; d[di+2] = src[si+2]; d[di+3] = 255;
  }
  ox.putImageData(id, 0, 0); return out;
}
const polarCache = {};

TT.createMap2D = function(canvas, o){
  o = Object.assign({body:'moon', interactive:true, projection:'equi', ext:30, minPx:26}, o || {});
  const ctx = canvas.getContext('2d'); let layer = 'color', W = 1, H = 1, dpr = 1, img = null, pol = null, items = [], selId = null, hl = new Set(), grid = false, alive = true, need = true, hover = null, pinMode = false, imgW = 4096;
  const v = {lat: 0, lon: 0, ppd: 3, zoom: 1, ox: 0, oy: 0}; let tween = null;
  const polar = () => o.projection === 'polar-s' || o.projection === 'polar-n';
  const south = () => o.projection === 'polar-s';
  const R0 = () => Math.min(W, H) / 2 * .96;
  const minPpd = () => Math.max(W / 360, H / 180);

  function project(lat, lon){
    if (polar()){
      const colat = south() ? lat + 90 : 90 - lat, rho = colat / o.ext, az = (south() ? lon : -lon) * D2R, R = R0() * v.zoom;
      return {x: W / 2 + v.ox + rho * R * Math.sin(az), y: H / 2 + v.oy - rho * R * Math.cos(az), vis: rho <= 1.02};
    }
    let dl = ((lon - v.lon + 540) % 360) - 180;
    return {x: W / 2 + dl * v.ppd, y: H / 2 - (lat - v.lat) * v.ppd, vis: true};
  }
  function unproject(x, y){
    if (polar()){
      const R = R0() * v.zoom, X = (x - W / 2 - v.ox) / R, Y = -(y - H / 2 - v.oy) / R, rho = Math.hypot(X, Y); if (rho > 1) return null;
      const az = Math.atan2(X, Y) / D2R, colat = rho * o.ext; return {lat: south() ? -90 + colat : 90 - colat, lon: TT.normLon(south() ? az : -az)};
    }
    const lat = v.lat - (y - H / 2) / v.ppd; if (Math.abs(lat) > 90) return null;
    return {lat, lon: TT.normLon(v.lon + (x - W / 2) / v.ppd)};
  }
  function clampView(){
    if (polar()) { v.zoom = Math.max(.7, Math.min(24, v.zoom)); return; }
    v.ppd = Math.max(minPpd(), Math.min(imgW / 360 * 6, v.ppd));
    const half = H / 2 / v.ppd; v.lat = half >= 90 ? 0 : Math.max(-90 + half, Math.min(90 - half, v.lat)); v.lon = TT.normLon(v.lon);
  }
  function loadSurface(keep){
    const url = (layer === 'topo' && o.body === 'earth') ? TEX.earth.topo : TEX[o.body].map; if (!keep){ img = null; pol = null; }
    TT.loadImage(url).then(i => {
      img = i; imgW = i.naturalWidth;
      if (polar()){ const key = o.body + o.projection + o.ext; if (!polarCache[key]) polarCache[key] = polarImage(i, south(), o.ext, 1024); pol = polarCache[key]; }
      clampView(); need = true; o.onLoad && o.onLoad(o.body);
    }).catch(() => {});
  }
  function draw(){
    need = false; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = '#050913'; ctx.fillRect(0, 0, W, H);
    if (img){
      if (polar() && pol){
        const R = R0() * v.zoom; ctx.save(); ctx.beginPath(); ctx.arc(W / 2 + v.ox, H / 2 + v.oy, R, 0, 7); ctx.clip();
        ctx.imageSmoothingQuality = 'high'; ctx.drawImage(pol, W / 2 + v.ox - R, H / 2 + v.oy - R, 2 * R, 2 * R); ctx.restore();
        ctx.strokeStyle = 'rgba(169,199,232,.5)'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(W / 2 + v.ox, H / 2 + v.oy, R, 0, 7); ctx.stroke();
      } else if (!polar()){
        const w = 360 * v.ppd, hh = 180 * v.ppd; ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
        for (let k = -1; k <= 1; k++){
          const xL = W / 2 + (-180 + k * 360 - v.lon) * v.ppd, yT = H / 2 - (90 - v.lat) * v.ppd;
          const dx0 = Math.max(0, xL), dx1 = Math.min(W, xL + w), dy0 = Math.max(0, yT), dy1 = Math.min(H, yT + hh); if (dx1 <= dx0 || dy1 <= dy0) continue;
          const sw = img.naturalWidth, sh = img.naturalHeight;
          ctx.drawImage(img, (dx0 - xL) / w * sw, (dy0 - yT) / hh * sh, (dx1 - dx0) / w * sw, (dy1 - dy0) / hh * sh, dx0, dy0, dx1 - dx0, dy1 - dy0);
        }
      }
    }
    if (grid) drawGrid();
    items.forEach(it => { if (it.body !== o.body) return; const p = project(it.lat, it.lon); if (!p.vis || p.x < -20 || p.x > W + 20 || p.y < -20 || p.y > H + 20) return;
      if (hl.has(it.id)){ ctx.strokeStyle = 'rgba(244,246,250,.7)'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, o.minPx * .85, 0, 7); ctx.stroke(); }
      TT.drawMarker(ctx, it.kind, p.x, p.y, o.minPx * .42, {dim: it.dim, selected: it.id === selId}); });
    if (!img){ ctx.fillStyle = '#A6B2C4'; ctx.font = '13px Inter, sans-serif'; ctx.textAlign = 'center'; ctx.fillText('Loading map…', W / 2, H / 2); }
  }
  function drawGrid(){
    ctx.strokeStyle = 'rgba(169,199,232,.25)'; ctx.lineWidth = 1; ctx.beginPath();
    if (polar()){
      const R = R0() * v.zoom, cx = W / 2 + v.ox, cy = H / 2 + v.oy; for (let c = 5; c <= o.ext; c += 5){ ctx.moveTo(cx + R * c / o.ext, cy); ctx.arc(cx, cy, R * c / o.ext, 0, 7); }
      for (let a = 0; a < 360; a += 30){ const r = a * D2R; ctx.moveTo(cx, cy); ctx.lineTo(cx + R * Math.sin(r), cy - R * Math.cos(r)); }
    } else {
      const step = v.ppd > 20 ? 1 : v.ppd > 8 ? 5 : v.ppd > 3 ? 10 : 30;
      for (let lat = -90; lat <= 90; lat += step){ const y = H / 2 - (lat - v.lat) * v.ppd; ctx.moveTo(0, y); ctx.lineTo(W, y); }
      for (let lon = -180; lon <= 180; lon += step){ for (let k = -1; k <= 1; k++){ const x = W / 2 + (lon + k * 360 - v.lon) * v.ppd; ctx.moveTo(x, 0); ctx.lineTo(x, H); } }
    }
    ctx.stroke();
  }
  function tick(now){
    if (!alive) return; requestAnimationFrame(tick);
    if (tween){ const t = Math.min(1, (now - tween.t0) / tween.dur), e = ease(t); for (const k in tween.b) v[k] = tween.a[k] + (tween.b[k] - tween.a[k]) * e; if (t >= 1) tween = null; clampView(); need = true; }
    if (hl.size || selId) need = true;
    if (need) draw();
  }
  const api = {
    kind: '2d', view: v, project, unproject,
    setBody(b){ o.body = b; loadSurface(); need = true; },
    setProjection(p, ext){ o.projection = p; if (ext) o.ext = ext; v.zoom = 1; v.ox = v.oy = 0; loadSurface(); },
    setMarkers(list){ items = list; need = true; },
    setSelection(id, ids){ selId = id; hl = new Set(ids || []); need = true; },
    setGrid(b){ grid = b; need = true; }, setAuto(){}, setLayer(l){ layer = l; if (o.body === 'earth') loadSurface(true); },
    setPinMode(b){ pinMode = b; canvas.classList.toggle('pin', b); },
    focus(lat, lon, f){
      f = f || {}; const dur = TT.reduced() ? 0 : (f.dur != null ? f.dur : 900);
      if (polar()){
        const z = f.zoom || Math.max(v.zoom, 4), p = project(lat, lon), ux = (p.x - W / 2 - v.ox) / v.zoom, uy = (p.y - H / 2 - v.oy) / v.zoom;
        if (!dur){ v.zoom = z; v.ox = -ux * z; v.oy = -uy * z; clampView(); need = true; return; }
        tween = {t0: performance.now(), dur, a: {zoom: v.zoom, ox: v.ox, oy: v.oy}, b: {zoom: z, ox: -ux * z, oy: -uy * z}}; return;
      }
      const ppd = f.ppd || Math.max(v.ppd, W / (f.span || 40)); let dl = ((lon - v.lon + 540) % 360) - 180;
      if (!dur){ v.lat = lat; v.lon = v.lon + dl; v.ppd = ppd; clampView(); need = true; return; }
      tween = {t0: performance.now(), dur, a: {lat: v.lat, lon: v.lon, ppd: v.ppd}, b: {lat, lon: v.lon + dl, ppd}};
    },
    zoomBy(k, cx, cy){
      tween = null; cx = cx == null ? W / 2 : cx; cy = cy == null ? H / 2 : cy;
      if (polar()){ v.zoom /= k; clampView(); need = true; return; }
      const at = unproject(cx, cy); v.ppd /= k; clampView();
      if (at){ v.lon += at.lon - unproject(cx, cy).lon; v.lat += at.lat - unproject(cx, cy).lat; } clampView(); need = true;
    },
    resetView(){ tween = null; if (polar()){ v.zoom = 1; v.ox = v.oy = 0; } else { v.ppd = minPpd() * 1.02; v.lat = o.body === 'moon' ? -40 : 15; v.lon = 0; clampView(); } need = true; },
    screenOf(lat, lon){ const p = project(lat, lon); return {x: p.x, y: p.y, visible: p.vis}; },
    pickAt(x, y, r){ r = r || 20; let best = null, bd = r * r; items.forEach(it => { if (it.body !== o.body) return; const p = project(it.lat, it.lon); const d = (p.x - x) ** 2 + (p.y - y) ** 2; if (p.vis && d < bd){ bd = d; best = it; } }); return best; },
    resize(){ const r = canvas.getBoundingClientRect(); dpr = Math.min(devicePixelRatio || 1, 2); W = Math.max(1, r.width); H = Math.max(1, r.height); canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr); clampView(); need = true; },
    dispose(){ alive = false; ro.disconnect(); }
  };
  if (o.interactive){
    const ptrs = new Map(); let moved = 0, pinch = 0;
    canvas.addEventListener('pointerdown', e => { canvas.setPointerCapture(e.pointerId); ptrs.set(e.pointerId, {x: e.offsetX, y: e.offsetY}); moved = 0; tween = null; canvas.classList.add('grabbing'); if (ptrs.size === 2){ const [a, b] = [...ptrs.values()]; pinch = Math.hypot(a.x - b.x, a.y - b.y); } });
    canvas.addEventListener('pointermove', e => {
      const p = ptrs.get(e.pointerId);
      if (!p){ const it = api.pickAt(e.offsetX, e.offsetY, 16); if ((it && it.id) !== (hover && hover.id)){ hover = it; canvas.classList.toggle('hand', !!it); } o.onHover && o.onHover(it, e.offsetX, e.offsetY); return; }
      const dx = e.offsetX - p.x, dy = e.offsetY - p.y; moved += Math.abs(dx) + Math.abs(dy); p.x = e.offsetX; p.y = e.offsetY;
      if (ptrs.size === 2){ const [a, b] = [...ptrs.values()]; const d = Math.hypot(a.x - b.x, a.y - b.y); if (pinch) api.zoomBy(pinch / d); pinch = d; return; }
      if (polar()){ v.ox += dx; v.oy += dy; } else { v.lon -= dx / v.ppd; v.lat += dy / v.ppd; clampView(); } need = true;
    });
    const end = e => { const p = ptrs.get(e.pointerId); ptrs.delete(e.pointerId); canvas.classList.remove('grabbing');
      if (p && moved < 6 && ptrs.size === 0){ const it = api.pickAt(e.offsetX, e.offsetY, e.pointerType === 'touch' ? 28 : 20); if (it) o.onPick && o.onPick(it); else { const pt = unproject(e.offsetX, e.offsetY); if (pinMode && pt) o.onPin && o.onPin(pt.lat, pt.lon); else o.onBlank && o.onBlank(pt); } } };
    canvas.addEventListener('pointerup', end); canvas.addEventListener('pointercancel', end);
    canvas.addEventListener('pointerleave', () => { hover = null; o.onHover && o.onHover(null); });
    canvas.addEventListener('wheel', e => { e.preventDefault(); api.zoomBy(Math.exp(e.deltaY * .0015), e.offsetX, e.offsetY); }, {passive: false});
    canvas.addEventListener('dblclick', e => api.zoomBy(.5, e.offsetX, e.offsetY));
    canvas.setAttribute('tabindex', '0');
    canvas.addEventListener('keydown', e => { const k = 30 / (polar() ? 1 : v.ppd); if (e.key === '+' || e.key === '=') api.zoomBy(.7); else if (e.key === '-') api.zoomBy(1.4); else if (!polar() && e.key === 'ArrowLeft') v.lon -= k; else if (!polar() && e.key === 'ArrowRight') v.lon += k; else if (!polar() && e.key === 'ArrowUp') v.lat += k; else if (!polar() && e.key === 'ArrowDown') v.lat -= k; else return; clampView(); need = true; e.preventDefault(); });
  }
  const ro = new ResizeObserver(() => api.resize()); ro.observe(canvas);
  api.resize(); v.ppd = minPpd() * 1.02; loadSurface(); requestAnimationFrame(tick);
  return api;
};
})();
