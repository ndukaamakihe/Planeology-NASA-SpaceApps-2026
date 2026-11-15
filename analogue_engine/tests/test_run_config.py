"""The GUI settings file: defaults must equal the Science profile, switches must work."""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "examples" / "real_data"))

import grid_1deg as g  # noqa: E402
import run_config as rc  # noqa: E402


def _by_id(profile):
    return {f["feature_id"]: f for f in profile["features"]}


def test_defaults_equal_science_profile():
    cfg = rc.load_config()
    assert rc.validate(cfg) == []
    mine, science = rc.build_profile(cfg, "mars_t"), g.profile("mars_t")
    assert _by_id(mine) == _by_id(science)
    assert mine["dimension_weights"] == science["dimension_weights"]


def test_switch_off_removes_parameter_and_empty_dimension():
    cfg = rc.load_config()
    cfg["parameters"]["albedo"]["use"] = 0
    prof = rc.build_profile(cfg, "mars_t")
    assert "albedo" not in _by_id(prof)
    assert "optical" not in prof["dimension_weights"]
    assert "albedo" in prof["declared_limitations"][-1]


def test_weight_and_tau_are_taken_from_settings():
    cfg = rc.load_config()
    cfg["parameters"]["slope_deg"].update(weight=3, tau=8)
    f = _by_id(rc.build_profile(cfg, "mars_t"))["slope_deg"]
    assert (f["weight"], f["tau"], f["tau_unit"]) == (3, 8, "deg")


def test_invalid_settings_are_reported():
    cfg = rc.load_config()
    cfg["parameters"]["albedo"]["use"] = 2
    cfg["parameters"]["slope_deg"]["tau"] = 0
    cfg["parameters"]["unknown_thing"] = {"use": 1, "weight": 1}
    errors = rc.validate(cfg)
    assert any("albedo" in e for e in errors) and any("slope_deg" in e for e in errors)
    assert any("unknown_thing" in e for e in errors)
    for p in cfg["parameters"].values():
        p["use"] = 0
    assert "no parameter has use = 1" in rc.validate(cfg)


def test_filter_lets_unknown_values_pass():
    flt = {"use": 1, "max_precipitation_mm_yr": 500, "max_ndvi": 0.2, "max_aridity_index": None,
           "exclude_rock_groups": ["ice", "water"]}
    row = {"is_land": "1.0", "rock_group": "sedimentary", "precipitation_mm_yr": "100", "ndvi": ""}
    assert rc.passes_filter(row, flt)
    assert not rc.passes_filter({**row, "precipitation_mm_yr": "800"}, flt)
    assert not rc.passes_filter({**row, "rock_group": "ice"}, flt)
    assert not rc.passes_filter({**row, "is_land": "0.0"}, flt)
