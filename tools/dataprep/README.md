# Fine data grids (Earth 0.25°, Mars 0.5°)

The app ships with the exported data in `web/app/data/planalogy/`, so you only need this to rebuild it.

1. Put the raw source files in `data/earth/` and `data/mars/` next to these scripts (the Data team's `spaceapps-data` folder).
2. `python prepare_data.py --res 0.25 --mars-res 0.5` writes `data/ready/fine/earth_0p25deg.csv.gz` and `mars_0p5deg.csv.gz`.
3. `python prepare_future.py --res 0.25` writes the climate years `data/ready/fine/ssp245|ssp585/earth_0p25deg_<year>.csv.gz`.
4. From the repo root: `python tools/dataprep/trim_fine.py <path>/data/ready/fine data/grid_fine` (plain CSV, only the columns the backend reads; the folder is not committed).
5. `PYTHONPATH=analogue_engine/src python -m backend.web_export --data data/grid_fine --gzip --no-calibration`

With `--no-calibration` the presets get the science team's start weights. The shipped manifest reuses the weights calibrated on the 1° grid.
