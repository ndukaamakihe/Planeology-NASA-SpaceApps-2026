/* Planalogy — About: what the prototype does, where the data comes from, who built it. */
(function(){
const TT = window.TT, h = TT.h;

/* Edit the team here. linkedin: paste each profile URL; while it is empty the card links to a LinkedIn people search. */
const TEAM = [
  {name:'Aldiyar Zhakyp', role:'UI/UX', does:'Leads the user interface and user experience.', linkedin:''},
  {name:'Daniel Vázquez Piñeiro', role:'Software', does:'Works on the software and application development.', linkedin:''},
  {name:'Jonas Bauer', role:'PM / Storytelling', does:'Coordinates the project and shapes its story.', linkedin:''},
  {name:'Mohamad Alrifai', role:'Data', does:'Leads data collection, processing and climate data integration.', linkedin:''},
  {name:'Nduka Amakihe', role:'Software', does:'Works on the software and application development.', linkedin:''},
  {name:'Wojciech Kaczanowski', role:'Space Science', does:'Contributes the planetary science expertise.', linkedin:''}
];

const STEPS = [
  ['Pick an area on Mars', 'Click anywhere on Mars. Planalogy averages the ground in a circle of 100 km radius around the click.'],
  ['See the match on Earth', 'Every place on Earth is coloured by how closely it resembles your area. Earth turns to the best match, a thin arc links the two places and the match opens.'],
  ['Choose a mission (under Mission and weights)', 'A rover drive, sample science, thermal testing or ice prospecting. Each mission weighs the surface differently.'],
  ['Move through the years', 'The slider under the globes runs from today to 2090, one year at a time, under two climate scenarios; press play to watch it. Earth then shows the change since today: red cells drop out, green cells become new analogs, the rest turns blue or orange as it gets more or less similar.'],
  ['Tune the parameters', 'Switch each parameter on or off and set its weight. The ranking updates at once.']
];

const SOURCES = [
  ['Terrain (slope, roughness, relief)', 'WorldClim 2.1 elevation (SRTM)', 'MOLA, Mars Global Surveyor (NASA)'],
  ['Day–night temperature', 'MODIS land surface temperature (NASA), WorldClim 2.1 air temperature', 'Mars Climate Database v6 (LMD, ESA, CNES)'],
  ['Thermal inertia', 'Computed from albedo and the day–night swing', 'Same formula; TES (NASA) for reference'],
  ['Albedo', 'MODIS MCD43C3 (NASA)', 'TES bolometric albedo (NASA)'],
  ['Mineral groups', 'GLiM rock classes mapped to typical minerals (a proxy)', 'TES mineral maps (NASA), OMEGA (ESA) and CRISM (NASA) hydrated-mineral sites'],
  ['Rock type', 'GLiM global lithological map (Hartmann and Moosdorf 2012)', 'USGS SIM 3292 global geologic map (Tanaka et al. 2014)'],
  ['Impact structure', 'Earth Impact Database', 'Robbins and Hynek 2012 crater database'],
  ['Ground ice', 'Permafrost probability (Obu et al. 2019), glaciers', 'Mars Odyssey GRS hydrogen (NASA), SIM 3292'],
  ['Dry, bare land filter', 'WorldClim 2.1 precipitation, MODIS NDVI', 'Not needed'],
  ['Future climate, 2030 to 2090', 'WorldClim 2.1 CMIP6 projections, mean of six climate models, SSP2-4.5 and SSP5-8.5; about 1 km for selected sites', 'Not projected']
];

const LIMITS = [
  'Similarity is not suitability. A cell is about 28 km wide on Earth and 30 km on Mars, and you compare areas of 100 km radius; check imagery and the literature before naming a site.',
  'Air pressure, sunlight, UV, dust and gravity are never scored. Earth cannot reproduce them.',
  'In the future years air temperature, rain and aridity come from the climate projections. Ground temperatures shift with the air, and permafrost thaws where the mean air temperature rises above −1 °C (a simple threshold rule). Vegetation, glaciers, terrain and rock stay as measured today.',
  'The 1 km maps show a finer picture, not a more exact forecast: the fine pattern comes from today, the change from climate models with cells of 100 km and more.',
  'The Moon is a preview. Its sites are shown, but scoring needs a Moon data grid, which is the next step.'
];

const LI = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="14" height="14" rx="2.5" fill="currentColor"/><path d="M4.4 6.6h1.9v5.2H4.4zM5.35 3.9a1.1 1.1 0 110 2.2 1.1 1.1 0 010-2.2zM7.5 6.6h1.8v.75c.3-.5.95-.9 1.85-.9 1.7 0 2.05 1.05 2.05 2.45v2.9h-1.9V9.2c0-.6-.05-1.3-.85-1.3s-1 .6-1 1.25v2.65H7.5z" fill="#000"/></svg>';
function person(p){
  const url = p.linkedin || 'https://www.linkedin.com/search/results/people/?keywords=' + encodeURIComponent(p.name);
  const a = h('a', {class:'li', href:url, target:'_blank', rel:'noopener', 'aria-label': p.name + ' on LinkedIn'}, h('span', null, p.linkedin ? 'LinkedIn' : 'Find on LinkedIn'));
  a.insertAdjacentHTML('afterbegin', LI);
  return h('div', {class:'person'}, h('b', null, p.name), h('span', {class:'role'}, p.role), h('p', null, p.does), a);
}

TT.pages.about = function(root){
  const page = h('div', {class:'page about'}); root.appendChild(page);
  page.append(
    h('header', {class:'slide-head'}, h('div', {class:'kicker k-about'}, 'About'), h('h1', null, 'Where on Earth is Mars?')),
    h('p', {class:'lede'}, 'Before a rover, a drill or a habitat goes to Mars, it is tested on Earth. Planalogy takes any place on Mars and finds the places on Earth that resemble it most, using the same eight measured properties on both planets. It also looks ahead: as the climate warms, some of today\'s test sites turn greener and new drylands appear, so the best place to build a long-lived test station may not be where it is today.'),
    h('p', {class:'lede'}, 'A student prototype for the NASA Space Apps Challenge 2026, challenge “Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars”.'),

    h('h2', null, 'How to use it'),
    h('ol', {class:'steps5'}, STEPS.map(([t, d]) => h('li', null, h('b', null, t), h('span', null, d)))),

    h('h2', null, 'How the score works'),
    h('p', null, 'Each parameter gives a similarity between 0 and 1 on a fixed scale. The score is their weighted average, shown from 0 to 100. A missing value is never counted as zero; the cell is left out instead. The mission presets set the weights, and one of them was tuned on known analog sites such as the Atacama Desert.'),

    h('h2', null, 'Where the data comes from'),
    h('div', {class:'cmp-scroll'}, h('table', {class:'t'},
      h('thead', null, h('tr', null, ['Parameter', 'Earth', 'Mars'].map(t => h('th', null, t)))),
      h('tbody', null, SOURCES.map(r => h('tr', null, r.map(c => h('td', null, c))))))),
    h('p', {class:'small muted'}, 'All layers were brought to one grid per planet (Earth 0.25°, about 28 km; Mars 0.5°, about 30 km) with the same parameter names on both planets. Globe imagery: Earth from Solar System Scope (CC BY 4.0, based on NASA Blue Marble, summer, snow-free), Mars from NASA 3D Resources, Moon from the NASA CGI Moon Kit (LRO); relief shading from MOLA and WorldClim elevation.'),

    h('h2', null, 'What it cannot tell you'),
    h('ul', null, LIMITS.map(x => h('li', null, x))),

    h('h2', null, 'Team'),
    h('div', {class:'team'}, TEAM.map(person)),
    h('p', null, h('a', {class:'btn primary', href:'#finder'}, 'Open the Analog Finder')));
};
})();
