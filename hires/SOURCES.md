# Planalogy 11 km: data sources

Every dataset used or planned for the 11 km grid. Keep this file up to date whenever a source is added.
Status: **used** (in the current build), **planned** (agreed, not downloaded yet), **needs account**
(NASA Earthdata login required).

## Used

### Earth

| Layer | Dataset | Where | Resolution | Notes |
|---|---|---|---|---|
| Elevation → slope, roughness, relief, land mask | WorldClim 2.1 elevation (SRTM based) | https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_30s_elev.zip (page: https://www.worldclim.org/data/worldclim21.html) | 30″ (~0.93 km) | Fick & Hijmans 2017, Int. J. Climatol. |
| Air temperature (min, max, mean), precipitation → aridity | WorldClim 2.1 monthly normals 1970-2000 | https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_2.5m_{tmin,tmax,tavg,prec}.zip | 2.5′ (~4.6 km) | aridity = P / Hargreaves PET (FAO-56 radiation), computed by us |
| Ground temperature (day-night swing, coldest night) | MODIS MOD11A2 LST long-term 2000-2017, OpenLandMap (Hengl 2018) | https://zenodo.org/records/1435938 (annual day_m, night_m and 12 monthly night_m files) | 1 km | values K × 50; 87.37° N to 62° S |
| Albedo | MODIS blue-sky albedo climatology (20 years of MODIS) | https://zenodo.org/records/6350821 (albedo_climatology_0.05CMG.zip, 12 mid-month days) | 0.05° | historical (with snow) blue-sky albedo |
| NDVI | Monthly global NDVI from MODIS and AVHRR, 1982-2019 | https://zenodo.org/records/4305975 (12 months of 2019) | 5 km | monthly 90th percentile; rescaled to the 1° grid's NDVI |
| Lakes (water mask) | Natural Earth 10 m lakes + North America + Europe supplements | https://naciscdn.org/naturalearth/10m/physical/ne_10m_lakes.zip (and _north_america, _europe) | vector | public domain |
| Impact structures | Wikipedia "List of impact structures on Earth" (88 with coordinates and diameter) + Kara-Kul | https://en.wikipedia.org/wiki/List_of_impact_structures_on_Earth | points | derived from the Earth Impact Database |
| Future climate (2030-2090, SSP2-4.5 and SSP5-8.5) | Data team's 1° CMIP6 projections (WorldClim 2.1 CMIP6, multi-model mean) | repo `data/grid_1deg/ssp245`, `ssp585` | 1° | applied as a change (delta method) |
| Rock type, minerals, ground ice (until replaced) | Data team's 1° grid (GLiM, Obu 2019) | repo `data/grid_1deg` (`parameters.csv` lists its sources) | 1° | being replaced by the planned sources below |

### Mars

| Layer | Dataset | Where | Resolution | Notes |
|---|---|---|---|---|
| Elevation → slope, roughness, relief | MGS MOLA global DEM mosaic | https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif | 463 m (averaged to 926 m) | USGS Astrogeology |
| Albedo | MGS TES bolometric albedo mosaic | https://planetarymaps.usgs.gov/mosaic/Mars_MGS_TES_Albedo_mosaic_global_7410m.tif | 7.4 km | USGS Astrogeology |
| Temperatures, rock, minerals, ice, craters (until replaced) | Data team's 1° grid (MCD v6, SIM 3292, TES minerals, Odyssey GRS, Robbins craters) | repo `data/grid_1deg` | 1° | |

### Other

| What | Source |
|---|---|
| Known Mars analog catalog (245 sites) | Compiled by an agent from general knowledge, **unverified**: `hires_tool/known_analogs.json` |
| ISRO HOPE analog station (Tso Kar, Ladakh) | https://www.isro.gov.in/ISRO_EN/Space_Analog_Mission.html |
| Qaidam Basin as a Mars analog | JGR Planets 2017 (doi 10.1002/2017JE005293) |

## Added for 11 km rock, ice, craters and thermal inertia (downloaded 15 Nov 2026)

| Layer | Dataset | Where (exact file) | Resolution | Status |
|---|---|---|---|---|
| Earth rock type (+ mineral proxy) | GLiM, Global Lithological Map v1.0/1.1 (Hartmann & Moosdorf 2012, G-Cubed, doi 10.1029/2012GC004370) | https://www.dropbox.com/s/9vuowtebp9f1iud/LiMW_GIS%202015.gdb.zip (official link from https://www.geo.uni-hamburg.de/geologie/forschung/aquatische-geochemie/glim.html and https://csdms.colorado.edu/wiki/Alldata:GLiM); gridded 0.5° version on PANGAEA doi 10.1594/PANGAEA.788537 | vector, 1,235,400 polygons, ~1:3.75 M | downloaded (1.1 GB); used |
| Earth ground ice (permafrost probability) | Permafrost Extent and Ground Temperature Map 2000-2016, Northern Hemisphere, v5.0 (Obu et al. 2019, Earth-Sci. Rev.; data PANGAEA doi 10.1594/PANGAEA.888600, CC-BY-3.0) | https://store.pangaea.de/Publications/ObuJ-etal_2018/UiO_PEX_PERPROB_5.0_20181128_2000_2016_NH.zip (via https://apgc.awi.de/dataset/pex) | 1 km, EPSG:3995 | downloaded (106 MB zip, 1.9 GB GeoTIFF); used |
| Mars geology | Geologic Map of Mars, SIM 3292 (Tanaka et al. 2014, doi 10.3133/sim3292) | https://pubs.usgs.gov/sim/3292/downloads/sim3292_database.zip | vector, 1:20 M | downloaded (809 MB); used |
| Mars craters | Robbins & Hynek 2012 crater database v1 (JGR, doi 10.1029/2011JE003966), 384,343 craters ≥ 1 km | USGS Astrogeology API: https://astrogeology.usgs.gov/pygeoapi/collections/mars/robbinsv1/items?f=csv (paged, limit 50000) → raw/robbins/robbins_v1.csv | points + diameters | downloaded; used (note: the API returns columns in a different order on each page; pages are merged by column name) |
| Mars thermal inertia | MGS TES thermal inertia maps, night and day 2007 (Putzig & Mellon 2007, Icarus; PDS volume mgs-m-tes-5-timap-v1) | https://pds-geosciences.wustl.edu/mgs/mgs-m-tes-5-timap-v1/mgst_9001/data/global_ti_night_2007.img (+ .lbl, day, datainfo.txt); page https://pds-geosciences.wustl.edu/missions/mgs/tes-timap.html | 20 ppd (~3 km) | downloaded; used (night map) |
| Mars ground ice | SWIM, Subsurface Water Ice Mapping, SWIM4MIM combined ice consistency maps (Morgan et al. 2021, Nature Astronomy, doi 10.1038/s41550-020-01290-z) | https://swim.psi.edu/SWIM4MIMProducts.php (GeoTIFF, 3 km, −60° to 60°, no data −30) | 3 km | **not used: site down (HTTP 523) all day 15 Nov 2026, no mirror found**; Mars ice uses Odyssey GRS + SIM 3292 polar units instead |

## Needs a NASA Earthdata account (Earth minerals)

| Layer | Dataset | Where | Resolution |
|---|---|---|---|
| Surface minerals (gypsum, calcite, hematite, goethite, clays…) | EMIT L2B Estimated Mineral Identification and Band Depth (EMITL2BMIN v001) | https://lpdaac.usgs.gov/products/emitl2bminv001/ | 60 m, arid regions ±52° |
| Silica / carbonate indices from thermal emissivity | ASTER Global Emissivity Dataset 100 m (AG100 v003) | https://lpdaac.usgs.gov/products/ag100v003/ | 100 m |

Account: https://urs.earthdata.nasa.gov/users/new

## Validation of the 11 km rock, ice and thermal-inertia layers (against the Data team's 1° grid)

| Layer | Check | Result |
|---|---|---|
| Earth rock group (GLiM) | 1° majority of the 11 km cells vs the 1° grid | 92.5 % agree (23,336 land cells) |
| Earth permafrost (Obu) | 1° mean vs the 1° grid | r = 0.936 (11,398 cells) |
| Mars rock group (SIM 3292) | 11 km cell at each 1° centre vs the 1° grid | 96.9 % agree |
| Mars thermal inertia (TES 2007) | vs the 1° grid's TES map (Mellon 2000) | r = 0.80 |
