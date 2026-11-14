/* Planalogy — shell and hash router. Routes use plain #name hashes (letters, digits, hyphens) so they survive the artifact frame. */
(function(){
const TT = window.TT, h = TT.h;
TT.pages = TT.pages || {};
const main = TT.$('#main'), nav = TT.$('#nav'), menu = TT.$('#menu'), foot = TT.$('#foot');
menu.innerHTML = TT.icons.menu;
/* header menu: view options for the Analog Finder; on small screens it also opens the page links */
const pop = h('div', {class:'glass menu-pop', role:'dialog', 'aria-label':'Options', hidden:true});
document.body.appendChild(pop);
function drawPop(){
  TT.clear(pop);
  const mode = TT.lsGet('planalogy.mode', 'simple') === 'advanced' ? 'advanced' : 'simple';
  const seg = h('div', {class:'seg', role:'radiogroup', 'aria-label':'Analog Finder view'});
  [['simple', 'Simple'], ['advanced', 'Advanced']].forEach(([k, l]) => seg.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': mode === k,
    onclick: () => { TT.lsSet('planalogy.mode', k); window.dispatchEvent(new CustomEvent('planalogy-mode', {detail: k})); drawPop(); }}, l)));
  pop.append(h('h4', null, 'Analog Finder view'), seg,
    h('p', {class:'tiny muted'}, mode === 'simple' ? 'Mars target, mission scenarios and the climate timeline.' : 'Adds category weights, the AI mission and the dry-land filters.'));
}
const closeMenu = () => { pop.hidden = true; nav.classList.remove('open'); menu.setAttribute('aria-expanded', 'false'); };
menu.addEventListener('click', () => {
  if (!pop.hidden){ closeMenu(); return; }
  drawPop(); pop.hidden = false; if (window.innerWidth <= 900) nav.classList.add('open'); menu.setAttribute('aria-expanded', 'true');
});
document.addEventListener('click', e => { if (!pop.hidden && !pop.contains(e.target) && !menu.contains(e.target) && !nav.contains(e.target)) closeMenu(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !pop.hidden){ closeMenu(); menu.focus(); } });
TT.$('#skip').addEventListener('click', () => TT.focusMain());

function parse(){
  const hsh = (location.hash || '').replace(/^#/, '');
  let m;
  if (!hsh || hsh === 'home') return {name:'home'};
  if ((m = hsh.match(/^explore(?:-(earth|moon|mars))?$/))) return {name:'explore', body:m[1] || null};
  if ((m = hsh.match(/^location-([A-Za-z0-9_-]{2,80})$/))) return {name:'detail', id:m[1]};
  if (hsh === 'finder') return {name:'finder'};
  if (hsh === 'compare') return {name:'compare'};
  if (hsh === 'about') return {name:'about'};
  if ((m = hsh.match(/^admin(?:-(locations|assets|sources))?$/))) return {name:'admin', sub:m[1] || 'dashboard'};
  return {name:'home'};
}
let current = null, first = true;
function route(){
  if (current && current.destroy){ try { current.destroy(); } catch(e){ console.error(e); } }
  current = null; closeMenu();
  const r = parse(); TT.clear(main); window.scrollTo(0, 0);
  const page = {finder:TT.pages.finder, home:TT.pages.home, explore:TT.pages.explore, detail:TT.pages.detail, compare:TT.pages.compare, about:TT.pages.about, admin:TT.pages.admin}[r.name];
  const titles = {finder:'Analog Finder — Planalogy', home:'Planalogy — Find Earth\'s Extremes', explore:'Explore — Planalogy', detail:'Location — Planalogy', compare:'Compare — Planalogy', about:'About and methodology — Planalogy', admin:'Admin — Planalogy'};
  document.title = titles[r.name];
  nav.querySelectorAll('a').forEach(a => { if (a.dataset.r === r.name || (r.name === 'detail' && a.dataset.r === 'explore')) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  foot.hidden = r.name === 'explore' || r.name === 'admin' || r.name === 'finder';
  try { current = page(main, r) || null; } catch(e){ console.error(e); main.appendChild(h('div', {class:'wrap page'}, h('h1', null, 'Something went wrong'), h('p', {class:'muted'}, 'This page failed to load: ' + e.message), h('a', {class:'btn', href:'#'}, 'Back to home'))); }
  if (!first) TT.focusMain(); first = false;
}
window.addEventListener('hashchange', route);

/* compare counter in the header */
TT.updateCmpBadge = () => { const b = TT.$('#cmpn'), n = TT.Compare.ids.length; b.hidden = !n; b.textContent = n; };
TT.Compare.onChange = TT.updateCmpBadge;
TT.updateCmpBadge();

/* when shared data changes, the current page decides whether to refresh itself */
TT.Store.on(() => { if (current && current.refresh) current.refresh(); });
TT.Caps.on(() => { if (current && current.refresh) current.refresh(); });

route();
TT.Caps.init().catch(e => { console.error(e); TT.Caps.ready = true; TT.Caps.subs.forEach(f => f()); });
})();
