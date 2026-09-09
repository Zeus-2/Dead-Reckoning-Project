# Vehicle Telemetry Thesis Toolkit

This is my final cleaned source-code package for the MSc vehicle telemetry project.

## What the toolkit does

1. **Privacy trimming** – removes configured distance around private start/end locations without overwriting the original logs.
2. **Cleaning and classification** – conservatively cleans each recording and separates primary, supplementary, preliminary and unusable data.
3. **V1 baseline dead reckoning** – integrates OBD speed with a simple constant-bias gyro heading estimate.
4. **V2 dead reckoning** – uses time-varying stationary gyro bias, robust filtering and quality-gated magnetometer heading-change fusion.
5. **V2 + OpenStreetMap** – uses the first post-privacy GPS point as a known start anchor and constrains the V2 route with topology-aware OSM road matching.
6. **Driving-behaviour features** – derives descriptive speed, acceleration, braking, RPM, throttle, boost and turn-rate features.
7. **Visualisation** – creates SVG route overlays, RMSE comparisons, final-error comparisons and error-over-distance plots.
8. **Showcase** – builds a printable local HTML report that presents the dataset, version progression and figures in one place.

## Installation on Windows

I use Python 3.14. The only non-standard package is `osmium`, which is required only for the `.osm.pbf` map-assisted stage.

```powershell
py -m pip install -r requirements.txt
```

Run the toolkit with:

```powershell
py main.py
```

or double-click `run_toolkit.bat`.

## Repository access, privacy and research data

The dissertation copy of this project is intended to be shared through a **private, restricted-access GitHub repository**, with the repository link provided in the dissertation appendix. It is not intended to be published as an unrestricted public repository.

I use restricted access because the complete research material can contain information that is sensitive in combination, including:

- approximate private start/end locations associated with my home and workplace;
- raw CAN/OBD telemetry collected from my vehicle;
- timestamps and journey sequences;
- GPS ground-truth data used for evaluation;
- vehicle operating and driving-behaviour signals;
- intermediate files that may make it possible to reconstruct or infer journeys.

Although individual CAN/OBD values may appear innocuous, the full time-series dataset can reveal considerably more when signals are combined. This project specifically demonstrates that vehicle telemetry can be used to infer route shape and driving behaviour, so distributing the complete raw dataset publicly would undermine the privacy risks being evaluated by the research itself.

The restricted repository is therefore used as an **academic evidence and reproducibility archive**. Access should be limited to people who need to inspect the implementation or evidence for assessment, such as my supervisor, dissertation markers or other authorised university staff.

The source-code version of `config/privacy_locations.json` contains **example coordinates only**. When I process my real recordings locally, I replace those examples with the approximate private locations that I want the privacy-trimming stage to protect. Those real values should not be copied into any public version of the project.

If I later create a public version of the repository, I should publish only the source code, example configuration and suitably anonymised/derived results. Raw journey logs, real private-location configuration, precise GPS data and other identifying telemetry should remain excluded.

Further detail is provided in `DATA_ACCESS_AND_PRIVACY.md`.

## Repository layout and relative paths

I separate source code, configuration, research data, documentation and map data into dedicated folders. The toolkit resolves repository resources relative to `main.py`, so cloning or moving the repository does not require me to edit absolute Windows paths.

The OpenStreetMap road extract is linked directly as:

```text
data/maps/study_area_roads.osm.pbf
```

When I select V2 map assistance, the toolkit uses this file automatically. I am not prompted to provide its location.

My raw recordings can be stored under `data/raw/`, while the source code is contained under `src/`.

### GitHub note for the OSM PBF

The study-area PBF is approximately 106 MiB, which exceeds GitHub's normal 100 MiB single-file limit. I therefore track `data/maps/*.pbf` using **Git LFS**. After installing Git LFS once, I use `git lfs install` before pushing the repository. The included `.gitattributes` already marks the PBF for LFS storage.

## Final primary-dataset rule

The final classifier treats a recording as primary dead-reckoning evidence when it has:

- at least 10 minutes of retained telemetry;
- at least 3 miles of OBD-integrated travel;
- at least 80% GPS ground-truth coverage;
- at least 80% rotation/gyro coverage.

Shorter recordings are retained as method-development evidence rather than deleted.

## Reconstruction design

### V1

V1 is deliberately simple. I project the phone rotation-rate vector onto gravity, estimate one stationary gyro bias, integrate relative heading and combine it with OBD vehicle speed.

### V2 without a map

V2 adds stable stationary-window detection, time-varying bias interpolation, zero-rate updates, robust filtering and cautious magnetometer heading-change fusion. GPS is not used to construct this route. GPS is used after reconstruction for evaluation and initial-heading alignment only.

### V2 with OSM

The map-assisted method assumes the first post-privacy GPS position is known. It does **not** use subsequent GPS positions or GPS bearing for inference. The OSM matcher keeps a small beam of plausible route hypotheses and scores road distance, heading, topology/continuity, road switching and weak speed/road-class plausibility.

## Output structure

Each processing run gets a new versioned output folder, so previous results are not deleted or overwritten. This also avoids common OneDrive file-lock issues.

The most useful final outputs are:

- `dataset_manifest.csv`
- `dead_reckoning_v1_summary.csv`
- `dead_reckoning_v2_summary.csv`
- `driving_behaviour_summary.csv`
- `comparison_visuals*/rmse_comparison.svg`
- `comparison_visuals*/<run>/route_progression.svg`
- `showcase*/index.html`

## Interpretation

This is a single-vehicle F56 Mini Cooper case study using commodity telemetry. I use the dataset to evaluate feasibility, accumulated drift, route-shape reconstruction, the effect of improved inertial processing and the effect of OSM road constraints. I do not present the resulting accuracy as a general guarantee for all vehicles.
