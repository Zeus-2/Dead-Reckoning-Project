"""Descriptive driving-behaviour feature extraction from my primary telemetry runs."""

import csv
import math
from pathlib import Path

from src.dead_reckoning.common import load_primary_run, project_rotation_onto_gravity, write_points_csv
from src.core.paths import resolve_primary_folder, versioned_output_folder
from src.core.settings import STATIONARY_SPEED_MPH
from src.core.telemetry_math import mean, median, percentile


def derive_acceleration(elapsed, data):
    values = [None] * len(data)

    for index in range(1, len(data)):
        dt = elapsed[index] - elapsed[index - 1]

        if dt <= 0.0 or dt > 3.0:
            continue

        previous_speed = data[index - 1].get("speed_mph")
        current_speed = data[index].get("speed_mph")

        if previous_speed is None or current_speed is None:
            continue

        values[index] = (
            (current_speed - previous_speed) * 0.44704 / dt
        )

    # I use a small median filter because OBD speed is quantised and sampled
    # more slowly than a dedicated inertial logger.
    filtered = list(values)

    for index in range(2, len(values) - 1):
        local = [
            value
            for value in values[index - 1:index + 2]
            if value is not None
        ]

        if local:
            filtered[index] = median(local)

    return filtered


def corrected_turn_rate(data):
    raw = project_rotation_onto_gravity(data)
    stationary = [
        yaw
        for row, yaw in zip(data, raw)
        if yaw is not None and (row.get("speed_mph") or 0.0) <= STATIONARY_SPEED_MPH
    ]
    bias = median(stationary)

    return [
        None if yaw is None else yaw - bias
        for yaw in raw
    ]


def count_stops(data):
    count = 0
    in_stop = False

    for row in data:
        stopped = (row.get("speed_mph") or 0.0) <= STATIONARY_SPEED_MPH

        if stopped and not in_stop:
            count += 1
            in_stop = True
        elif not stopped:
            in_stop = False

    # The initial parked state is not useful as a driving stop event.
    return max(0, count - 1)


def valid(values):
    return [value for value in values if value is not None and math.isfinite(value)]


def process_run(source, output_root):
    elapsed, data = load_primary_run(source)
    acceleration = derive_acceleration(elapsed, data)
    turn_rate = corrected_turn_rate(data)

    speed = valid([row.get("speed_mph") for row in data])
    moving_speed = [value for value in speed if value > STATIONARY_SPEED_MPH]
    rpm = valid([row.get("rpm") for row in data])
    throttle = valid([row.get("throttle_percent") for row in data])
    boost = valid([row.get("boost_psi") for row in data])
    accel = valid(acceleration)
    positive_accel = [value for value in accel if value > 0.0]
    braking = [-value for value in accel if value < 0.0]
    absolute_turn = [abs(value) for value in valid(turn_rate)]

    moving_rows = sum(
        1 for row in data if (row.get("speed_mph") or 0.0) > STATIONARY_SPEED_MPH
    )

    run_folder = output_root / source.stem
    run_folder.mkdir(parents=True, exist_ok=True)
    points_path = run_folder / "behaviour_timeseries.csv"

    write_points_csv(
        points_path,
        {
            "time_seconds": elapsed,
            "speed_mph": [row.get("speed_mph") for row in data],
            "derived_acceleration_m_s2": acceleration,
            "engine_rpm": [row.get("rpm") for row in data],
            "throttle_percent": [row.get("throttle_percent") for row in data],
            "boost_psi": [row.get("boost_psi") for row in data],
            "absolute_turn_rate_deg_s": [
                None if value is None else abs(value)
                for value in turn_rate
            ],
        },
    )

    return {
        "source_file": source.name,
        "duration_minutes": round((elapsed[-1] - elapsed[0]) / 60.0, 3),
        "moving_sample_percent": round(moving_rows / len(data) * 100.0, 2),
        "stop_count": count_stops(data),
        "mean_moving_speed_mph": round(mean(moving_speed), 3) if moving_speed else "",
        "max_speed_mph": round(max(speed), 3) if speed else "",
        "p95_speed_mph": round(percentile(speed, 95), 3) if speed else "",
        "p95_positive_acceleration_m_s2": round(percentile(positive_accel, 95), 3) if positive_accel else "",
        "p95_braking_m_s2": round(percentile(braking, 95), 3) if braking else "",
        "mean_rpm": round(mean(rpm), 3) if rpm else "",
        "p95_rpm": round(percentile(rpm, 95), 3) if rpm else "",
        "mean_throttle_percent": round(mean(throttle), 3) if throttle else "",
        "p95_throttle_percent": round(percentile(throttle, 95), 3) if throttle else "",
        "mean_boost_psi": round(mean(boost), 3) if boost else "",
        "p95_boost_psi": round(percentile(boost, 95), 3) if boost else "",
        "p95_absolute_turn_rate_deg_s": round(percentile(absolute_turn, 95), 3) if absolute_turn else "",
        "timeseries_output": str(points_path.relative_to(output_root)),
    }


def write_summary(output_root, records):
    path = output_root / "driving_behaviour_summary.csv"

    if records:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    return path


def write_method(output_root):
    text = """MY DRIVING-BEHAVIOUR FEATURE ANALYSIS
=====================================

I treat this as descriptive feature inference rather than a claim that I
can classify a driver's personality or driving style from a small dataset.

I derive acceleration/deceleration from OBD vehicle speed and calculate
summary features from speed, RPM, throttle, boost and phone turn-rate data.
The outputs include moving-speed statistics, braking/acceleration percentiles,
stop counts and turn-rate intensity.

Because my logger samples at a relatively modest rate, I use these features
for comparative analysis between recordings rather than claiming precise
high-frequency event detection.
"""

    (output_root / "METHOD_BEHAVIOUR.txt").write_text(text, encoding="utf-8")


def run(primary_source):
    primary_folder = resolve_primary_folder(primary_source)
    files = sorted(primary_folder.glob("*.csv"))

    if not files:
        raise ValueError("I could not find primary cleaned CSV files.")

    output_root = versioned_output_folder(primary_folder.parent, "behaviour_analysis")
    records = [process_run(source, output_root) for source in files]
    write_summary(output_root, records)
    write_method(output_root)
    return output_root, records


def main(default_source=None):
    print()
    print("My Driving-Behaviour Feature Analysis")
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

    print(f"\nI extracted behaviour features from {len(records)} primary run(s).")
    print(f"  {output_root}")
    return output_root


if __name__ == "__main__":
    main()
