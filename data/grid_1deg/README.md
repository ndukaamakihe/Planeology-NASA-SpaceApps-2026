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

## Year slider

Add one Earth file per year or scenario next to the others, for example
`earth_1deg_2030.csv` and `earth_1deg_2050.csv`. Each file has the same
columns and grid; only the time-dependent columns change. Name the source
and the scenario in `parameters.csv`.

## Using it with the similarity engine

```bash
python analogue_engine/examples/real_data/run_real_grid.py data/grid_1deg gale
```

See `analogue_engine/docs/data-contract.md` (section 4b) for the columns the
engine scores and the fixes requested upstream.
