# 1° × 1° Earth / Mars grid (Data team)

Put the grid files in this folder:

| File | Content |
|---|---|
| `earth_1deg.csv` | One row per Earth cell |
| `mars_1deg.csv` | One row per Mars cell |
| `parameters.csv` | Every column: unit, description, source per planet, `comparable` |
| `SOURCE.txt` | How the files were built |
| `preview/*.png` | Optional preview maps |

The `.sqlite` and `.xlsx` versions are not needed because they hold the same
data as the CSVs.

## Upload (GitHub website)

1. Make sure the branch selector shows **`data-grid-1deg`**, then open this
   folder.
2. Choose **Add file → Upload files** and drag the CSVs (and `SOURCE.txt`).
3. Commit to the `data-grid-1deg` branch, then open a pull request to `main`.

## Format rules (the current files already follow them)

1. One row per 1°×1° cell. `lat` and `lon` are cell centres (lat 89.5…−89.5,
   lon −179.5…179.5, east positive). Use the same grid and column names on
   every planet.
2. One unit per column, the same on every planet, as listed in
   `parameters.csv`. Never mix °C and K.
3. **Empty cell = no data.** Never write 0, −9999 or NaN for missing values.
4. `rock_group` uses one shared vocabulary for all planets: `volcanic`,
   `ancient_crust`, `sedimentary`, `evaporite_salt`, `ice`, `impact`,
   `water`.
5. Flags are 0/1 (`is_land`, `ground_ice_flag`).
6. In `parameters.csv`, keep the `comparable` column (`yes` / `no` /
   `filter` / `helper`). Only `yes` columns can be compared across planets.

## Year slider (future Earth, climate change)

| Path | Content |
|---|---|
| `ssp245/earth_1deg_<year>.csv` | SSP2-4.5 (middle of the road), years 2030, 2050, 2070, 2090 |
| `ssp585/earth_1deg_<year>.csv` | SSP5-8.5 (high emissions), same years |
| `summary_ssp245.csv`, `summary_ssp585.csv` | aridity classes per year and the watched analog sites |
| `aridity_change_map.png` | where the aridity class gets drier / wetter vs today |

Source: WorldClim 2.1 CMIP6 projections (Fick & Hijmans 2017), 6-model ensemble mean
(ACCESS-CM2, EC-Earth3-Veg, IPSL-CM6A-LR, MIROC6, MPI-ESM1-2-HR, MRI-ESM2-0), 10 arc-minutes,
aggregated to 1°. The year is the middle of the 20-year period (2021-2040 ... 2081-2100).
Built by the Data team's `download_future.py` + `prepare_future.py`.

Same grid and columns as today's file. Changed: `air_temp_mean_K`, `air_temp_min_K`, `air_temp_max_K`,
`air_temp_swing_K` (scored, P2), `precipitation_mm_yr` (dry/bare filter), `aridity_index`,
`aridity_class`. Kept at today's value: `ndvi` (no projection; keeping it means the dry/bare filter
changes only through precipitation, so the year slider shows climate effects, not a missing value).
Emptied (no projection, not used): `soil_moisture_pct`, `vapour_pressure_kPa`.
Unchanged (no projection, or does not change in 80 years): terrain, ground temperature, albedo,
thermal inertia, rock type, minerals, craters, ground ice. Helper columns: `n_models`,
`air_temp_change_K`, `precipitation_change_pct`, `precipitation_spread_mm_yr`, `aridity_class_today`,
`scenario`, `period`. The aridity index (UNEP, Hargreaves PET) is computed with one method for
today and the future; it is not meaningful for polar cold deserts.

## New columns in this version (58 columns)

`slope_deg`, `roughness_m`, `relief_m` (P1, ~9-10 km DEM, same method both planets),
`air_temp_swing_K` (P2, air vs air), `mineral_groups` (P7 proxy), `aridity_index`,
`aridity_class` (Earth filter). Mars `rock_group`: impact units take the group around them
(Gale = sedimentary). Details: `parameters.csv` and `analogue_engine/docs/data-contract.md` 4b.

## Using it with the similarity engine

```bash
python analogue_engine/examples/real_data/run_real_grid.py data/grid_1deg gale
```

See `analogue_engine/docs/data-contract.md` (section 4b) for the columns the
engine scores and the fixes requested upstream.
