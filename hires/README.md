# Planalogy at 11 km

This folder rebuilds the Planalogy data at **~11 km cells on both planets** (Earth 0.1°, Mars 0.1875°),
about 100 times finer than the Data team's 1° grid (~110 km). It also contains a local search tool,
the export that runs the app's Analog Finder at 11 km in the browser, and the method and results of an
agent-based search for new Mars analogs.

Everything uses the same engine as the app: the same mission profiles, the same comparators and the same
dry-land rule. Only the cells are smaller.

| | 1° grid (`data/grid_1deg`) | 11 km grid (this folder) |
|---|---|---|
| Earth land cells | 25,628 | 2,128,673 |
| Mars cells | 64,800 | 1,843,200 |
| Mars-like dry land today (rule v2) | 2,553 | 259,212 |
| Cell size | Earth ~111 km, Mars ~59 km | ~11 km on both planets |

## Contents

1. [Layout and setup](#layout-and-setup)
2. [Data sources](#data-sources)
3. [Build pipeline](#build-pipeline)
4. [Validation against the 1° grid](#validation-against-the-1-grid)
5. [Engine and rules at 11 km](#engine-and-rules-at-11-km)
6. [Training the mission profiles at 11 km](#training-the-mission-profiles-at-11-km)
7. [The search tool](#the-search-tool)
8. [The app at 11 km](#the-app-at-11-km)
9. [Search for new analogs (agents and audits)](#search-for-new-analogs-agents-and-audits)
10. [Results](#results)
11. [Limitations and open questions](#limitations-and-open-questions)

## Layout and setup

```
hires/            code (this folder)
hires_data/       downloads and outputs, ~17 GB, ignored by git
  raw/              source files (see Data sources)
  grid_11km/        built grids (*.npz) and the search table (table/*.npy, ~650 MB)
data/grid_1deg/   the Data team's 1° grid, including the ssp245/ and ssp585/ projections
```

Paths can be changed with `PLANALOGY_HIRES_DATA` (default `<repo>/hires_data`) and `PLANALOGY_GRID_1DEG`
(default `<repo>/data/grid_1deg`).

Python 3.11+ with:

```bash
pip install numpy scipy tifffile imagecodecs h5py pyshp pillow
```

All scripts run with `python -I <script>` from any folder.

## Data sources

Every source is public and downloads without an account. `fetch.sh` downloads the large files and resumes
stalled transfers; `fetch_ranges.sh` finishes a slow download with parallel byte ranges. The WorldClim,
TES, impact and lake files are small direct downloads (URLs below).

### Earth

| Layer | Source | Resolution | Size | Used for |
|---|---|---|---|---|
| Elevation | [WorldClim 2.1](https://www.worldclim.org/data/worldclim21.html) `wc2.1_30s_elev` (SRTM based) | 30″ (~0.93 km) | 338 MB | slope, roughness, relief, land mask |
| Climate 1970-2000 | WorldClim 2.1 `wc2.1_2.5m_{tmin,tmax,tavg,prec}`, monthly | 2.5′ (~4.6 km) | 1.4 GB | air temperature mean, minimum and daily swing; precipitation; aridity |
| Ground temperature | MODIS MOD11A2 long-term medians 2000-2017, OpenLandMap ([Zenodo 1435938](https://zenodo.org/records/1435938)): annual day and night, monthly night | 1 km | 4.4 GB of the 33 GB record | ground day-night swing, coldest monthly night |
| Albedo | MODIS blue-sky albedo climatology from 20 years of MODIS ([Zenodo 6350821](https://zenodo.org/records/6350821)), 12 mid-month days | 0.05° | 6 GB zip | albedo, apparent thermal inertia |
| Vegetation | Monthly NDVI from MODIS and AVHRR ([Zenodo 4305975](https://zenodo.org/records/4305975)), the 12 months of 2019 | 5 km | 180 MB | bare-ground test (NDVI < 0.2) |
| Lakes | [Natural Earth](https://www.naturalearthdata.com/) 10 m lakes and reservoirs, with the North America and Europe supplements | vector | 4 MB | water mask |
| Impact structures | Wikipedia "List of impact structures on Earth" (88 with coordinates and diameter), plus Kara-Kul | points | - | inside an impact structure |
| Future climate | The Data team's 1° CMIP6 projections (`data/grid_1deg/ssp245`, `ssp585`, 2030-2090) | 1° | - | change applied to the 11 km climate (delta method) |
| Rock type (+ mineral proxy) | GLiM vector map (Hartmann & Moosdorf 2012), [original GIS data](https://www.geo.uni-hamburg.de/geologie/forschung/aquatische-geochemie/glim.html) | 1,235,259 polygons, ~1:3.75 M | 1.1 GB | rock group and mineral groups (the Data team's class mapping) |
| Ground ice | Permafrost probability, Northern Hemisphere (Obu et al. 2019, [PANGAEA 888600](https://doi.pangaea.de/10.1594/PANGAEA.888600)) | 1 km | 106 MB zip | ground ice = probability ≥ 0.5 or glacier; south of the equator the 1° flag is kept |

### Mars

| Layer | Source | Resolution | Used for |
|---|---|---|---|
| Elevation | MOLA global DEM mosaic, [USGS Astrogeology](https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif) (2.1 GB) | 463 m, averaged 2×2 to 926 m | slope, roughness, relief |
| Albedo | TES bolometric albedo mosaic, [USGS Astrogeology](https://planetarymaps.usgs.gov/mosaic/Mars_MGS_TES_Albedo_mosaic_global_7410m.tif) | 7.4 km | albedo, apparent thermal inertia |
| Geology | Geologic Map of Mars, [SIM 3292](https://pubs.usgs.gov/sim/3292/) (Tanaka et al. 2014), vector | 1:20 M | rock group; polar units for ground ice |
| Craters | Robbins & Hynek 2012 database, 384,343 craters ≥ 1 km, via the [USGS Astrogeology API](https://astrogeology.usgs.gov/pygeoapi/collections/mars/robbinsv1) | points + diameters | inside a crater rim |
| Thermal inertia | TES night map 2007 (Putzig & Mellon), [PDS Geosciences](https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html) | 20 ppd (~3 km) | stored and shown, **not scored** (see Engine) |
| Temperatures, minerals, GRS hydrogen | The Data team's 1° grid (MCD v6 climate model, TES minerals, Odyssey GRS) | 1° (the climate model itself is ~200 km) | bilinear (temperatures) or parent cell |

The Mars ice maps of SWIM (swim.psi.edu) were planned but the site was down on 15 Nov 2026 (HTTP 523) with no
mirror; Mars ground ice uses Odyssey GRS (≥ 10 wt% H2O) plus the SIM 3292 polar units instead. Every source,
with exact file URLs and status, is listed in [`SOURCES.md`](SOURCES.md).

## Build pipeline

Run in this order. Each step writes to `hires_data/grid_11km/`.

| Step | Script | What it does |
|---|---|---|
| 1 | `build_terrain.py earth` / `mars` | Terrain on ~0.93 km pixels, same method on both planets: Earth 30″ DEM, Mars MOLA 463 m averaged 2×2. Each cell holds 12×12 pixels. Writes mean elevation, mean slope (central differences, latitude-corrected), roughness (standard deviation), relief (max - min) and land fraction. |
| 2 | `build_climate.py` | Monthly WorldClim 2.5′: annual mean, coldest-month minimum, mean daily range (tmax - tmin), yearly precipitation. Hargreaves PET per month (FAO-56 extraterrestrial radiation at mid-month) and the UNEP aridity index P / PET, as in the 1° grid. Aggregated to 0.1° by pixel centre. |
| 3 | `build_lst.py` | Ground swing = annual day median - annual night median; coldest night = minimum over the 12 monthly night medians. Values are K × 50; coverage 87.4° N to 62° S. |
| 4 | `build_albedo.py` | Mean of 12 mid-month days of the historical (with snow) blue-sky albedo. |
| 5 | `build_ndvi.py` | 2019 mean of the monthly NDVI over the months with data. |
| 6 | `build_water.py` | Natural Earth lakes rasterised at 0.02° and averaged to a water fraction per 0.1° cell. |
| 7 | `build_fine_classes.py` | Earth rock type and mineral proxy from GLiM (rasterised at 0.02°, majority class per cell) and ground ice from Obu 2019 (5×5 samples per cell); Mars rock group from SIM 3292 (majority unit; impact units keep the 1° group), crater flag from Robbins (cell centre inside a rim, radius at least half a cell) and TES thermal inertia. |
| 8 | `build_earth.py` | Assembles the Earth grid. Rules below. |
| 9 | `build_mars.py` | Assembles the Mars grid: fine terrain, TES albedo, SIM rock group, Robbins craters, ice = GRS ≥ 10 wt% or a polar unit; temperatures bilinear from 1°; minerals from the parent cell; ATI = (1 - albedo) / ground swing. |
| 10 | `build_table.py` | Memory-mapped search table over Earth land cells (one `.npy` per column) with today's climate and every projected year precomputed. |

Rules in `build_earth.py`:

- **Land:** at least half the cell has elevation data and less than half is lake.
- **Ground temperature south of 62° S** (no MODIS data): bilinear from the 1° grid.
- **Albedo:** MODIS between 60° S and 60° N. Poleward, a 12-month mean is biased by the polar night, so the 1° value is used.
- **NDVI:** the 5 km product has gaps over water, snow and much of the high Arctic.
  - Rescaled to the 1° grid's NDVI scale (fit 1° = 0.865 × fine + 0.010; it is a monthly 90th percentile, so it runs high).
  - Gaps are filled from neighbouring cells (3×3, then 5×5), then from the 1° grid.
  - The source is kept per cell in `ndvi_source` (0 own, 1 neighbours, 2 one-degree, 3 none).
- **Rock type and minerals:** GLiM at 11 km; where GLiM has no class, the parent 1° cell (coastal cells take the nearest land parent).
- **Ground ice:** Obu 2019 permafrost (probability ≥ 0.5) or the GLiM glacier class in the Northern Hemisphere; the 1° flag in the south.
- **Inside an impact structure:** the cell centre is within the rim (radius at least half a cell).

Future years (`build_table.py`, and the same formula in the browser), delta method as in the app:

- Air mean, minimum and swing: today's 11 km value + the 1° projected change (bilinear).
- Ground swing moves with the air swing; ground minimum moves with the air minimum.
- Precipitation and aridity: today's 11 km value × the 1° ratio.
- NDVI, albedo, terrain, rock and ice stay as today.

## Validation against the 1° grid

Each new layer was averaged back to 1° and compared with the Data team's grid over land cells:

| Layer | Pearson r | Note |
|---|---|---|
| Air temperature mean, minimum, swing | 1.000 | same source (WorldClim) |
| Precipitation | 0.999 | |
| Aridity index | 0.999 | the dry class (≤ 0.20) agrees on 99.97 % of cells |
| Ground day-night swing | 0.998 | |
| Coldest ground night | 1.000 | |
| NDVI | 0.957 | after rescaling; class < 0.2 agrees on 96 % |
| Albedo (60° S-60° N) | 0.955 | detail gain: Salar de Uyuni 0.50 at 11 km vs 0.36 at 1° |
| Mars albedo | 0.991 | |
| Earth permafrost probability (Obu) | 0.936 | |
| Earth rock group (GLiM) | 92.5 % agree | 1° majority of the 11 km cells |
| Mars rock group (SIM 3292) | 96.9 % agree | |
| Mars thermal inertia (TES 2007) | 0.80 | vs the older TES map (Mellon 2000) in the 1° grid |

Terrain does not match one-to-one, as expected: it depends on cell and pixel size. Slope on 0.93 km
pixels is larger than on ~10 km pixels; relief inside an 11 km cell is smaller than inside a 110 km cell.

## Engine and rules at 11 km

- **Similarity:** adapted Gower, as in `analogue_engine` and `web/app/js/scoring.js`: clipped-linear, categorical, boolean and Jaccard comparators, two-level category and feature weights, the app's four mission profiles (`presets.json`, copied from the 1° manifest).
- **Terrain scales:** the app's τ were set for 110 km cells on ~10 km pixels. Each terrain τ is multiplied by the ratio of the means (11 km / 1°), as the geometric mean of Earth and Mars: slope ×2.59, roughness ×0.373, relief ×0.390. **Provisional.**
- **Mars targets:** the rovers' landing sites, where they actually operate:
  - Bradbury Landing in Gale (-4.59, 137.44);
  - Octavia E. Butler in Jezero (18.44, 77.45);
  - Arcadia Planitia (46.5, -167.5);
  - optionally Oxia Planum (18.16, -24.33, ESA Rosalind Franklin) and Deuteronilus Mensae (43.9, 24.4).
- **Dry land (Science's rule v2):** not ice or water, bare ground (NDVI < 0.2), and either aridity ≤ 0.20 or a cold desert (mean air temperature < 0 °C, precipitation < 250 mm/yr, albedo < 0.6). Where no NDVI exists even after gap filling, only Antarctica counts as bare. Cells with 10 % or more lake water are not dry land (lake shores).
- **Thermal inertia:** scored with the same formula on both planets, apparent thermal inertia = (1 - albedo) / ground day-night swing, as a percentile within each planet. TES physical thermal inertia was tried for Mars and rejected by the third audit: Earth has no physical map, and on Earth the ATI percentile is almost the inverse of the swing (r = -0.91), so a high Mars percentile (Gale is at the 92nd) rewarded polar cells and lake shores with tiny swings.

## Training the mission profiles at 11 km

The app's mission weights are Science's starting weights; only the rover profile had been calibrated, on the
1° grid. At 11 km they were trained again on known analogs.

**First attempt: the engine's method** (`calibrate_hires.py`, report `calibration_11km.json`).

- Method: `analogue_engine.calibration`, vectorised with numpy so it runs on all ~259,000 dry cells.
  - Pairwise logistic loss: every known analog should score above every other cell.
  - KL anchor to Science's weights.
  - Leave-one-out gate.
- Results were mixed:
  - rover with Science's three sites: accepted (+35 %, 2 of 3);
  - rover with 17 catalogued sites: rejected (+1 %);
  - sample science: rejected;
  - ice: no usable site.
- Why: known analogs were chosen for many reasons (access, one special feature, history), so asking each one to beat every cell is too strict. At 11 km the site's point can also fall in an unrepresentative cell.

**Second attempt, used: "look alike", not "rank first"** (`calibrate_soft.py`, report `calibration_soft_11km.json`).

- **A site is an area:** every dry, complete cell within 20 km of its point. The site's score is a soft maximum over those cells.
- **Soft target:** a site only has to reach the top 5 % of cells. Loss = softplus((q - s_site) / T), where q is the score at the top-5 % threshold.
- **Shared features**, a second, closed-form method: weights proportional to w0 · exp(z), where z measures how consistently the known sites look like the Mars target on each feature, compared with all candidates.
- **Labels:** Science's known analogs plus catalogued sites of the matching kind:
  - rover: field-test sites and stations;
  - sample science: evaporite basins and paleolakes;
  - thermal: hyper-arid and high-altitude deserts;
  - ice: polar and permafrost sites.
- **Anchor and gate:** both methods stay anchored to Science's weights, and both pass the engine's gate: hide each site, train on the others, and compare the hidden site's best-cell rank with its rank under Science's weights. Accepted if the mean improves by at least 5 % and at least half of the hidden sites improve.

| Mission | Sites | Method kept | Hidden sites, mean rank | Improved | Sites in top 5 % |
|---|---|---|---|---|---|
| Rover navigation (Gale) | 19 | soft rank | 37,941 → 34,845 (+8 %) | 12 / 19 | 11 → 12 |
| Sample science (Jezero) | 32 | soft rank | 78,438 → 52,213 (+33 %) | 17 / 32 | 8 → 8 |
| Thermal testing (Gale) | 17 | soft rank | 74,649 → 55,100 (+26 %) | 12 / 17 | 5 → 10 |
| Ground-ice ISRU (Arcadia) | 6 | soft rank | 15,147 → 10,693 (+29 %) | 5 / 6 | 0 → 0 |

These are the weights trained on the final data (11 km rock, ice and craters). On the first 11 km build, with
rock and ice still at 1°, Science's weights put the hidden rover sites at a mean rank of 52,802; the 11 km
layers alone bring that to 37,941 before any training.

The trained weights are in `presets_trained_11km.json`; Science's starting weights are in
`science_presets.json`. The tool uses the trained weights by default (`--weights app` for the 1° app
weights), and the 11 km app shows them as "Calibrated on known analogs".

Large shifts for Science to review:

- **Sample science nearly drops rock type** (0.27 → 0.02), even with GLiM at 11 km: its labels (evaporite basins) are classed as evaporites while Jezero is sedimentary, so rock type does not help separate them.
- **Ice relies on the coldest ground temperature and rock type**, and drops slope and albedo.
- **Thermal** keeps the day-night swing as its main feature.

The labels come from the unverified catalog, so the trained weights are evidence of consistency with sites
already in use, not scientific validation.

## The search tool

`planalogy_hires.py` scores all 2.1 M Earth land cells in about 4 s, reading the shared memory-mapped table.

```bash
python -I hires/planalogy_hires.py search --preset rover_navigation --top 15 --exclude-known-km 50 --brief
python -I hires/planalogy_hires.py search --preset sample_science --mars-point 18.16,-24.33 --bbox=-60,75,-170,-30
python -I hires/planalogy_hires.py shift --preset thermal_environment --scenario ssp585 --year 2090 --kind loss
python -I hires/planalogy_hires.py cell --preset ice_prospecting --at 30.75,84.45
python -I hires/planalogy_hires.py known --near 33.3,78.0 --km 200
```

- `search`: best dry cells today.
- `shift`: cells that gain or lose dry-land status in a projected year.
- `cell`: everything about one place.
- `known`: catalogued known analogs nearby.

Each result has:

- score (0-100) and rank among dry cells;
- dry status and rank in 2050 and 2090 under both scenarios, with aridity, temperature and precipitation;
- similarity per feature and the Earth values;
- the nearest catalogued known analog.

Write a `--bbox` that starts with a negative number with `=` (argparse).

`known_analogs.json` lists 245 known Mars analog sites (field-test sites, stations and literature analogs)
used to skip candidates within 50 km of a known one. It was compiled by an agent from general knowledge and
is **not verified** against sources. Coordinates of 41 entries are marked approximate.

## The app at 11 km

The 11 km Earth grid has 2.1 M land cells, too many for the app's JSON tables. The app (`web/app`) now runs
in **compact mode**:

| File | Size | Content |
|---|---|---|
| `cells.json` | 12.4 MB | the 266,044 cells that are Mars-like dry land in at least one year, as base64 typed arrays (`export_web.py`) |
| `deltas.json` | 6.9 MB | the 1° climate changes for each projected year |
| `mars_fine_a.json`, `mars_fine_b.json`, `mars_fine_c.json` | 39 MB | Mars 11 km slope, roughness, relief, albedo, ATI percentile, rock group, ground ice and crater flag |
| `mars.json` | 8.8 MB | the 1° Mars table for everything else |
| `manifest.json` | | 11 km grids, scaled terrain τ, landing-site targets plus Oxia Planum, known analogs as 11 km cell ids, and a `compact` block (`export_app.py`) |

- `web/app/js/compact.js` rebuilds the Finder's usual `{columns, rows}` tables from these files, and future years with the same bilinear delta method as the tool. It keeps a small cache of year tables (~100 MB each).
- `finder.js` has three hooks: the base table, the yearly tables, and picking a Mars point (11 km terrain, albedo, rock, ice and craters over the 1° table).
- Checked in the browser against the tool: 257,208 dry cells today; picking Bradbury Landing gives the same values as the tool.

To build:

```bash
python -I hires/export_web.py <out dir>                 # cells.json, deltas.json, engine.json
python -I hires/export_app.py web/app <out dir>         # turns web/app/data/planalogy into 11 km mode
```

`backend/web_export.py` still writes the 1° version into the same folder; running it again restores the 1° app.

Limits of compact mode:

- Cells that are never dry land are not shipped, so "dry land only" cannot be switched off at 11 km.
- The Finder needs more memory and takes a few seconds to load and to change year.

`atlas/index.html` is the **Analog Atlas** page: a standalone explorer with the same engine, plus the search results below. To rebuild its data:

```bash
python -I hires/export_web.py <atlas>/data
python -I hires/render_layers.py <atlas>/layers [future_ranks.json]
python -I hires/build_atlas.py <audit.json> <atlas>/layers/layers.json <atlas>/data/atlas.json
```

## Search for new analogs (agents and audits)

**Goal:** find Earth sites that are genuinely new as Mars analogs (not in the literature, not used for
tests), useful for a real mission, and ideally gaining or losing analog status with climate change.

**Method:**

1. **Ten search agents, one slice each:**
   - rover navigation in the Americas, in Africa/Europe/the Middle East, and in Asia/Oceania;
   - sample science (Jezero) in the Americas and in the Old World;
   - thermal testing worldwide;
   - ground ice for crewed missions (Arcadia, Deuteronilus, Phlegra, Erebus);
   - ESA's Oxia Planum;
   - climate gains;
   - climate losses.

   Each ran the tool, dropped cells within 50 km of a catalogued analog, searched the web for prior Mars-analog use, checked what is actually in the cell, and kept 3-5 candidates. In total: 42 candidates.
2. **An auditor agent:**
   - re-ran 29 candidate cells (all reproduced except one scout claim), checked neighbouring cells, and searched in English, Chinese, Russian, Mongolian, Persian and Spanish;
   - rejected 28 candidates, with reasons;
   - kept 4 finalists.
3. **The audit found a bug:** cells without NDVI counted as bare ground, so lakes and vegetated Arctic tundra passed as dry land. It is fixed (water mask and NDVI gap filling, see the build pipeline). All numbers below come from the corrected run.
4. **A second audit, under the trained weights:**
   - re-checked about 30 cells, each with 8 neighbours, and searched in English, Chinese and Russian;
   - looked for the best concrete site per mission and for robust climate stories;
   - rejected 20 more candidates.
   - A climate story counts as robust only if it happens by 2050 in both scenarios with a clear margin.
5. **A third audit, on the 11 km rock, ice and crater layers and re-trained weights:**
   - re-checked the new top cells and every previous finalist;
   - found the thermal-inertia problem (TES vs apparent thermal inertia, see Engine), which was fixed before the results below;
   - rejected 26 more candidates; 74 rejections in total, all with reasons.

## Results

Final numbers (11 km rock, ice and craters; trained weights; thermal-inertia fix). Ranks are among the dry
cells for that mission (257,208 today). Ranks change a lot from one cell to the next: read a finalist as the
peak of a good area, not a unique spot.

**Audited finalists** (auditor confidence out of 10):

| Site | Mission | Today | Future | Confidence |
|---|---|---|---|---|
| Yanshuigou / Qiulitag anticlines north of Kuqa, Xinjiang, China (41.85, 82.95) | Rover navigation, Gale | #69 | #66-#71 to 2090 in both scenarios | 6 |
| Western slopes of Cerro Zapaleri, Altiplano, Chile (-22.85, -67.25) | Thermal testing, Gale | #410 | improves: about #260 in 2050, #189-#230 in 2090 | 5 |
| Zhamanshin impact crater, Kazakhstan (48.40, 60.97) | Sample science, Jezero | #61 | #59-#60 to 2090 | 4 |
| Ashikule volcanic basin, West Kunlun, Xinjiang, China (35.75, 81.65) | Ground-ice ISRU, Arcadia | #1 of 22,369 | #1 in every scenario to 2090 | 4 |
| Golfo San Jorge pampa, Chubut, Argentina (-45.35, -67.65) | Sample science, Jezero | not dry (aridity 0.203) | **gain:** dry from 2050 in both scenarios (about #570); rainfall falls | 5 |
| Northern Qilian Shan foothills, Subei County, Gansu, China (39.65, 97.25) | Rover navigation, Gale | #199 | **loss:** not dry from 2050 in both scenarios (mean temperature -0.6 → +2.0 / +2.6 °C); cannot return (aridity > 0.25) | 4 |

Caveats:

- **Kuqa:** layered red beds and salts, a stand-in for Curiosity's clay-to-sulfate traverse. Access to Xinjiang is the weak point.
- **Zapaleri:** a 34 K ground day-night swing at about 4,650 m, reachable by road from San Pedro de Atacama. Ten catalogued analogs lie within 250 km.
- **Zhamanshin:** fits Jezero if its centre really holds lake sediments over impactites (to be checked). NASA GSFC is studying the crater, so it is new as a sampling analog, not unstudied.
- **Ashikule:** a volcanic field with lava flows and salt lakes at about 4,700 m. The engine keeps permafrost as today, so a thaw of the ground is not modelled. Very hard access. The ice profile was trained on only 6 sites.
- **Golfo San Jorge:** today it is only 0.003 above the aridity limit; a tourist "Valle de Marte" trail lies 25-35 km away.
- **Qilian foothills:** all nearby cold-desert cells drop out too.

Did not hold in the last round: Yazd (now a single-cell peak far down the list), the Uvs Nuur basin (one cell
is half lake), and the north Baffin Island ice lead (1 mm under the precipitation limit).

Other robust climate gain: the Maghreb is drying. Of the 22 clusters worldwide with at least 3 robust-gain
cells, 21 are in Morocco or Algeria, for example around Ain Oussera / Chott Zahrez Chergui, Algeria, with
aridity 0.216 → 0.18 by 2050. Their analog ranks are low, and the Ouarzazate area is already an ESA ExoMars
test region.

No Mars-analog use was found for the finalists. That is not proof of absence. No candidate in the United
States was both new and robust.

**Known analogs that lose dry-land status** (mean air temperature passes 0 °C):

| Site | Today (rank, mission) | Lost |
|---|---|---|
| Kara-Kul crater, Pamir | #2,527, rover | 2050 in both scenarios (back as arid land in 2090 under SSP5-8.5) |
| Tso Moriri, Ladakh | #8,438, thermal | 2050 in both scenarios |
| Tso Kar, Ladakh (region of ISRO's HOPE analog station) | #140,049, rover | 2050 under SSP5-8.5; 2090 in both |

**Ground ice:** with ground ice required, the best Earth analogs for Arcadia Planitia are high cold deserts on
permafrost in the Kunlun and northern Tibet, plus Arctic Canada. Ice-prospecting candidates fall from 22,369
cells today to 19,924 in 2050 (SSP2-4.5) and 15,388 in 2090 (SSP5-8.5).

**Dry land worldwide:** 257,208 cells today.

| Year, scenario | Dry cells | Gained | Lost |
|---|---|---|---|
| 2050, SSP2-4.5 | 255,307 | 4,004 | 5,905 |
| 2050, SSP5-8.5 | 254,664 | 4,734 | 7,278 |
| 2090, SSP2-4.5 | 254,860 | 5,572 | 7,920 |
| 2090, SSP5-8.5 | 252,267 | 8,744 | 13,685 |

## Limitations and open questions

- Minerals are a proxy from the rock class on Earth (GLiM) and from TES (~20 km) on Mars; Earth surface minerals (EMIT 60 m, ASTER GED 100 m) need a NASA Earthdata login and are not in yet.
- Earth ground ice south of the equator and Mars hydrogen (GRS) are still 1° data; SWIM Mars ice maps were unavailable.
- Mars temperatures come from a ~200 km climate model.
- Permafrost and vegetation stay as today in future years.
- Terrain scales (τ) at 11 km are provisional.
- The trained weights rely on labels from the unverified catalog; the large shifts (rock type for sample science, albedo for thermal and ice) need Science's review.
- The cold-desert albedo check (< 0.6) is ours; to confirm with Science.
- Vegetation stays as today in future years: no global NDVI projection exists, so drying regions that lose plant cover are missed.
- The future uses the 1° multi-model change. WorldClim also publishes CMIP6 at 2.5′ per model; a finer future would need several models downloaded and averaged.
- The known-analog catalog is incomplete and unverified.
- No finalist has been checked with satellite imagery or in the field.
