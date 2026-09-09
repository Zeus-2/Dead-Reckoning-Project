"""My V1 baseline dead-reckoning experiment."""

import csv
import math
from pathlib import Path

from src.dead_reckoning.common import (
    distance_metrics,
    evaluate_relative_path,
    integrate_path,
    load_primary_run,
    project_rotation_onto_gravity,
    write_points_csv,
)
from src.core.paths import resolve_primary_folder, versioned_output_folder
from src.core.settings import (
    MAX_YAW_RATE_DEG_S,
    STATIONARY_SPEED_MPH,
    V1_GYRO_DEADBAND_DEG_S,
    YAW_SIGN,
)
from src.core.telemetry_math import median


def estimate_constant_bias(data, raw_yaw):
    stationary = []

    for row, yaw in zip(data, raw_yaw):
        speed = row.get("speed_mph")

        if (
            speed is not None
            and yaw is not None
            and speed <= STATIONARY_SPEED_MPH
            and abs(yaw) <= 5.0
        ):
            stationary.append(yaw)

    if stationary:
        return median(stationary), len(stationary)

    fallback = [yaw for yaw in raw_yaw if yaw is not None and abs(yaw) <= 5.0]
    return median(fallback), 0


def correct_yaw(data, raw_yaw, bias):
    corrected = []

    for row, yaw in zip(data, raw_yaw):
        speed = row.get("speed_mph")

        if yaw is None or speed is None or speed <= STATIONARY_SPEED_MPH:
            corrected.append(0.0)
            continue

        value = YAW_SIGN * (yaw - bias)

        if abs(value) < V1_GYRO_DEADBAND_DEG_S:
            value = 0.0

        corrected.append(
            max(-MAX_YAW_RATE_DEG_S, min(MAX_YAW_RATE_DEG_S, value))
        )

    return corrected


def process_run(source, output_root):
    elapsed, data = load_primary_run(source)
    raw_yaw = project_rotation_onto_gravity(data)
    bias, stationary_samples = estimate_constant_bias(data, raw_yaw)
    corrected = correct_yaw(data, raw_yaw, bias)
    x, y, heading, distance = integrate_path(elapsed, data, corrected)
    evaluation = evaluate_relative_path(x, y, data)
    distance_result = distance_metrics(data, distance)

    run_folder = output_root / source.stem
    run_folder.mkdir(parents=True, exist_ok=True)
    points_path = run_folder / "v1_points.csv"

    write_points_csv(
        points_path,
        {
            "time_seconds": elapsed,
            "speed_mph": [row.get("speed_mph") for row in data],
            "raw_projected_yaw_deg_s": raw_yaw,
            "corrected_yaw_deg_s": corrected,
            "relative_heading_deg": heading,
            "cumulative_obd_distance_m": distance,
            "dead_reckoned_x_m": x,
            "dead_reckoned_y_m": y,
            "evaluation_aligned_x_m": evaluation["aligned_x"],
            "evaluation_aligned_y_m": evaluation["aligned_y"],
            "gps_ground_truth_x_m": evaluation["gps_x"],
            "gps_ground_truth_y_m": evaluation["gps_y"],
            "position_error_m": evaluation["per_row_error"],
        },
    )

    metrics = evaluation["metrics"]

    return {
        "source_file": source.name,
        "rows": len(data),
        "duration_minutes": round((elapsed[-1] - elapsed[0]) / 60.0, 3),
        "gyro_bias_deg_s": round(bias, 6),
        "stationary_bias_samples": stationary_samples,
        "yaw_sign": YAW_SIGN,
        "obd_integrated_distance_m": distance_result["obd_distance_m"],
        "gps_track_distance_m": distance_result["gps_distance_m"],
        "distance_error_percent": distance_result["distance_error_percent"],
        "posthoc_alignment_rotation_deg": round(
            math.degrees(evaluation["alignment_rotation_rad"]),
            3,
        ),
        "mean_position_error_m": metrics["mean"],
        "median_position_error_m": metrics["median"],
        "rmse_position_error_m": metrics["rmse"],
        "p95_position_error_m": metrics["p95"],
        "final_position_error_m": metrics["final"],
        "final_relative_heading_deg": round(heading[-1], 3),
        "points_output": str(points_path.relative_to(output_root)),
    }


def write_summary(output_root, records):
    path = output_root / "dead_reckoning_v1_summary.csv"

    if records:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    return path


def write_method(output_root):
    text = """MY V1 BASELINE DEAD-RECKONING METHOD
====================================

I use OBD vehicle speed and the phone rotation-rate vector projected onto
the gravity direction. I estimate one constant gyroscope bias for the
whole trip from stationary samples, apply a small deadband, integrate yaw
rate for relative heading, and integrate OBD speed for travelled distance.

My inferred route starts at (0, 0) with a relative heading of 0 degrees.
GPS latitude, longitude and bearing are not used to construct the route.

For evaluation only, I convert the GPS trace to local X/Y metres and apply
one rigid rotation to the completed relative route because V1 has no
absolute starting heading. I do not scale the inferred route.

I keep V1 deliberately simple so it provides a baseline against which I
can compare the more developed V2 method.
"""

    (output_root / "METHOD_V1.txt").write_text(text, encoding="utf-8")


def run(primary_source):
    primary_folder = resolve_primary_folder(primary_source)
    files = sorted(primary_folder.glob("*.csv"))

    if not files:
        raise ValueError("I could not find any primary cleaned CSV files.")

    output_root = versioned_output_folder(primary_folder.parent, "dead_reckoning_v1")
    records = []

    for source in files:
        records.append(process_run(source, output_root))

    write_summary(output_root, records)
    write_method(output_root)
    return output_root, records


def main(default_source=None):
    print()
    print("My V1 Baseline Dead Reckoning")
    print("=" * 42)

    if default_source is not None:
        print("My default source is:")
        print(f"  {default_source}")
        print("Press Enter to use it, or type another cleaned/primary folder.")

    raw = input("Source folder: ").strip().strip('"')

    if not raw and default_source is not None:
        raw = str(default_source)

    if not raw:
        print("Cancelled.")
        return None

    try:
        output_root, records = run(raw)
    except Exception as error:
        print(f"[ERROR] {error}")
        return None

    for record in records:
        print(
            f"[V1] {record['source_file']}: "
            f"RMSE {record['rmse_position_error_m']} m"
        )

    print("\nMy V1 results are in:")
    print(f"  {output_root}")
    return output_root


if __name__ == "__main__":
    main()
