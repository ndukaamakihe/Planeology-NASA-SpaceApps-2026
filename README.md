# Planeology-NASA-SpaceApps-2026
A data-driven planetary analogue identification platform using NASA and partner space agency observations, geospatial analysis and mathematical modelling to identify Earth locations suitable for future lunar and Martian mission testing.

## Structure

| Folder | What it is |
|---|---|
| `analogue_engine/` | Similarity model (pure Python): comparators, weights, calibration on known analogs, year slider, site cards. See its README and `docs/`. |
| `backend/` | App backend: data interface, geospatial helpers, mission profiles, integration, and `engine_service.py`, which connects the engine to the data. |
| `data/grid_1deg/` | Data team's 1°×1° Earth/Mars grid (`earth_1deg.csv`, `mars_1deg.csv`, `parameters.csv`). It comes from branch `data-grid-1deg`. |

## Install

```bash
pip install -r requirements.txt
```

The requirements include the engine as `-e ./analogue_engine`.

## Run the mission presets

```bash
python -m backend.engine_service
```

This runs all four presets: rover navigation (Gale), sample science
(Jezero), thermal environment (Gale) and ground-ice prospecting (Arcadia).
To run one preset with more sites, or to point at another data folder:

```bash
python -m backend.engine_service rover_navigation --top 20 --data data/grid_1deg
```

Results go to `data/results/<preset>.json`. Each file contains the ranked
sites with site cards (score, coverage, what matches, what doesn't, what is
missing), a heat map of every scored cell, map points, the calibration
verdict and the declared limitations. The first run calibrates each preset
(about 20 s) and caches the result in `data/preset_profiles.json`.

**Year slider (climate change):** the Data team's projected Earth files are in
`data/grid_1deg/ssp245/` and `data/grid_1deg/ssp585/` (`earth_1deg_<year>.csv` for 2030, 2050, 2070,
2090; WorldClim 2.1 CMIP6, 6-model mean). Today's file is the baseline (1985 = middle of 1970-2000):

```bash
python -m backend.engine_service --years                    # SSP2-4.5
python -m backend.engine_service --years --scenario ssp585  # high emissions
```

This writes `data/results/<preset>_years_<scenario>.json` with the sites gaining or
losing analogy. What changes in the future files: air temperature (incl. the
day-night air swing, scored in P2), precipitation (dry/bare filter) and aridity;
see `data/grid_1deg/README.md`.

**Settings for a GUI:** `analogue_engine/examples/real_data/analysis_config.json`
switches every parameter on/off (`use` 1/0) and sets its weight; defaults are the
Science P1-P10 recommendation (`run_config.py`, data contract section 9).

Yearly files can be **climate projections only** (`lat`, `lon`,
`air_temp_swing_K`, `air_temp_min_K`, `precipitation_mm_yr`,
`aridity_index`, ... without terrain columns). They are merged onto the
present grid as follows:
- **Ground temperatures (delta method):** today's ground temperature plus the
  projected change in air temperature since the earliest yearly file, which
  acts as the model's present.
- **Dry land:** follows Science's rule. A land cell that is not ice or water
  counts as dry when it is bare ground (NDVI < 0.2) and either
  `aridity_index` ≤ 0.20 or a cold desert: mean annual air temperature
  below 0 °C and precipitation below 250 mm/yr. Cold deserts barely
  evaporate, so the aridity index alone calls them wet (Devon Island, Dry
  Valleys). A cold cell must also have albedo < 0.6, so ice sheets that the
  geology map gives a rock type stay out (provisional, to confirm with
  Science). The app adds a "hyper-arid only" option (aridity < 0.05).
- **Not projected:** terrain, rock, craters, albedo, thermal inertia,
  ground ice and NDVI (vegetation) keep their present values. No global
  NDVI projection exists, so on the future maps plants stay as today.

**Other resolutions (e.g. 50 km cells):** nothing assumes 1° cells. Put one
`earth_<name>.csv` and one `mars_<name>.csv` (same columns) in a folder, for
example `data/grid_50km/` with Earth at 0.45° and Mars at 0.84°, and pass
`--data data/grid_50km` to `engine_service` or `web_export`. Each planet's
step and origin are read from the files. The relief uses that grid's
neighbouring cells, and targets and known analogs (stored as site
coordinates) map to the cell that contains them. Both planets must use the
same degree step or the same cell size in km; otherwise loading stops with a
clear error. Yearly files are `earth_<name>_<year>.csv`.

## Web app (Planalogy)

`web/app/` is the static web app. It has the 3D globe and an **Analog
Finder**. Pick a Mars target (a preset site or **any point on Mars**), then
choose a mission preset or set weights, by hand or by describing the mission
to Claude. Every Earth land cell is re-ranked in the browser; by default only
dry, bare land counts, and a switch turns that off. A heat map, the top sites
and site cards update instantly.

`backend/web_export.py` exports the raw feature values of every Earth land
cell and every Mars cell. `web/app/js/scoring.js` applies the engine's
comparators, scales, weights and ordering. A test under Node.js checks that
the similarities match the engine bit for bit and that the ranking is
identical. Yearly Earth files only carry the climate-dependent columns.
Files are plain JSON: the Claude artifact serves `.json` but not `.gz`, and
accepts up to 16 MB per file. If one file would exceed 15 MB (fine grids), the
export writes gzip-compressed `.json.gz` instead, about 4x smaller with
unchanged values. The app reads both formats, but for the artifact such a grid
has to be split into several files. Use `--gzip` or `--no-gzip` to force
either.
To refresh the data after new grid files, including yearly files for the
year slider, run:

```bash
python -m backend.web_export                     # years from data/grid_1deg/ssp245/
python -m backend.web_export --scenario ssp585   # or the high-emission scenario
```

The app is published as a Claude artifact. Any static host also works:

```bash
python -m http.server --directory web/app
```

## Tests

```bash
python -m pytest backend/tests -q
```

```bash
cd analogue_engine
python -m pytest -q
```
