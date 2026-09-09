"""Shared dead-reckoning functions used by my V1 and V2 experiments."""

import csv
import math
from pathlib import Path

from src.core.settings import MAX_YAW_RATE_DEG_S, STATIONARY_SPEED_MPH
from src.core.telemetry_io import load_run
from src.core.telemetry_math import (
    best_rigid_rotation,
    evaluate_position_errors,
    gps_track_distance,
    local_xy_from_gps,
    metric_summary,
    rotate_xy,
)


def project_rotation_onto_gravity(data):
    """Project the phone rotation vector onto the measured vertical axis."""

    result = []

    for row in data:
        values = (
            row.get("rot_x"),
            row.get("rot_y"),
            row.get("rot_z"),
            row.get("grav_x"),
            row.get("grav_y"),
            row.get("grav_z"),
        )

        if None in values:
            result.append(None)
            continue

        rx, ry, rz, gx, gy, gz = values
        gravity_norm = math.sqrt(gx * gx + gy * gy + gz * gz)

        if gravity_norm < 1e-9:
            result.append(None)
            continue

        result.append((rx * gx + ry * gy + rz * gz) / gravity_norm)

    return result


def integrate_path(elapsed, data, yaw_rate):
    """Integrate my corrected yaw and OBD speed into a relative X/Y path."""

    count = len(data)
    x = [0.0] * count
    y = [0.0] * count
    heading = [0.0] * count
    distance = [0.0] * count

    for index in range(1, count):
        dt = elapsed[index] - elapsed[index - 1]

        x[index] = x[index - 1]
        y[index] = y[index - 1]
        heading[index] = heading[index - 1]
        distance[index] = distance[index - 1]

        if dt <= 0.0 or dt > 10.0:
            continue

        previous_speed = max(0.0, data[index - 1].get("speed_mph") or 0.0) * 0.44704
        current_speed = max(0.0, data[index].get("speed_mph") or 0.0) * 0.44704
        step_distance = (previous_speed + current_speed) * 0.5 * dt

        previous_rate = max(
            -MAX_YAW_RATE_DEG_S,
            min(MAX_YAW_RATE_DEG_S, yaw_rate[index - 1] or 0.0),
        )
        current_rate = max(
            -MAX_YAW_RATE_DEG_S,
            min(MAX_YAW_RATE_DEG_S, yaw_rate[index] or 0.0),
        )

        heading_change = (previous_rate + current_rate) * 0.5 * dt
        midpoint_heading = heading[index - 1] + heading_change * 0.5
        midpoint_rad = math.radians(midpoint_heading)

        # I define relative heading 0 degrees as movement along +Y.
        x[index] = x[index - 1] + step_distance * math.sin(midpoint_rad)
        y[index] = y[index - 1] + step_distance * math.cos(midpoint_rad)
        heading[index] = heading[index - 1] + heading_change
        distance[index] = distance[index - 1] + step_distance

    return x, y, heading, distance


def evaluate_relative_path(x, y, data):
    """Evaluate a GPS-free relative route using GPS only after reconstruction."""

    gps_x, gps_y, gps_origin = local_xy_from_gps(data)
    rotation = best_rigid_rotation(x, y, gps_x, gps_y, data)
    aligned_x, aligned_y = rotate_xy(x, y, rotation)
    errors, per_row_error = evaluate_position_errors(
        aligned_x,
        aligned_y,
        gps_x,
        gps_y,
        data,
    )

    return {
        "gps_x": gps_x,
        "gps_y": gps_y,
        "gps_origin": gps_origin,
        "alignment_rotation_rad": rotation,
        "aligned_x": aligned_x,
        "aligned_y": aligned_y,
        "errors": errors,
        "per_row_error": per_row_error,
        "metrics": metric_summary(errors),
    }


def distance_metrics(data, cumulative_distance):
    obd_distance = cumulative_distance[-1] if cumulative_distance else 0.0
    gps_distance = gps_track_distance(data)

    error_percent = ""

    if gps_distance > 0.0:
        error_percent = round(
            (obd_distance - gps_distance) / gps_distance * 100.0,
            3,
        )

    return {
        "obd_distance_m": round(obd_distance, 3),
        "gps_distance_m": round(gps_distance, 3),
        "distance_error_percent": error_percent,
    }


def write_points_csv(path, columns):
    """Write equal-length per-sample series without publishing raw lat/lon."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    names = list(columns.keys())
    lengths = {len(values) for values in columns.values()}

    if len(lengths) > 1:
        raise ValueError("My output series do not all have the same length.")

    count = next(iter(lengths), 0)

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(names)

        for index in range(count):
            writer.writerow([columns[name][index] for name in names])


def load_primary_run(path):
    elapsed, data = load_run(path)

    if len(data) < 2:
        raise ValueError("I do not have enough rows to dead-reckon this recording.")

    if not any(row.get("speed_mph") is not None for row in data):
        raise ValueError("I could not find usable vehicle-speed data.")

    return elapsed, data


def zero_yaw_when_stationary(data, yaw_rate):
    result = []

    for row, value in zip(data, yaw_rate):
        speed = row.get("speed_mph") or 0.0
        result.append(0.0 if speed <= STATIONARY_SPEED_MPH else (value or 0.0))

    return result
