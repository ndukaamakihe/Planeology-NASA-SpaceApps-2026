"""Decompress the fine grids into data/grid_fine/ with only the columns the backend reads."""
import csv, gzip, sys
from pathlib import Path
SRC = Path(sys.argv[1]); DST = Path(sys.argv[2])
DROP = set("""air_pressure_Pa cell_area_km2 chem_cl_wt chem_fe_wt chem_k_wt chem_si_wt chem_th_wt
crater_density_per_10k_km2 crater_max_diam_km dust_cover_index ground_ice_h2o_wt hydrated_mineral_sites
mineral_amphibole mineral_carbonates mineral_hematite mineral_high_ca_pyroxene mineral_k_feldspar mineral_low_ca_pyroxene
mineral_olivine mineral_plagioclase mineral_quartz mineral_sheet_silicates_hi_si_glass mineral_sulfates mineral_surface_dust
soil_moisture_pct solar_flux_14h_Wm2 solar_radiation_Wm2 surface_temp_day_K surface_temp_night_K
vapour_pressure_kPa wind_ms""".split())
for src in sorted(SRC.rglob("*.csv.gz")):
    out = DST / src.relative_to(SRC).with_suffix("")
    if out.exists() and out.stat().st_mtime > src.stat().st_mtime: continue
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(src, "rt", newline="") as f, open(str(out) + ".part", "w", newline="") as g:
        r = csv.reader(f); head = next(r); keep = [i for i, c in enumerate(head) if c not in DROP]
        w = csv.writer(g); w.writerow([head[i] for i in keep])
        for row in r: w.writerow([row[i] for i in keep])
    Path(str(out) + ".part").rename(out); print(out, flush=True)
for extra in ("parameters.csv", "SOURCE.txt"):
    if (SRC / extra).exists(): (DST / extra).write_bytes((SRC / extra).read_bytes())
