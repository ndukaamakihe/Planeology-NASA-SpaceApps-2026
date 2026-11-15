/* Planalogy — shared helpers. Record text is untrusted (it can come from the shared db), so it is only ever set with textContent. */
(function(){
const TT = window.TT = window.TT || {};
TT.pages = TT.pages || {};

TT.h = function h(tag, attrs){
  const el = document.createElement(tag);
  if (attrs) for (const k in attrs){
    const v = attrs[k];
    if (v == null) continue;
    if (k.slice(0,5) === 'aria-' && typeof v === 'boolean'){ el.setAttribute(k, String(v)); continue; }   // aria states need "true"/"false"
    if (v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;            // trusted static markup only (icons)
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.slice(0,2) === 'on' && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (let i = 2; i < arguments.length; i++) TT.append(el, arguments[i]);
  return el;
};
TT.append = function(el, c){
  if (c == null || c === false) return;
  if (Array.isArray(c)) c.forEach(x => TT.append(el, x));
  else if (c instanceof Node) el.appendChild(c);
  else el.appendChild(document.createTextNode(String(c)));
};
const h = TT.h;
TT.$ = (s, r) => (r || document).querySelector(s);
TT.clear = el => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

const I = (p, extra) => '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"' + (extra||'') + '>' + p + '</svg>';
TT.icons = {
  search: I('<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>'),
  spark: I('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>'),
  plus: I('<path d="M12 5v14M5 12h14"/>'), minus: I('<path d="M5 12h14"/>'),
  reset: I('<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>'),
  rotate: I('<path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/>'),
  grid: I('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'),
  map: I('<path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"/><path d="M9 4v14M15 6v14"/>'),
  globe: I('<circle cx="12" cy="12" r="9"/><path d="M3 12h18"/><path d="M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>'),
  pin: I('<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>'),
  filter: I('<path d="M4 5h16l-6 8v6l-4-2v-4z"/>'),
  info: I('<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>'),
  close: I('<path d="M6 6l12 12M18 6L6 18"/>'),
  compare: I('<path d="M8 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h3M16 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3M12 2v20"/>'),
  copy: I('<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>'),
  menu: I('<path d="M4 7h16M4 12h16M4 17h16"/>'),
  chevron: I('<path d="M9 6l6 6-6 6"/>'),
  check: I('<path d="M5 12l5 5 9-10"/>'),
  edit: I('<path d="M4 20h4L19 9l-4-4L4 16z"/>'),
  trash: I('<path d="M4 7h16M10 7V4h4v3M6 7l1 13h10l1-13"/>'),
  upload: I('<path d="M12 16V4M7 9l5-5 5 5M5 20h14"/>'),
  dash: I('<rect x="3" y="3" width="8" height="10" rx="1.5"/><rect x="13" y="3" width="8" height="6" rx="1.5"/><rect x="13" y="11" width="8" height="10" rx="1.5"/><rect x="3" y="15" width="8" height="6" rx="1.5"/>'),
  list: I('<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>'),
  image: I('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 17l-5-5-9 8"/>'),
  book: I('<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5"/>'),
  eye: I('<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  out: I('<path d="M9 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M16 8l4 4-4 4M20 12H9"/>')
};
TT.icon = name => h('span', {html: TT.icons[name] || '', 'aria-hidden': 'true', style: {display:'inline-flex'}});

/* marker shapes: one drawing routine shared by 3D sprites and the 2D map. Shape + colour, never colour alone. */
TT.KINDS = {
  landing:{label:'Candidate landing', short:'Landing', color:'#6EA8E8', shape:'ring'},
  base:   {label:'Potential base', short:'Base', color:'#E3B25B', shape:'square'},
  analog: {label:'Earth analog', short:'Analog', color:'#6FD0B4', shape:'triangle'},
  user:   {label:'User-selected', short:'Pin', color:'#F4F6FA', shape:'diamond'}
};
TT.drawMarker = function(ctx, kind, x, y, r, opt){
  opt = opt || {};
  const k = TT.KINDS[kind] || TT.KINDS.landing;
  ctx.save(); ctx.translate(x, y);
  ctx.globalAlpha = opt.dim ? .35 : 1;
  ctx.lineJoin = 'round';
  const path = () => {
    ctx.beginPath();
    if (k.shape === 'ring'){ ctx.arc(0,0,r,0,Math.PI*2); }
    else if (k.shape === 'square'){ ctx.rect(-r*.85,-r*.85,r*1.7,r*1.7); }
    else if (k.shape === 'triangle'){ ctx.moveTo(0,-r*1.05); ctx.lineTo(r*1.0,r*.8); ctx.lineTo(-r*1.0,r*.8); ctx.closePath(); }
    else { ctx.moveTo(0,-r*1.1); ctx.lineTo(r*.9,0); ctx.lineTo(0,r*1.1); ctx.lineTo(-r*.9,0); ctx.closePath(); }
  };
  path(); ctx.fillStyle = 'rgba(8,13,27,.82)'; ctx.fill();
  ctx.lineWidth = Math.max(2, r*.34); ctx.strokeStyle = k.color; path(); ctx.stroke();
  ctx.fillStyle = k.color; ctx.beginPath(); ctx.arc(0, k.shape==='triangle'?r*.15:0, r*.26, 0, Math.PI*2); ctx.fill();
  if (opt.selected){
    ctx.globalAlpha = 1; ctx.lineWidth = 2; ctx.strokeStyle = '#F4F6FA';
    ctx.beginPath(); ctx.arc(0,0,r*1.7,0,Math.PI*2); ctx.stroke();
  }
  ctx.restore();
};
TT.markerIcon = function(kind, size){
  size = size || 18;
  const c = document.createElement('canvas'); c.width = c.height = size*2; c.className = 'mk'; c.style.width = c.style.height = size + 'px';
  c.setAttribute('aria-hidden','true');
  TT.drawMarker(c.getContext('2d'), kind, size, size, size*.6);
  return c;
};

/* number & coordinate formatting */
TT.normLon = l => { l = ((l + 180) % 360 + 360) % 360 - 180; return l === -180 ? 180 : l; };
TT.fmtLat = (lat, d) => Math.abs(lat).toFixed(d == null ? 3 : d) + '° ' + (lat < 0 ? 'S' : 'N');
TT.fmtLon = (lon, d) => Math.abs(lon).toFixed(d == null ? 3 : d) + '° ' + (lon < 0 ? 'W' : 'E');
TT.fmtCoord = (lat, lon, d) => TT.fmtLat(lat, d) + ', ' + TT.fmtLon(lon, d);
TT.fmtNum = n => {
  if (n == null || isNaN(n)) return '';
  const a = Math.abs(n);
  if (a >= 1000) return n.toLocaleString('en-US', {maximumFractionDigits:0});
  if (a >= 100) return String(Math.round(n*10)/10);
  if (a >= 10) return String(Math.round(n*100)/100);
  if (a >= 1) return String(Math.round(n*1000)/1000);
  return String(Math.round(n*10000)/10000);
};
TT.haversineKm = (a, b, R) => {
  const d = Math.PI/180, dLat = (b.lat-a.lat)*d, dLon = (b.lon-a.lon)*d;
  const s = Math.sin(dLat/2)**2 + Math.cos(a.lat*d)*Math.cos(b.lat*d)*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.min(1, Math.sqrt(s)));
};
TT.slug = s => String(s||'').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g,'').replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,60);
TT.debounce = (fn, ms) => { let t; return function(){ const a = arguments, c = this; clearTimeout(t); t = setTimeout(() => fn.apply(c, a), ms); }; };
TT.reduced = () => window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
TT.isoDate = () => new Date().toISOString().slice(0,10);
TT.lsGet = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch(e){ return d; } };
TT.lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch(e){} };

/* toasts, modal, confirm */
TT.toast = function(msg, bad){
  let box = TT.$('.toasts');
  if (!box){ box = h('div', {class:'toasts', role:'status', 'aria-live':'polite'}); document.body.appendChild(box); }
  const t = h('div', {class:'toast' + (bad ? ' bad' : '')}, msg);
  box.appendChild(t); setTimeout(() => t.remove(), 3800);
};
TT.modal = function(build, opts){
  opts = opts || {};
  const prev = document.activeElement;
  const scrim = h('div', {class:'scrim', role:'presentation'});
  const dlg = h('div', {class:'glass dialog' + (opts.wide ? ' wide' : ''), role:'dialog', 'aria-modal':'true', 'aria-label': opts.label || 'Dialog', tabindex:'-1'});
  scrim.appendChild(dlg);
  const close = v => { document.removeEventListener('keydown', onKey, true); scrim.remove(); if (prev && prev.focus) prev.focus(); if (opts.onClose) opts.onClose(v); };
  const onKey = e => {
    if (e.key === 'Escape'){ e.stopPropagation(); close(); }
    else if (e.key === 'Tab'){
      const f = dlg.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])');
      if (!f.length) return;
      const a = f[0], z = f[f.length-1];
      if (e.shiftKey && document.activeElement === a){ e.preventDefault(); z.focus(); }
      else if (!e.shiftKey && document.activeElement === z){ e.preventDefault(); a.focus(); }
    }
  };
  scrim.addEventListener('mousedown', e => { if (e.target === scrim) close(); });
  document.addEventListener('keydown', onKey, true);
  build(dlg, close);
  document.body.appendChild(scrim);
  const first = dlg.querySelector('input,select,textarea,button.primary,button') || dlg; first.focus();
  return close;
};
TT.confirm = function(o){
  return new Promise(res => {
    TT.modal((dlg, close) => {
      dlg.append(
        h('h3', null, o.title), h('p', {class:'muted'}, o.body),
        h('div', {class:'acts'},
          h('button', {class:'btn', onclick: () => close()}, o.cancel || 'Cancel'),
          h('button', {class:'btn ' + (o.danger ? 'danger' : 'primary'), onclick: () => { res(true); close(); }}, o.ok || 'Confirm')));
    }, {label:o.title, onClose: v => res(false)});
  });
};

/* status badge for a parameter */
TT.badge = status => h('span', {class:'badge ' + status, title: {measured:'Reported measurement from a cited source', derived:'Derived or inferred, not directly measured', unavailable:'No value in this dataset'}[status]}, status);

TT.focusMain = () => { const m = TT.$('#main'); if (m){ m.setAttribute('tabindex','-1'); m.focus({preventScroll:true}); } };
})();
