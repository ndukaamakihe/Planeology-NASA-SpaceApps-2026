"""
Planalogy - NASA Space Apps Challenge 2026

Module: Analog Presets
Purpose: Mission presets: one profile per use case, each with its own target and
its own known analogs for calibration.

Weights follow the Science P1-P10 analysis and the mission's needs; they are
PROVISIONAL starting points that calibration then adjusts. Known analogs come
from the Science documents and must be confirmed by Science.

Coordinates are points at each site (approximate), not cell centres: the
cell that contains the point is looked up in whatever grid is loaded, so the
same lists work at 1 degree, 50 km or any other resolution. At 1 degree each
point falls in the cell used originally (checked by the tests).

Not a preset on purpose: helicopter flight (e.g. Ingenuity). It depends on
air density, which no Earth site reproduces.
"""

from __future__ import annotations

from typing import Any

from backend import grid_data as g

# Mars targets (lat, lon; east positive)
CELLS = {
    "Gale Crater (Curiosity)": (-5.4, 137.8),
    "Jezero Crater (Perseverance)": (18.38, 77.58),
    "Arcadia Planitia (approx.)": (46.5, -167.5),
}
# Known Earth analogs (lat, lon)
EARTH = {
    "Atacama": (-24.08, -69.92),  # Yungay hyperarid core
    "Arizaro": (-24.7, -67.75),  # Salar de Arizaro
    "Kara-Kul": (39.02, 73.45),  # Kara-Kul impact structure
    "Dry Valleys": (-77.52, 161.83),  # Wright Valley, McMurdo Dry Valleys
    "Devon Island (Haughton)": (75.38, -89.67),  # Haughton crater
}

cell_id = g.cell_id  # id format, e.g. earth_+83.5_-077.5 at 1 degree


def target_key(data: dict[str, Any], name: str) -> tuple[float, float] | None:
    """Mars cell (centre) containing a named target in the loaded grid; None if outside it."""
    return data["mars_spec"].containing(*CELLS[name])


def analog_id(data: dict[str, Any], name: str) -> str | None:
    """Id of the Earth cell containing a named known analog in the loaded grid; None if outside it."""
    spec = data["earth_spec"]
    key = spec.containing(*EARTH[name])
    return None if key is None else spec.cell_id(*key)


ALL_FEATURES = ["slope_deg", "roughness_m", "relief_m", "surface_temp_swing_K", "surface_temp_min_K",
                "air_temp_swing_K", "ati_percentile", "albedo", "mineral_groups", "rock_group",
                "inside_impact_structure", "ground_ice_flag"]


def _weights(**overrides: float) -> dict[str, float]:
    base = {"slope_deg": 1, "roughness_m": 1, "relief_m": 1, "surface_temp_swing_K": 2, "surface_temp_min_K": 1,
            "air_temp_swing_K": 1, "ati_percentile": 1, "albedo": 1, "mineral_groups": 1, "rock_group": 1,
            "inside_impact_structure": 1, "ground_ice_flag": 1}
    base.update(overrides)
    return base


PRESETS: list[dict[str, Any]] = [
    {
        "id": "rover_navigation",
        "name": "Rover navigation and mobility",
        "mission": "Curiosity-type rover driving and route planning",
        "target": "Gale Crater (Curiosity)",
        "why": "Terrain decides mobility; surface material (thermal inertia, albedo) separates dunes, gravel and bedrock.",
        "dimension_weights": {"terrain": 2, "thermophysical": 1, "optical": 1, "thermal": 0.5,
                              "mineralogy": 0.25, "geology": 0.5, "craters": 0.5, "water": 0.5},
        "feature_weights": _weights(),
        "known_analogs": ["Atacama", "Arizaro", "Kara-Kul"],
    },
    {
        "id": "sample_science",
        "name": "Sample science and geology",
        "mission": "Perseverance-type sampling of water-formed sediments",
        "target": "Jezero Crater (Perseverance)",
        "why": "Rock type and surface material record the water history (Science P7/P8); dry lake beds and salt flats match best.",
        "dimension_weights": {"geology": 2, "mineralogy": 1, "thermophysical": 1, "optical": 1, "terrain": 1,
                              "thermal": 0.5, "water": 0.5, "craters": 0.5},
        "feature_weights": _weights(),
        "known_analogs": ["Atacama", "Arizaro"],
    },
    {
        "id": "thermal_environment",
        "name": "Thermal environment testing",
        "mission": "Instrument and thermal-management tests in a Mars-like day-night cycle",
        "target": "Gale Crater (Curiosity)",
        "why": "The day-night swing is the clearest Mars-like signal (Science P2); cold minima matter for survival heating.",
        "dimension_weights": {"thermal": 3, "thermophysical": 1, "optical": 1, "terrain": 0.25,
                              "geology": 0, "craters": 0, "water": 0.5},
        "feature_weights": _weights(),
        "known_analogs": ["Atacama", "Dry Valleys", "Arizaro"],
    },
    {
        "id": "ice_prospecting",
        "name": "Ground-ice prospecting (ISRU)",
        "mission": "Drilling and extraction tests for shallow ground ice",
        "target": "Arcadia Planitia (approx.)",
        "why": "Ice is a hard requirement for the Earth site. Similarity then favours cold, flat plains.",
        "dimension_weights": {"thermal": 2, "terrain": 1, "optical": 0.5, "thermophysical": 0.5,
                              "geology": 0.5, "craters": 0, "water": 0},
        # The ice flag is a requirement, not a similarity: the Mars grid flags no
        # Arcadia cell (its threshold is >= 10 wt% H2O), although Science reports shallow ice.
        "feature_weights": _weights(ground_ice_flag=0),
        "constraints": [{"id": "earth_site_has_ground_ice", "feature_id": "ground_ice_flag", "type": "equals",
                         "value": True, "description": "An ice-extraction test needs ground ice at the Earth site."}],
        "required": ["ground_ice_flag"],
        "extra_limitations": [
            "Mars ice flag in this grid needs >= 10 wt% H2O; Arcadia shows about 5 wt% so it is flagged 0 although "
            "Science reports ice centimetres below the surface. Ice is used as a requirement on Earth sites instead.",
            "Earth ice data covers northern-hemisphere permafrost only (Antarctic sites show no ice).",
        ],
        "known_analogs": ["Devon Island (Haughton)", "Dry Valleys"],
    },
]


def build_profile(preset: dict[str, Any], data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Science starting profile for a preset, for the loaded grid (``data`` from grid_data.build).

    Without ``data`` it assumes the original 1-degree grid.
    """
    if data is None:
        spec, base = g.GridSpec.one_degree("mars"), None
    else:
        spec, base = data["mars_spec"], data["limitations"]
    key = spec.containing(*CELLS[preset["target"]])
    if key is None:
        raise ValueError(f"{preset['target']} {CELLS[preset['target']]} is outside the Mars grid")
    target = spec.cell_id(*key)
    return g.make_profile(
        preset["id"], target, preset["dimension_weights"], preset["feature_weights"],
        description=f"{preset['name']}: {preset['why']}",
        constraints=preset.get("constraints"), required=preset.get("required"),
        extra_limitations=preset.get("extra_limitations"), base_limitations=base,
    )
