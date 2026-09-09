# Source structure

```text
vehicle_telemetry_thesis/
├── main.py
├── run_toolkit.bat
├── requirements.txt
├── README.md
├── config/
│   └── privacy_locations.json
├── data/
│   ├── maps/
│   │   └── study_area_roads.osm.pbf
│   ├── raw/
│   └── processed/
├── docs/
│   ├── DATA_ACCESS_AND_PRIVACY.md
│   ├── SOURCE_STRUCTURE.md
│   └── VERSION_HISTORY.md
└── src/
    ├── core/
    │   ├── app_state.py
    │   ├── paths.py
    │   ├── settings.py
    │   ├── telemetry_io.py
    │   └── telemetry_math.py
    ├── preprocessing/
    │   ├── privacy_trim.py
    │   └── clean_dataset.py
    ├── dead_reckoning/
    │   ├── common.py
    │   ├── v1.py
    │   ├── v2.py
    │   └── v2_inertial.py
    ├── mapping/
    │   ├── osm_network.py
    │   └── osm_map_match.py
    ├── analysis/
    │   └── behaviour.py
    └── visualisation/
        ├── svg_charts.py
        ├── results.py
        └── showcase.py
```

## Design

I keep `main.py` at the repository root as the single entry point. The larger implementation is split by responsibility so the project is easier to inspect in GitHub and easier to reference in my dissertation.

`src/core` contains shared state, path, parsing and mathematical helpers. `src/preprocessing` contains privacy and cleaning stages. `src/dead_reckoning` contains V1/V2 logic. `src/mapping` contains OSM loading and matching. `src/analysis` contains behaviour analysis, while `src/visualisation` contains figure and showcase generation.

The map path and privacy configuration path are both repository-relative and are defined centrally in `src/core/settings.py`.
