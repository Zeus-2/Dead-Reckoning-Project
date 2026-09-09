"""My V2 experiment runner: inertial reconstruction plus optional OSM assistance."""

import csv
from pathlib import Path

from src.core.paths import (
    normalise_run_name,
    resolve_primary_folder,
    versioned_output_folder,
)
from src.core.settings import MAP_PBF_FILE, PROJECT_ROOT
from src.dead_reckoning.v2_inertial import process_no_map


def write_summary(output_root, records):
    path = output_root / "dead_reckoning_v2_summary.csv"

    if records:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    return path


def improvement_percent(old, new):
    try:
        old = float(old)
        new = float(new)
    except (TypeError, ValueError):
        return ""

    if old <= 0.0:
        return ""

    return round((old - new) / old * 100.0, 2)


def load_v1_rmse(cleaned_root):
    candidates = [
        folder
        for folder in cleaned_root.iterdir()
        if folder.is_dir() and folder.name.startswith("dead_reckoning_v1")
    ]

    if not candidates:
        return {}

    folder = max(candidates, key=lambda path: path.stat().st_mtime)
    summary = folder / "dead_reckoning_v1_summary.csv"

    if not summary.exists():
        return {}

    result = {}

    with summary.open("r", encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            result[normalise_run_name(row.get("source_file", ""))] = row.get(
                "rmse_position_error_m",
                "",
            )

    return result


def write_method(output_root, map_enabled):
    map_text = """
V2 WITH OSM MAP ASSISTANCE
--------------------------
I use only the first post-privacy GPS point as a known starting anchor.
I do not use later GPS positions or GPS bearing to infer the route.

I load drivable OpenStreetMap roads around the experiment area, derive
candidate starting directions from nearby roads and use the early V2
inertial trajectory to select an initial direction. I then use a small
beam search instead of irreversible nearest-road snapping. Each candidate
is scored using distance, heading consistency, OSM topology/continuity,
road switching and a weak speed/road-class plausibility penalty.

If a plausible road cannot be found, the matcher can keep an inertial
state rather than forcing the route onto an arbitrary nearby road.
""" if map_enabled else ""

    text = f"""MY V2 DEAD-RECKONING METHOD
============================

V2 WITHOUT MAP ASSISTANCE
-------------------------
I project the phone Rotation Rate X/Y/Z vector onto gravity, identify
stable stationary windows and estimate a time-varying gyroscope bias.
I apply zero-rate updates, an adaptive deadband, a short median filter and
a light exponential smoother.

Where the phone magnetometer is sufficiently consistent with the gyro, I
use tilt-compensated magnetic heading changes as a weak local correction.
I quality-gate these intervals and disable magnetometer fusion completely
when too few trustworthy intervals are available.

I integrate the resulting yaw rate for relative heading and OBD speed for
distance. GPS latitude, longitude and bearing are not used to construct
the no-map route. GPS is used only afterwards for evaluation and one
rigid initial-heading alignment; the reconstructed route is never scaled.
{map_text}
EVALUATION
----------
I report V1, V2 no-map and V2 map-assisted positional error where those
results are available. Raw latitude/longitude are not written into my
result CSV files or visualisations.
"""

    (output_root / "METHOD_V2.txt").write_text(text, encoding="utf-8")


def run(primary_source, mode="both", pbf_path=None):
    primary_folder = resolve_primary_folder(primary_source)
    files = sorted(primary_folder.glob("*.csv"))

    if not files:
        raise ValueError("I could not find any primary cleaned CSV files.")

    mode = str(mode).lower()

    if mode not in {"no_map", "map", "both"}:
        raise ValueError("V2 mode must be no_map, map or both.")

    output_root = versioned_output_folder(primary_folder.parent, "dead_reckoning_v2")
    no_map_cache = {
        source: process_no_map(source, output_root)
        for source in files
    }

    map_results = {}
    map_enabled = mode in {"map", "both"}

    if map_enabled:
        from src.mapping.osm_network import build_network_for_runs
        from src.mapping.osm_map_match import process_map_run

        if pbf_path is None:
            pbf_path = MAP_PBF_FILE

        pbf_path = Path(pbf_path)

        if not pbf_path.exists():
            relative = pbf_path

            try:
                relative = pbf_path.relative_to(PROJECT_ROOT)
            except ValueError:
                pass

            raise ValueError(
                f"My bundled OSM map is missing: {relative}. "
                "I keep it at data/maps/study_area_roads.osm.pbf."
            )

        network, map_origin = build_network_for_runs(
            Path(pbf_path),
            list(no_map_cache.values()),
        )

        for source, no_map in no_map_cache.items():
            map_results[source] = process_map_run(
                no_map,
                network,
                map_origin,
                no_map["run_folder"],
            )

    v1_rmse = load_v1_rmse(primary_folder.parent)
    records = []

    for source in files:
        no_map = no_map_cache[source]
        map_result = map_results.get(source)
        metrics = no_map["evaluation"]["metrics"]
        map_metrics = map_result["metrics"] if map_result else {}
        v1_value = v1_rmse.get(normalise_run_name(source.name), "")

        records.append({
            "source_file": source.name,
            "duration_minutes": round((no_map["elapsed"][-1] - no_map["elapsed"][0]) / 60.0, 3),
            "obd_integrated_distance_m": no_map["distance_result"]["obd_distance_m"],
            "gps_track_distance_m": no_map["distance_result"]["gps_distance_m"],
            "distance_error_percent": no_map["distance_result"]["distance_error_percent"],
            "v1_rmse_position_error_m": v1_value,
            "v2_no_map_rmse_position_error_m": metrics["rmse"],
            "v2_no_map_mean_error_m": metrics["mean"],
            "v2_no_map_p95_error_m": metrics["p95"],
            "v2_no_map_final_error_m": metrics["final"],
            "v2_no_map_improvement_vs_v1_percent": improvement_percent(v1_value, metrics["rmse"]),
            "v2_gyro_bias_anchor_windows": no_map["gyro_anchor_count"],
            "v2_gyro_bias_anchor_samples": no_map["gyro_anchor_samples"],
            "v2_adaptive_deadband_deg_s": round(no_map["adaptive_deadband_deg_s"], 4),
            "v2_stationary_noise_sigma_deg_s": round(no_map["stationary_noise_sigma_deg_s"], 4),
            "v2_magnetometer_enabled": no_map["mag"]["magnetometer_enabled"],
            "v2_magnetometer_body_axis": no_map["mag"]["magnetometer_body_axis"],
            "v2_magnetometer_intervals_used": no_map["mag"]["magnetometer_intervals_used"],
            "v2_map_rmse_position_error_m": map_metrics.get("rmse", ""),
            "v2_map_mean_error_m": map_metrics.get("mean", ""),
            "v2_map_p95_error_m": map_metrics.get("p95", ""),
            "v2_map_final_error_m": map_metrics.get("final", ""),
            "v2_map_improvement_vs_v1_percent": improvement_percent(v1_value, map_metrics.get("rmse", "")),
            "v2_map_improvement_vs_v2_no_map_percent": improvement_percent(metrics["rmse"], map_metrics.get("rmse", "")),
            "v2_map_initial_bearing_deg": map_result.get("initial_bearing_deg", "") if map_result else "",
            "v2_map_matched_percent": map_result.get("matched_percent", "") if map_result else "",
            "v2_map_median_snap_distance_m": map_result.get("median_snap_distance_m", "") if map_result else "",
        })

    write_summary(output_root, records)
    write_method(output_root, map_enabled)
    return output_root, records



def main(default_source=None):
    print()
    print("My V2 Dead Reckoning")
    print("=" * 42)
    print("1. Run my V2 without map assistance")
    print("2. Run my V2 with OSM map assistance")
    print("3. Run both V2 methods")

    choice = input("Select V2 mode [3]: ").strip() or "3"
    mode = {"1": "no_map", "2": "map", "3": "both"}.get(choice)

    if mode is None:
        print("Invalid option.")
        return None

    if default_source is not None:
        print("\nMy default cleaned source is:")
        print(f"  {default_source}")
        print("Press Enter to use it, or type another cleaned/primary folder.")

    raw = input("Source folder: ").strip().strip('"')

    if not raw and default_source is not None:
        raw = str(default_source)

    if not raw:
        print("Cancelled.")
        return None

    try:
        primary_folder = resolve_primary_folder(raw)

        if mode in {"map", "both"}:
            print("My bundled OSM road file:")
            print(f"  {MAP_PBF_FILE.relative_to(PROJECT_ROOT)}")

        output_root, records = run(primary_folder, mode=mode)
    except Exception as error:
        print(f"[ERROR] {error}")
        return None

    for record in records:
        line = f"[V2 NO-MAP] {record['source_file']}: RMSE {record['v2_no_map_rmse_position_error_m']} m"
        if record["v2_map_rmse_position_error_m"] != "":
            line += f" | OSM RMSE {record['v2_map_rmse_position_error_m']} m"
        print(line)

    print("\nMy V2 results are in:")
    print(f"  {output_root}")
    return output_root


if __name__ == "__main__":
    main()
