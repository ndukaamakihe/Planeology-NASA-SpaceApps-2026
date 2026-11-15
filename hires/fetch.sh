#!/usr/bin/env bash
# fetch URL FILE : resumable download that restarts when the transfer stalls
fetch() {
  url="$1"; out="$2"
  want=$(curl -sIL -m 30 "$url" | grep -i '^content-length' | tail -1 | tr -dc '0-9')
  for try in 1 2 3 4 5 6 7 8 9 10; do
    have=$(stat -c %s "$out" 2>/dev/null || echo 0)
    if [ -n "$want" ] && [ "$have" = "$want" ]; then echo "ok $out"; return 0; fi
    curl -sSL -C - --speed-limit 20000 --speed-time 45 -o "$out" "$url" || sleep 3
  done
  echo "FAILED $out ($have of $want)"
}
R="${PLANALOGY_HIRES_DATA:-$(cd "$(dirname "$0")/.." && pwd)/hires_data}/raw"
mkdir -p "$R/lst" "$R/ndvi" "$R/albedo" "$R/mars"
Z=https://zenodo.org/api/records
jobs_list() {
  echo "https://planetarymaps.usgs.gov/mosaic/Mars_MGS_MOLA_DEM_mosaic_global_463m.tif|$R/mars/mola_dem_463m.tif"
  echo "$Z/6350821/files/albedo_climatology_0.05CMG.zip/content|$R/albedo/albedo_climatology_0.05CMG.zip"
  for k in day_m night_m; do f="clm_lst_mod11a2.annual.${k}_1km_s0..0cm_2000..2017_v1.0.tif"; echo "$Z/1435938/files/$f/content|$R/lst/$f"; done
  for m in jan feb mar apr may jun jul aug sep oct nov dec; do f="clm_lst_mod11a2.$m.night_m_1km_s0..0cm_2000..2017_v1.0.tif"; echo "$Z/1435938/files/$f/content|$R/lst/$f"; done
  for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
    last=$(case $m in 02) echo 28;; 04|06|09|11) echo 30;; *) echo 31;; esac)
    f="veg_ndvi_avhrr.mod09ga_p90_5km_s0..0cm_2019${m}01..2019${m}${last}_v1.0.tif"; echo "$Z/4305975/files/$f/content|$R/ndvi/$f"
  done
}
export -f fetch
jobs_list | xargs -P 5 -I{} bash -c 'fetch "$(echo "{}" | cut -d"|" -f1)" "$(echo "{}" | cut -d"|" -f2)"'
echo ALL DONE
