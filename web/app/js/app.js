/* Planalogy — shell and hash router. Two pages: the Analog Finder and About. */
(function(){
const TT = window.TT;
TT.pages = TT.pages || {};
const main = TT.$('#main'), nav = TT.$('#nav');
TT.$('#skip').addEventListener('click', () => TT.focusMain());

const parse = () => (location.hash || '').replace(/^#/, '') === 'about' ? 'about' : 'finder';
const titles = {finder:'Planalogy — Analog Finder', about:'About — Planalogy'};
let current = null, first = true;
function route(){
  if (current && current.destroy){ try { current.destroy(); } catch(e){ console.error(e); } }
  current = null;
  const name = parse(); TT.clear(main); window.scrollTo(0, 0);
  document.title = titles[name]; document.body.dataset.route = name;
  nav.querySelectorAll('.top-link').forEach(a => { a.hidden = a.dataset.r === name; });
  try { current = TT.pages[name](main) || null; }
  catch(e){ console.error(e); main.appendChild(TT.h('div', {class:'page'}, TT.h('h1', null, 'Something went wrong'), TT.h('p', {class:'muted'}, 'This page failed to load: ' + e.message))); }
  if (!first) TT.focusMain(); first = false;
}
window.addEventListener('hashchange', route);
route();
})();
