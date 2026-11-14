"""Mission presets: one profile per use case, each with its own target and
its own known analogs for calibration.

Weights follow the Science P1-P10 analysis and the mission's needs; they are
PROVISIONAL starting points that calibration then adjusts. Known analogs come
from the Science documents and must be confirmed by Science. Coordinates are
the 1-degree cells that contain each site.

Not a preset on purpose: helicopter flight (e.g. Ingenuity). It depends on
air density, which no Earth site reproduces.
"""

from __future__ import annotations

from typing import Any

import grid_1deg as g

CELLS = {
    "Gale Crater (Curiosity)": (-5.5, 137.5),
    "Jezero Crater (Perseverance)": (18.5, 77.5),
    "Arcadia Planitia (approx.)": (46.5, -167.5),
}
EARTH = {
    "Atacama": (-24.5, -69.5),
    "Arizaro": (-24.5, -67.5),
    "Kara-Kul": (39.5, 73.5),
    "Dry Valleys": (-77.5, 161.5),
    "Devon Island (Haughton)": (75.5, -89.5),
}


def cell_id(planet: str, lat: float, lon: float) -> str:
    return f"{planet}_{lat:+05.1f}_{lon:+06.1f}"


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


def build_profile(preset: dict[str, Any]) -> dict[str, Any]:
    lat, lon = CELLS[preset["target"]]
    return g.make_profile(
        preset["id"], cell_id("mars", lat, lon), preset["dimension_weights"], preset["feature_weights"],
        description=f"{preset['name']}: {preset['why']}",
        constraints=preset.get("constraints"), required=preset.get("required"),
        extra_limitations=preset.get("extra_limitations"),
    )
