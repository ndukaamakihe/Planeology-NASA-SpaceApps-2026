# Data contract — `analogue_engine` v0.2.0

Audience: backend/integration (Nduka). This is a *proposed* contract; field
names can be adapted once the backend contract is agreed. A complete working
examples: `examples/fixture_synthetic.json` (scalar only) and
`examples/fixture_mixed_synthetic.json` (every kind, P1–P10 inspired).
Templates for the data team: `examples/templates/`. Example outputs:
`examples/output/`.

## 1. Calling the engine

```python
from analogue_engine import compare, rank, sensitivity_analysis, load_bundle, AnalogueEngineError

bundle = load_bundle("examples/fixture_synthetic.json")   # or build dicts yourself
result = rank(target, candidates, profile, feature_definitions)
payload = result.to_json()        # strict JSON (never NaN/Infinity)
```

* `target`, each candidate: `Site` object **or** a dict in the format below.
* `profile`: `Profile` or dict.
* `feature_definitions`: list (or `{id: definition}` mapping) of dicts or objects.
* Pure function: no I/O, no network, no LLM, no global state. Same input →
  byte-identical JSON output.

```python
try:
    result = rank(...)
except AnalogueEngineError as e:
    return 400, e.to_dict()   # {"error": code, "message": ..., "details": {...}}
```

## 2. Input records

### FeatureDefinition

```json
{
  "id": "slope_deg",
  "dimension": "terrain",
  "definition": "Local surface slope from a DEM at the stated support ...",
  "canonical_unit": "deg",
  "kind": "scalar",
  "comparator_id": "clipped_linear_v1",
  "comparability_protocol": {
    "id": "slope_protocol_v0",
    "description": "optional",
    "required_metadata": ["method_id", "method_version", "spatial_support"],
    "must_match": ["method_id", "method_version", "spatial_support"],
    "cross_body_comparable": true,
    "equivalent_values": {"spatial_support": [["support_a", "support_b"]]}
  }
}
```

* `kind` and `comparator_id` must match:

  | kind | comparator_id | value shape | scale in profile |
  |---|---|---|---|
  | `scalar` | `clipped_linear_v1` | number | `tau` (canonical unit) **or** fixed `range` {min, max} |
  | `scalar` | `log_ratio_v1` | number > 0 | `tau` in `"decade"` |
  | `boolean` | `boolean_match_v1` | `true` / `false` | none |
  | `categorical` | `categorical_match_v1` | string from `categories` | none |
  | `set` | `jaccard_v1` | list of strings from `categories` | none |
  | `composition` | `cosine_v1` | object `{category: amount ≥ 0}` with **all** `categories` as keys | none |

* `categories` (required for categorical/set/composition): the shared
  vocabulary, identical for Earth and Mars. Values outside it are rejected.
* Metadata fields usable in protocols: `method_id`, `method_version`,
  `spatial_support`, `temporal_support`.
* `must_match` ⊆ `required_metadata` (two absent values never count as a match).
* `cross_body_comparable` must be explicit (`true`/`false`).
* `equivalent_values`: only equivalences declared by science/data; the engine
  never infers them (equal nominal resolution ≠ equal effective resolution).

### Site and Measurement

```json
{
  "id": "synthetic_A",
  "body": "earth",
  "data_mode": "synthetic",
  "name": null,
  "area_ref": "synthetic_area:synthetic_A",
  "measurements": [
    {
      "feature_id": "slope_deg",
      "value": 12,
      "status": "valid",
      "unit": "deg",
      "method_id": "synthetic_method_slope_deg",
      "method_version": "0",
      "spatial_support": "synthetic_support_v0",
      "temporal_support": null,
      "source_ref": "fixture:section6",
      "uncertainty": null
    }
  ]
}
```

* `data_mode`: `synthetic` | `real`. All sites in one request must share it.
* `value` shape depends on the feature kind (table above). Write 0 explicitly
  for absent components of a composition.
* `status`: `valid` (value required, finite) | `missing` (value must be null) |
  `flagged` (quality-flagged; value may be present but is not used).
* `unit` must equal the feature's `canonical_unit`. **No conversion in v0.**
* Absent data = `null` + `status: "missing"`. Never NaN, never 0.
* `uncertainty`: optional, ≥ 0; carried but not used in v0.

### Profile

```json
{
  "id": "synthetic_slope_priority",
  "version": "0.1.0",
  "target_id": "synthetic_target",
  "calibration_status": "uncalibrated",
  "description": "optional",
  "dimension_weights": {"terrain": 1.0},
  "features": [
    {"feature_id": "slope_deg", "weight": 0.8, "tau": 10,  "tau_unit": "deg"},
    {"feature_id": "vrm",       "weight": 0.1, "tau": 0.1, "tau_unit": "1"},
    {"feature_id": "relief_m",  "weight": 0.1, "tau": 100, "tau_unit": "m"}
  ],
  "required_features": [],
  "declared_limitations": ["Gravity: Earth 1 g vs Mars about 0.38 g; not reproducible on Earth."],
  "constraints": [
    {"id": "max_relief_gap", "feature_id": "relief_m", "type": "max_abs_difference", "limit": 20, "unit": "m"}
  ]
}
```

* `features` **is** the active feature set (order irrelevant to scores).
* `weight` ≥ 0, finite, need not be normalised (normalised within each
  dimension). `dimension_weights` optional with one dimension, mandatory with
  several, and must list exactly the active dimensions.
* Scale, only for comparators that use one: either `tau` > 0 or
  `"range": {"min": a, "max": b}` with b > a (min-max scaling with **fixed**
  bounds; the engine uses tau = b − a, because the min cancels in a
  difference). Never compute min/max from the current candidates.
  `tau_unit` = canonical unit (`clipped_linear_v1`) or `"decade"`
  (`log_ratio_v1`). Scale-free comparators must not get `tau`/`range`.
* `calibration_status`: `uncalibrated` | `provisional` | `science_reviewed`
  (shown separately from `data_mode`).
* `required_features` and constraint features must be active; they block
  ranking when not comparable even with weight 0.
* Constraint `type`: `max_abs_difference` (|x − t| ≤ limit), `min_value`
  (x ≥ limit), `max_value` (x ≤ limit). `unit` is required and must equal the
  canonical unit. Values within a relative tolerance of 1e-9 (absolute 1e-12)
  of the limit count as on the limit (satisfied), so float noise cannot decide.
  Numeric types only apply to scalar features.
* Constraint `type: "equals"` with `value` (true/false or a category) applies
  to boolean/categorical features, e.g.
  `{"id": "ice_must_be_present", "feature_id": "ground_ice_present", "type": "equals", "value": true}`.

### CSV for the data team (long format)

`load_sites_csv(path, feature_definitions) -> {site_id: Site}` reads one row
per (site, feature). Template: `examples/templates/measurements_template.csv`.

| Column | Required | Notes |
|---|---|---|
| `site_id`, `body`, `data_mode` | yes | site columns must be identical on all rows of a site |
| `site_name`, `area_ref` | no | `area_ref` links to the map polygon/cell |
| `feature_id`, `value`, `status`, `unit` | yes | empty `value` + `status=missing` = no data |
| `method_id`, `method_version`, `spatial_support`, `temporal_support` | per protocol | |
| `source_ref`, `uncertainty` | no | cite the dataset in `source_ref` |

Value encoding: scalar `12.5` · boolean `true`/`false` · categorical
`evaporite` · set `basalt;clay` (`[]` = empty set) · composition
`basalt=0.5;clay=0.2;salts=0;iron_oxides=0.3`. Feature definitions and
profiles stay in JSON (`examples/templates/definitions_and_profiles_template.json`).
GeoJSON is not read yet: put the engine fields in `properties` and the same
long format can be produced from it.

### Bundle file (optional helper)

`load_bundle(path)` reads `{"schema_version": "analogue_engine.bundle.v0",
"feature_definitions": [...], "sites": [...], "profiles": [...]}`.

## 3. Output

### RankingResult

| Field | Meaning |
|---|---|
| `target_id`, `profile_id`, `profile_version`, `model_id`, `model_version` | provenance |
| `data_mode`, `calibration_status` | shown separately; show both in the UI |
| `active_features`, `effective_weights`, `dimension_weights` | weights actually used (fixed for the search) |
| `ranked[]` | `{position, tied_with[], result: ComparisonResult}` for complete candidates only |
| `partial[]` | insufficient information; sorted by id (**no order implied**) |
| `excluded[]` | `incompatible` or `requirement_not_met`; sorted by id |
| `declared_limitations[]` | from the profile: conditions Earth cannot reproduce (shown, never scored) |
| `warnings[]` | request-level notes (`no_complete_candidates`, `ties_present`, `synthetic_data`, ...) |
| `ordering` | human-readable ordering rule |

### ComparisonResult (also returned by `compare`)

| Field | Meaning |
|---|---|
| `category` | `complete` / `partial` / `incompatible` / `requirement_not_met` |
| `rankable` | `category == "complete"` |
| `score_observed` | S_obs in [0,1], or `null` if nothing comparable. For non-complete candidates it is on a reduced basis: **do not sort it together with ranked scores** |
| `coverage` | weighted share of compared components, in [0,1] |
| `components[]` | one per active feature (below) |
| `dimensions[]` | per-dimension breakdown: `{dimension, dimension_weight, score_observed, coverage, features, compared_features}`; for a complete candidate `score_observed = Σ dimension_weight × dimension score`. Use it to show "strong geology analog, weak water analog" |
| `declared_limitations[]` | copied from the profile |
| `constraints[]` | `{id, feature_id, type, limit, status: satisfied/violated/unevaluable, observed, message}` |
| `reasons[]` | why not complete; `informational:` entries do not block |
| `limitations[]` | always includes `similarity_is_not_operational_suitability` |

### ComponentResult

`feature_id, dimension, status (compared | missing | comparability_pending |
incompatible), reason_code, message, unit, comparator_id, target_value,
candidate_value, delta, abs_difference, normalized_discrepancy, similarity,
detail, tau, raw_weight, effective_weight, contribution, blocking, required`.

* `delta`/`abs_difference` only for scalar kinds (null for categories, sets,
  compositions). `detail` explains the comparator (e.g. shared minerals for
  Jaccard, `abs_log10_ratio` for log, `cosine_distance` for cosine).
* `tau` is null for scale-free comparators.

* Not compared → `candidate_value`, `delta`, `similarity`, `contribution` are `null`.
* `contribution` = w_j·s_j / C (sums to `score_observed`).
* `reason_code` values: `not_provided`, `value_missing`, `quality_flagged`,
  `unit_mismatch`, `body_not_comparable`, `metadata_missing`,
  `protocol_mismatch:<field>`, `comparison_failed:<code>` (e.g. a difference
  overflowing to infinity, a log of 0 (`non_positive_value`), a cosine of an
  all-zero vector; only that candidate is excluded, the search continues).
* A `must_match` field that is present and different gives `incompatible`
  even if another required field is absent (more metadata could not fix it).

## 4. Errors (exceptions)

All inherit `AnalogueEngineError` and expose `.code`, `.message`, `.details`,
`.to_dict()`.

| Class | Typical `code` |
|---|---|
| `InvalidRequestError` | `invalid_number`, `non_finite_number`, `missing_field`, `invalid_enum`, `inconsistent_measurement`, `duplicate_measurement`, `duplicate_candidate`, `duplicate_feature_definition`, `unknown_comparator`, `invalid_protocol`, `unsupported_schema`, `invalid_json`, `invalid_type`, `invalid_value`, `value_type_mismatch`, `comparator_kind_mismatch`, `missing_categories`, `unexpected_categories`, `inconsistent_site` |
| `ProfileError` | `negative_weight`, `non_positive_tau`, `zero_weight_sum`, `zero_internal_weight_sum`, `dimension_weights_required`, `dimension_weights_mismatch`, `tau_unit_mismatch`, `unknown_feature`, `duplicate_active_feature`, `required_not_active`, `constraint_not_active`, `target_mismatch`, `target_missing_feature`, `target_unit_mismatch`, `target_metadata_missing`, `weight_overflow`, `constraint_unit_mismatch`, `feature_definitions_required`, `cannot_drop_requirement`, `tau_required`, `tau_not_used`, `tau_and_range`, `range_not_supported`, `constraint_kind_mismatch`, `target_value_type_mismatch`, `target_value_not_comparable`, `invalid_constraint` |
| `DataModeError` | `data_mode_mismatch` |

Taxonomy required by the brief:

| Situation | Where it appears |
|---|---|
| Invalid request | exception |
| Insufficient information | `partial` (`missing`, `comparability_pending`, constraint `unevaluable`) |
| Incompatible comparison | `excluded`, category `incompatible` |
| Requirement not met | `excluded`, category `requirement_not_met` |

## 4b. Data team grid format (what the engine reads today)

The Data team's current files **already work as they are**. Keep this
format; the adapter is `examples/real_data/grid_1deg.py`.

**Files**: `earth_1deg.csv` and `mars_1deg.csv` (later `moon_1deg.csv`),
plus `parameters.csv` describing every column. Data files are not committed
to this repository; the scripts take the folder as an argument:

```bash
python examples/real_data/run_real_grid.py <folder> gale
```

**Rules**
1. One row per 1°×1° cell. `lat` and `lon` are cell centres (lat
   89.5…−89.5, lon −179.5…179.5, east positive). Use the same grid and
   column names on every planet.
2. Units: one canonical unit per column, the same on every planet, as
   listed in `parameters.csv` (K, Pa, m, W/m², 0–1, wt%…). Never mix °C and K.
3. **Empty cell = no data.** Never write 0, −9999 or NaN for missing values.
4. Classes (`rock_group`) use one shared vocabulary for all planets:
   `volcanic, ancient_crust, sedimentary, evaporite_salt, ice, impact, water`.
5. Flags are 0/1 (`ground_ice_flag`, `is_land`).
6. In `parameters.csv`, keep the `comparable` column (`yes` / `no` /
   `filter` / `helper`). Only `yes` columns can be scored across planets.

**Columns the engine scores now** (Science P1–P10): `slope_deg`,
`roughness_m`, `relief_m` (P1; `elevation_m` only for the 3×3 fallback
`regional_relief_m`), `surface_temp_swing_K`, `surface_temp_min_K`,
`air_temp_swing_K` (P2), `apparent_thermal_inertia` (P3, as a within-planet
percentile), `albedo` (P4), `mineral_groups` (P7 proxy, Jaccard),
`rock_group` (P8), `crater_count` (P9, as yes/no), `ground_ice_flag` (P10).
Earth pre-filter: `is_land`, `precipitation_mm_yr`, `ndvi`, `rock_group`.

**Fixes and additions from the Data team** (grid version with 56 columns)
* `slope_deg`, `roughness_m`, `relief_m`: mean slope, standard deviation and
  max − min of elevation inside each cell, from a ~9–10 km DEM grid with the
  same method on both planets (Earth WorldClim 5′ = 9.3 km, Mars MOLA
  resampled to 6 pixels/degree = 9.9 km). Gale: 3.2°, 963 m, 3979 m.
* `air_temp_swing_K`: mean daily air temperature range. Earth: mean over 12
  months of WorldClim tmax − tmin. Mars: mean over 4 seasons of MCD v6 air
  temperature at 14 h − 02 h. Gale: 44 K, Earth land 5–15 K. This is the
  column that CMIP6 projections (WorldClim future tmax/tmin) can fill per
  year, so the year slider changes a scored feature, not only the filter.
* `mineral_groups` (P7 proxy): `|`-separated set from the vocabulary
  `basaltic, felsic, clays_hydrated, sulfates_salts, carbonates, iron_oxides`.
  Earth: typical minerals of the GLiM rock class. Mars: TES abundances
  normalised to the sum of non-dust minerals, present from 20 %, plus
  OMEGA/CRISM hydrated-mineral sites. Gale → `basaltic|clays_hydrated`.
  Coarse; Science may replace it with mineral lists from papers.
* `rock_group` on Mars: cells with an impact unit (e.g. AHi at Gale) take the
  most frequent non-impact group of the surrounding 5×5 cells. Gale is now
  `sedimentary`; `rock_code` keeps the original unit.
* Still open: `ground_ice_flag` in Antarctica (ESA CCI Permafrost v5 covers
  it and can be added).

**Year slider**: one Earth file per scenario and year in a subfolder,
`<scenario>/earth_1deg_<year>.csv` (e.g. `ssp245/earth_1deg_2050.csv`), built
by the Data team's `prepare_future.py` from WorldClim 2.1 CMIP6 projections
(multi-model ensemble mean; year = middle of the 20-year period 2021–2040 …
2081–2100). Same grid and columns as today's file. Changed: `air_temp_*`
including `air_temp_swing_K`, `precipitation_mm_yr`, `aridity_index`,
`aridity_class`. `ndvi` keeps today's value (no projection; an empty NDVI
would let every low-rain cell pass the filter and fake a climate effect).
Emptied (no projection, not used): `soil_moisture_pct`, `vapour_pressure_kPa`.
Everything else stays as today. Extra helper columns: `n_models`, `air_temp_change_K`,
`precipitation_change_pct`, `precipitation_spread_mm_yr`,
`aridity_class_today`. Ground temperature is not projected; ask Science before
deriving it from air temperature.

## 5. Backend integration (branch `backend`, `integration.run_assessment`)

The backend keeps a wide table (one row per location) and `run_assessment`
expects `similarity_scores = {location_id: 0..100}`. Bridge, verified end to
end against `backend/integration.py` at commit `baccadc` with pandas 3.1.1:

```python
from analogue_engine import rank, sites_from_wide_records, backend_payload

sites = sites_from_wide_records(df.to_dict("records"), cfg["column_specs"],
                                cfg["feature_definitions"], data_mode="synthetic")
target = sites[target_id]
earth = [s for k, s in sites.items() if k != target_id and s.body == "Earth"]
result = rank(target, earth, cfg["profiles"][mission_type], cfg["feature_definitions"])
payload = backend_payload(result)
results = run_assessment(target_id, mission_type, payload["similarity_scores"])
```

* `column_specs` maps each table column to `feature_id`, `unit`, `method_id`,
  `method_version`, `spatial_support` and `source_ref`. The data team fills
  this in once per column, not per row. Example:
  `examples/backend_bridge/bridge_config.json`.
* Empty cells (None, '' or pandas NaN) become **missing** measurements,
  never 0. Cells are decoded by feature kind.
* `payload` also has `ranked_order` (with the engine's tie-break by id),
  `not_ranked` (partial or excluded sites with their reasons, which
  `run_assessment` would otherwise silently skip), `dimension_scores` (0–100),
  weighted `coverage` and `declared_limitations`.
* Suggestions for the backend: round only for display; use `ranked_order` for
  the order; show `not_ranked` sites as "insufficient data" or "requirement
  not met"; use one coverage definition in the UI.
* One engine profile per backend mission type. Today the backend's mission
  profiles list parameters but have no weights or scales.

## 6. Weight calibration (for the AI / chat layer)

```python
from analogue_engine import calibrate_weights, CalibrationSettings

cal = calibrate_weights(target, candidates, start_profile, feature_definitions,
                        known_analogs=["site_id_1", "site_id_2", ...])
cal.calibrated_profile            # profile dict, ready for rank()
cal.calibrated_dimension_weights  # e.g. {"terrain": 0.24, "mineralogy": 0.23, ...}
cal.start_summary / cal.calibrated_summary   # ranks of the known analogs
cal.leave_one_out                 # hidden-site check
cal.new_candidates                # best sites that are not known analogs
cal.to_json()                     # strict JSON
```

* `start_profile` can be written by an AI from a mission description. The
  engine validates it like any other profile, and the AI never produces scores.
* Known analogs must be among the candidates and have the same features
  measured. Incomplete ones are reported in `known_analogs_unusable`.
* `CalibrationSettings(prior_strength=1.0, temperature=0.05, iterations=400, step=0.05)`.
  A higher `prior_strength` keeps the weights closer to the start.
* It runs in about 1 s for roughly 130 candidates with leave-one-out
  (pure Python).

## 7. Year slider: rankings over time (`rank_over_years`)

```python
from analogue_engine import rank_over_years

tl = rank_over_years(target, {2025: sites_2025, 2050: sites_2050, 2075: sites_2075},
                     profile, feature_definitions,
                     watch=[...known analog ids...], top_k=20)
tl.top_by_year        # {year: [site ids]}
tl.watched            # trajectories: score per year, trend per decade, status
tl.emerging / tl.fading            # entered / left the top k between first and last year
tl.biggest_gainers / tl.biggest_losers
```

* Pass one list of Earth sites per year, built from that year's data
  (observations or projections). Use **the same site ids every year** (e.g.
  `earth_<lat>_<lon>`). The target (Mars or Moon) and the profile stay fixed.
* A site that does not pass the pre-filter in some year can be left out for
  that year; its trajectory then shows null for that year.
* Status values are `gaining`, `losing` (change ≥ `change_threshold`,
  default 0.02 = 2 points), `stable`, `entering`, `leaving` and
  `insufficient`.
* Why it is meaningful: the scales are fixed and scores do not depend on the
  other sites, so a change in a site's score comes only from its own data.
* Put the year or scenario in each measurement's `temporal_support` (e.g.
  `"projection:ssp245:2050"`). Ask Science which projected variables really
  match the current ones. For example, climate models usually give the
  *air* temperature range, not the *ground* day–night swing.

## 8. Mission presets (buttons in the app)

`examples/real_data/run_presets.py <data_dir>` writes `output_presets.json`
with one entry per preset:

| Preset | Target | Main weight | Calibration verdict (current data) |
|---|---|---|---|
| `rover_navigation` | Gale (Curiosity) | terrain ×2 | accepted |
| `sample_science` | Jezero (Perseverance) | geology ×2 | rejected → science weights |
| `thermal_environment` | Gale | thermal ×3 | rejected → science weights |
| `ice_prospecting` | Arcadia Planitia | thermal and terrain; ground ice is a hard requirement | not validated → science weights |

Each entry has:
* `target_cell` and `why`;
* the start and calibrated category weights, the known-analog ranks and the
  leave-one-out check;
* `verdict`, `verdict_reason` and `weights_used`;
* `profile_used`: the profile to pass to `rank()`;
* `top_sites`: lat, lon, score and per-category scores;
* `declared_limitations`;
* `years`: the per-year trajectories, when yearly files exist.

**Validation gate:** `calibrate_weights` returns `verdict` and
`recommended_profile`. Learned weights are accepted only if hidden known
analogs improve: mean leave-one-out rank at least 5 % better, and at least
half of them improve. Otherwise the starting (Science) weights are
recommended.

Helicopter flight is deliberately not a preset: it depends on air density,
which Earth does not reproduce.

## 9. Site cards (`explain`)

```python
from analogue_engine import explain
card = explain(comparison_result)      # or explain(entry.result) for a ranked entry
```

A card re-arranges what the engine already computed; nothing is
recalculated. Its fields:
* `score_0_100`, `coverage_pct`, `status`, `rankable`;
* `headline`, a one-line summary;
* `matches` (category score ≥ 75), `partial_matches` (41–74) and
  `mismatches` (≤ 40), each with per-feature similarity, target value and
  site value;
* `not_scored` (categories with weight 0);
* `missing` (feature, reason, whether it blocks ranking);
* `requirements`;
* `earth_cannot_reproduce` (the declared limitations);
* `caveats` and `thresholds`.

The 75 / 40 thresholds are presentation choices for grouping, not
scientific cut-offs, and they are configurable.

`examples/real_data/site_cards.py <data_dir> [top_n]` writes
`output_site_cards.json`: the top-n cards per mission preset, with lat/lon
and whether the cell is a known analog. That is the map's "click a site"
panel.

## 10. Integration notes for the recommender

* Similarity is evidence, not operational suitability. Activity
  recommendations need requirements agreed with science, applied by the
  recommender or encoded as explicit profile constraints.
* Reducing the profile to increase coverage: `restrict_profile(profile,
  keep, new_version, feature_definitions)` and re-run **all** candidates under
  the new version. Dimensions left without features are dropped.
* `sensitivity_analysis(...)` returns, per ±20 % change of each weight and τ
  (perturbations that cannot change anything by construction are skipped),
  the new order and which candidates moved. Use it for "how robust is this
  ranking?" displays, not as a probability.

## 9. Settings file for the GUI (`examples/real_data/analysis_config.json`)

`run_config.py` reads one JSON file; the GUI only edits it. Per parameter:
`use` (1 = scored, 0 = ignored), `weight` and, for numbers, `tau`. Also the
dimension weights, the Earth filter (`max_precipitation_mm_yr`, `max_ndvi`,
`max_aridity_index`, excluded rock groups; empty values pass), the target
(`gale`, `jezero`, `arcadia` or a Mars cell) and the year slider
(`timeline.use`, `scenario`, `years`). The defaults reproduce
`grid_1deg.profile()` exactly (test `tests/test_run_config.py`).

```python
from run_config import load_config, run
cfg = load_config()
cfg["parameters"]["albedo"]["use"] = 0
result = run(cfg, "data/grid_1deg")   # dict: ranking (heat map), watched, timeline, profile
```
