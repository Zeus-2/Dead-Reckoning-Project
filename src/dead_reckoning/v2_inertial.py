"""My V2 inertial processing: adaptive gyro correction and cautious magnetometer fusion."""

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
from src.core.settings import (
    MAX_YAW_RATE_DEG_S,
    STATIONARY_SPEED_MPH,
    V2_MAG_BLEND_PER_SECOND,
    V2_MAG_FIELD_MAD_MULTIPLIER,
    V2_MAG_MAX_RATE_DEG_S,
    V2_MAG_MAX_RATE_DISAGREEMENT_DEG_S,
    V2_MAG_MAX_SAMPLE_BLEND,
    V2_MAG_MIN_HORIZONTAL_FIELD_UT,
    V2_MAG_MIN_SPEED_MPH,
    V2_MAG_MIN_VALID_INTERVALS,
    V2_MAG_REFERENCE_SPEED_MPH,
    V2_MAX_DEADBAND_DEG_S,
    V2_MAX_STATIONARY_WINDOW_MAD_DEG_S,
    V2_MIN_DEADBAND_DEG_S,
    V2_MIN_STATIONARY_WINDOW_SECONDS,
    V2_SMOOTHING_ALPHA,
    YAW_SIGN,
)
from src.core.telemetry_math import angular_delta_deg, mad, median


def stationary_bias_anchors(elapsed, data, raw_yaw):
    windows = []
    current = []

    for index, (row, yaw) in enumerate(zip(data, raw_yaw)):
        speed = row.get("speed_mph")
        stationary = (
            speed is not None
            and yaw is not None
            and speed <= STATIONARY_SPEED_MPH
            and abs(yaw) <= 8.0
        )

        if stationary:
            current.append(index)
        elif current:
            windows.append(current)
            current = []

    if current:
        windows.append(current)

    anchors = []
    residuals = []

    for window in windows:
        if len(window) < 2:
            continue

        duration = elapsed[window[-1]] - elapsed[window[0]]

        if duration < V2_MIN_STATIONARY_WINDOW_SECONDS:
            continue

        values = [raw_yaw[index] for index in window if raw_yaw[index] is not None]

        if not values:
            continue

        centre = median(values)
        spread = 1.4826 * mad(values)

        # I reject stationary windows where the phone itself appears to move.
        if spread > V2_MAX_STATIONARY_WINDOW_MAD_DEG_S:
            continue

        anchor_time = median([elapsed[index] for index in window])
        anchors.append((anchor_time, centre, len(values)))
        residuals.extend(value - centre for value in values)

    return anchors, residuals


def interpolate_bias(elapsed, anchors, raw_yaw):
    if not elapsed:
        return [], anchors

    if not anchors:
        fallback = [value for value in raw_yaw if value is not None and abs(value) <= 5.0]
        value = median(fallback)
        return [value] * len(elapsed), [(elapsed[0], value, 0)]

    anchors = sorted(anchors, key=lambda item: item[0])

    if len(anchors) == 1:
        return [anchors[0][1]] * len(elapsed), anchors

    result = []
    anchor_index = 0

    for time_value in elapsed:
        if time_value <= anchors[0][0]:
            result.append(anchors[0][1])
            continue

        if time_value >= anchors[-1][0]:
            result.append(anchors[-1][1])
            continue

        while (
            anchor_index + 1 < len(anchors)
            and time_value > anchors[anchor_index + 1][0]
        ):
            anchor_index += 1

        t0, b0, _ = anchors[anchor_index]
        t1, b1, _ = anchors[anchor_index + 1]
        fraction = 0.0 if t1 == t0 else (time_value - t0) / (t1 - t0)
        result.append(b0 + (b1 - b0) * fraction)

    return result, anchors


def median_filter_three(values):
    if len(values) < 3:
        return list(values)

    filtered = list(values)

    for index in range(1, len(values) - 1):
        filtered[index] = median(
            [values[index - 1], values[index], values[index + 1]]
        )

    return filtered


def correct_yaw_v2(elapsed, data, raw_yaw):
    anchors, stationary_residuals = stationary_bias_anchors(elapsed, data, raw_yaw)
    bias_series, anchors = interpolate_bias(elapsed, anchors, raw_yaw)

    noise_sigma = 1.4826 * mad(stationary_residuals)
    deadband = max(
        V2_MIN_DEADBAND_DEG_S,
        min(V2_MAX_DEADBAND_DEG_S, 2.5 * noise_sigma),
    )

    corrected = []

    for row, yaw, bias in zip(data, raw_yaw, bias_series):
        speed = row.get("speed_mph")

        if yaw is None or speed is None or speed <= STATIONARY_SPEED_MPH:
            corrected.append(0.0)
            continue

        value = YAW_SIGN * (yaw - bias)

        if abs(value) < deadband:
            value = 0.0

        corrected.append(
            max(-MAX_YAW_RATE_DEG_S, min(MAX_YAW_RATE_DEG_S, value))
        )

    corrected = median_filter_three(corrected)

    # I use a light EMA after the median filter to reduce isolated noise
    # without flattening ordinary bends and roundabouts.
    smoothed = []
    state = 0.0

    for row, value in zip(data, corrected):
        speed = row.get("speed_mph") or 0.0

        if speed <= STATIONARY_SPEED_MPH:
            state = 0.0
        else:
            state = V2_SMOOTHING_ALPHA * value + (1.0 - V2_SMOOTHING_ALPHA) * state

        smoothed.append(state)

    return smoothed, bias_series, anchors, deadband, noise_sigma


def choose_horizontal_body_axis(data):
    scores = [[], [], []]

    for row in data:
        gravity = (row.get("grav_x"), row.get("grav_y"), row.get("grav_z"))

        if None in gravity:
            continue

        norm = math.sqrt(sum(value * value for value in gravity))

        if norm < 1e-9:
            continue

        for axis in range(3):
            scores[axis].append(abs(gravity[axis]) / norm)

    medians = [median(values) if values else 1.0 for values in scores]
    return min(range(3), key=lambda axis: medians[axis]), medians


def magnetic_heading_series(data):
    """Create tilt-compensated magnetic headings without using GPS."""

    axis, axis_scores = choose_horizontal_body_axis(data)
    strengths = []

    for row in data:
        magnetic = (row.get("mag_x"), row.get("mag_y"), row.get("mag_z"))

        if None in magnetic:
            continue

        strengths.append(math.sqrt(sum(value * value for value in magnetic)))

    if not strengths:
        return [None] * len(data), axis, axis_scores, 0.0, 0.0

    field_median = median(strengths)
    field_sigma = 1.4826 * mad(strengths)

    if field_sigma <= 0.0:
        field_low = max(V2_MAG_MIN_HORIZONTAL_FIELD_UT, field_median * 0.35)
        field_high = max(field_low + 1.0, field_median * 2.5)
    else:
        spread = V2_MAG_FIELD_MAD_MULTIPLIER * field_sigma
        field_low = max(V2_MAG_MIN_HORIZONTAL_FIELD_UT, field_median - spread)
        field_high = field_median + spread

    headings = []

    for row in data:
        values = (
            row.get("grav_x"),
            row.get("grav_y"),
            row.get("grav_z"),
            row.get("mag_x"),
            row.get("mag_y"),
            row.get("mag_z"),
        )

        if None in values:
            headings.append(None)
            continue

        gx, gy, gz, mx, my, mz = values
        gravity_norm = math.sqrt(gx * gx + gy * gy + gz * gz)
        field_strength = math.sqrt(mx * mx + my * my + mz * mz)

        if gravity_norm < 1e-9 or not (field_low <= field_strength <= field_high):
            headings.append(None)
            continue

        ux, uy, uz = gx / gravity_norm, gy / gravity_norm, gz / gravity_norm
        dot_mg = mx * ux + my * uy + mz * uz
        nx, ny, nz = mx - dot_mg * ux, my - dot_mg * uy, mz - dot_mg * uz
        north_norm = math.sqrt(nx * nx + ny * ny + nz * nz)

        if north_norm < V2_MAG_MIN_HORIZONTAL_FIELD_UT:
            headings.append(None)
            continue

        nx, ny, nz = nx / north_norm, ny / north_norm, nz / north_norm
        ex = uy * nz - uz * ny
        ey = uz * nx - ux * nz
        ez = ux * ny - uy * nx
        east_norm = math.sqrt(ex * ex + ey * ey + ez * ez)

        if east_norm < 1e-9:
            headings.append(None)
            continue

        ex, ey, ez = ex / east_norm, ey / east_norm, ez / east_norm

        body = [0.0, 0.0, 0.0]
        body[axis] = 1.0
        dot_bg = body[0] * ux + body[1] * uy + body[2] * uz
        bx = body[0] - dot_bg * ux
        by = body[1] - dot_bg * uy
        bz = body[2] - dot_bg * uz
        body_norm = math.sqrt(bx * bx + by * by + bz * bz)

        if body_norm < 0.35:
            headings.append(None)
            continue

        bx, by, bz = bx / body_norm, by / body_norm, bz / body_norm
        north_component = bx * nx + by * ny + bz * nz
        east_component = bx * ex + by * ey + bz * ez
        headings.append(math.degrees(math.atan2(east_component, north_component)) % 360.0)

    return headings, axis, axis_scores, field_median, field_sigma


def choose_magnetic_sign(elapsed, data, magnetic_heading, gyro_yaw):
    positive = []
    negative = []

    for index in range(1, len(data)):
        h0 = magnetic_heading[index - 1]
        h1 = magnetic_heading[index]

        if h0 is None or h1 is None:
            continue

        dt = elapsed[index] - elapsed[index - 1]
        speed = data[index].get("speed_mph") or 0.0

        if dt <= 0.0 or dt > 2.0 or speed < V2_MAG_REFERENCE_SPEED_MPH:
            continue

        magnetic_rate = angular_delta_deg(h1, h0) / dt
        gyro_rate = (gyro_yaw[index - 1] + gyro_yaw[index]) * 0.5

        if abs(magnetic_rate) > V2_MAG_MAX_RATE_DEG_S:
            continue

        positive.append(abs(magnetic_rate - gyro_rate))
        negative.append(abs(-magnetic_rate - gyro_rate))

    if not positive:
        return 1.0, None

    positive_score = median(positive)
    negative_score = median(negative)

    if negative_score < positive_score:
        return -1.0, negative_score

    return 1.0, positive_score


def blend_gyro_with_magnetometer(elapsed, data, gyro_yaw):
    """Blend local magnetic heading changes into my corrected gyro signal."""

    headings, axis, axis_scores, field_median, field_sigma = magnetic_heading_series(data)
    sign, sign_score = choose_magnetic_sign(elapsed, data, headings, gyro_yaw)

    fused = list(gyro_yaw)
    used = [False] * len(data)
    candidate_intervals = 0

    for index in range(1, len(data)):
        h0 = headings[index - 1]
        h1 = headings[index]
        speed = data[index].get("speed_mph") or 0.0
        dt = elapsed[index] - elapsed[index - 1]

        if (
            h0 is None
            or h1 is None
            or speed < V2_MAG_MIN_SPEED_MPH
            or dt <= 0.0
            or dt > 2.0
        ):
            continue

        magnetic_rate = sign * angular_delta_deg(h1, h0) / dt
        gyro_rate = (gyro_yaw[index - 1] + gyro_yaw[index]) * 0.5

        if abs(magnetic_rate) > V2_MAG_MAX_RATE_DEG_S:
            continue

        if abs(magnetic_rate - gyro_rate) > V2_MAG_MAX_RATE_DISAGREEMENT_DEG_S:
            continue

        candidate_intervals += 1

    # If there are too few trustworthy intervals I leave V2 gyro-only.
    enabled = candidate_intervals >= V2_MAG_MIN_VALID_INTERVALS

    if enabled:
        for index in range(1, len(data)):
            h0 = headings[index - 1]
            h1 = headings[index]
            speed = data[index].get("speed_mph") or 0.0
            dt = elapsed[index] - elapsed[index - 1]

            if (
                h0 is None
                or h1 is None
                or speed < V2_MAG_MIN_SPEED_MPH
                or dt <= 0.0
                or dt > 2.0
            ):
                continue

            magnetic_rate = sign * angular_delta_deg(h1, h0) / dt
            gyro_rate = (gyro_yaw[index - 1] + gyro_yaw[index]) * 0.5

            if (
                abs(magnetic_rate) > V2_MAG_MAX_RATE_DEG_S
                or abs(magnetic_rate - gyro_rate) > V2_MAG_MAX_RATE_DISAGREEMENT_DEG_S
            ):
                continue

            blend = min(V2_MAG_MAX_SAMPLE_BLEND, V2_MAG_BLEND_PER_SECOND * dt)
            fused[index] = (1.0 - blend) * gyro_yaw[index] + blend * magnetic_rate
            used[index] = True

    diagnostics = {
        "magnetometer_enabled": enabled,
        "magnetometer_body_axis": ("X", "Y", "Z")[axis],
        "magnetometer_axis_gravity_scores": axis_scores,
        "magnetometer_field_median_uT": field_median,
        "magnetometer_field_sigma_uT": field_sigma,
        "magnetometer_sign": sign,
        "magnetometer_sign_score_deg_s": sign_score,
        "magnetometer_intervals_available": candidate_intervals,
        "magnetometer_intervals_used": sum(used),
        "magnetometer_used": used,
    }

    return fused, diagnostics


def process_no_map(source, output_root):
    elapsed, data = load_primary_run(source)
    raw_yaw = project_rotation_onto_gravity(data)
    corrected, bias_series, anchors, deadband, noise_sigma = correct_yaw_v2(
        elapsed,
        data,
        raw_yaw,
    )
    fused_yaw, mag = blend_gyro_with_magnetometer(elapsed, data, corrected)
    x, y, heading, distance = integrate_path(elapsed, data, fused_yaw)
    evaluation = evaluate_relative_path(x, y, data)
    distance_result = distance_metrics(data, distance)

    run_folder = output_root / source.stem
    run_folder.mkdir(parents=True, exist_ok=True)
    points_path = run_folder / "v2_no_map_points.csv"

    write_points_csv(
        points_path,
        {
            "time_seconds": elapsed,
            "speed_mph": [row.get("speed_mph") for row in data],
            "raw_projected_yaw_deg_s": raw_yaw,
            "estimated_bias_deg_s": bias_series,
            "corrected_gyro_yaw_deg_s": corrected,
            "fused_yaw_deg_s": fused_yaw,
            "magnetometer_correction_used": [int(value) for value in mag["magnetometer_used"]],
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

    return {
        "source": source,
        "elapsed": elapsed,
        "data": data,
        "raw_yaw": raw_yaw,
        "bias_series": bias_series,
        "corrected_yaw": corrected,
        "fused_yaw": fused_yaw,
        "heading": heading,
        "distance": distance,
        "x": x,
        "y": y,
        "evaluation": evaluation,
        "distance_result": distance_result,
        "gyro_anchor_count": len(anchors),
        "gyro_anchor_samples": sum(anchor[2] for anchor in anchors),
        "adaptive_deadband_deg_s": deadband,
        "stationary_noise_sigma_deg_s": noise_sigma,
        "mag": mag,
        "points_path": points_path,
        "run_folder": run_folder,
    }

