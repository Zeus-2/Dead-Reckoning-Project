"""Beam-search OSM map matching for my V2 reconstruction."""

import math
from dataclasses import dataclass
from pathlib import Path

from src.dead_reckoning.common import write_points_csv
from src.mapping.osm_network import RoadNetwork, road_candidates, road_speed_penalty
from src.core.settings import (
    MAP_BEAM_WIDTH,
    MAP_CANDIDATES_PER_STATE,
    MAP_HEADING_COST_M_PER_DEG,
    MAP_INITIAL_SCORE_MAX_POINTS,
    MAP_INITIAL_SCORE_SAMPLE_STEP,
    MAP_INITIAL_SEARCH_RADIUS_M,
    MAP_MAX_LOCAL_COST_M,
    MAP_SEARCH_RADIUS_M,
    MAP_SEGMENT_SWITCH_PENALTY_M,
    MAP_UNMATCHED_PENALTY_M,
    STATIONARY_SPEED_MPH,
)
from src.core.telemetry_math import (
    evaluate_position_errors,
    first_valid_gps,
    latlon_to_xy,
    local_xy_from_gps,
    median,
    metric_summary,
)


def candidate_initial_bearings(network, start_x, start_y):
    candidates = road_candidates(
        network,
        start_x,
        start_y,
        MAP_INITIAL_SEARCH_RADIUS_M,
        heading=None,
        limit=20,
    )

    bearings = []

    for _distance, _heading_difference, _sx, _sy, segment_index in candidates:
        heading = network.segments[segment_index].heading
        bearings.extend((heading, (heading + 180.0) % 360.0))

    # I de-duplicate bearings within a few degrees so parallel road segments
    # do not unnecessarily dominate the initial search.
    unique = []

    for bearing in bearings:
        if not any(abs((bearing - other + 180.0) % 360.0 - 180.0) < 4.0 for other in unique):
            unique.append(bearing)

    return unique or [0.0]


def transform_relative_to_map(rel_x, rel_y, start_x, start_y, bearing_deg):
    angle = math.radians(bearing_deg)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    xs = []
    ys = []

    for x, y in zip(rel_x, rel_y):
        # Relative +Y is heading zero in my inertial coordinates.
        east = cosine * x + sine * y
        north = -sine * x + cosine * y
        xs.append(start_x + east)
        ys.append(start_y + north)

    return xs, ys


def score_initial_bearing(network, rel_x, rel_y, start_x, start_y, bearing):
    map_x, map_y = transform_relative_to_map(rel_x, rel_y, start_x, start_y, bearing)
    costs = []

    upper = min(len(map_x), MAP_INITIAL_SCORE_MAX_POINTS)

    for index in range(0, upper, MAP_INITIAL_SCORE_SAMPLE_STEP):
        if index == 0:
            continue

        dx = map_x[index] - map_x[index - 1]
        dy = map_y[index] - map_y[index - 1]
        movement_heading = math.degrees(math.atan2(dx, dy)) % 360.0 if (dx or dy) else bearing

        candidates = road_candidates(
            network,
            map_x[index],
            map_y[index],
            MAP_INITIAL_SEARCH_RADIUS_M,
            heading=movement_heading,
            limit=5,
        )

        if not candidates:
            costs.append(MAP_INITIAL_SEARCH_RADIUS_M)
            continue

        distance, heading_difference, *_ = candidates[0]
        costs.append(distance + MAP_HEADING_COST_M_PER_DEG * heading_difference)

    return median(costs) if costs else float("inf")


def select_initial_bearing(network, rel_x, rel_y, start_x, start_y):
    bearings = candidate_initial_bearings(network, start_x, start_y)
    scored = [
        (score_initial_bearing(network, rel_x, rel_y, start_x, start_y, bearing), bearing)
        for bearing in bearings
    ]
    scored.sort(key=lambda item: item[0])
    return scored[0][1]


@dataclass
class BeamState:
    x: float
    y: float
    segment_index: int | None
    cost: float
    parent_index: int | None
    matched: bool
    snap_distance: float | None
    local_cost: float


def map_match_beam(network, rel_x, rel_y, heading, data, start_x, start_y, initial_bearing):
    raw_x, raw_y = transform_relative_to_map(
        rel_x,
        rel_y,
        start_x,
        start_y,
        initial_bearing,
    )

    layers = [[BeamState(start_x, start_y, None, 0.0, None, False, 0.0, 0.0)]]

    for index in range(1, len(rel_x)):
        previous_layer = layers[-1]
        dx = raw_x[index] - raw_x[index - 1]
        dy = raw_y[index] - raw_y[index - 1]
        speed = data[index].get("speed_mph") or 0.0
        absolute_heading = (initial_bearing + heading[index]) % 360.0
        new_states = []

        for previous_index, previous in enumerate(previous_layer):
            if speed <= STATIONARY_SPEED_MPH:
                new_states.append(
                    BeamState(
                        previous.x,
                        previous.y,
                        previous.segment_index,
                        previous.cost,
                        previous_index,
                        previous.matched,
                        0.0,
                        0.0,
                    )
                )
                continue

            predicted_x = previous.x + dx
            predicted_y = previous.y + dy
            candidates = road_candidates(
                network,
                predicted_x,
                predicted_y,
                MAP_SEARCH_RADIUS_M,
                heading=absolute_heading,
                limit=MAP_CANDIDATES_PER_STATE,
            )

            for distance, heading_difference, sx, sy, segment_index in candidates:
                segment = network.segments[segment_index]
                continuity = network.continuity_penalty(previous.segment_index, segment_index)
                switch_penalty = (
                    MAP_SEGMENT_SWITCH_PENALTY_M
                    if previous.segment_index is not None and previous.segment_index != segment_index
                    else 0.0
                )
                local_cost = (
                    distance
                    + MAP_HEADING_COST_M_PER_DEG * heading_difference
                    + continuity
                    + switch_penalty
                    + road_speed_penalty(segment, speed)
                )

                if local_cost > MAP_MAX_LOCAL_COST_M:
                    continue

                new_states.append(
                    BeamState(
                        sx,
                        sy,
                        segment_index,
                        previous.cost + local_cost,
                        previous_index,
                        True,
                        distance,
                        local_cost,
                    )
                )

            # I always retain one inertial continuation so the matcher is not
            # forced to snap onto an implausible road when the candidate set is poor.
            unmatched_cost = MAP_UNMATCHED_PENALTY_M
            new_states.append(
                BeamState(
                    predicted_x,
                    predicted_y,
                    previous.segment_index,
                    previous.cost + unmatched_cost,
                    previous_index,
                    False,
                    None,
                    unmatched_cost,
                )
            )

        if not new_states:
            previous = min(previous_layer, key=lambda state: state.cost)
            new_states = [
                BeamState(
                    previous.x + dx,
                    previous.y + dy,
                    previous.segment_index,
                    previous.cost + MAP_UNMATCHED_PENALTY_M,
                    previous_layer.index(previous),
                    False,
                    None,
                    MAP_UNMATCHED_PENALTY_M,
                )
            ]

        new_states.sort(key=lambda state: state.cost)
        layers.append(new_states[:MAP_BEAM_WIDTH])

    final_index = min(
        range(len(layers[-1])),
        key=lambda index: layers[-1][index].cost,
    )

    selected = [None] * len(layers)
    current_index = final_index

    for layer_index in range(len(layers) - 1, -1, -1):
        state = layers[layer_index][current_index]
        selected[layer_index] = state

        if state.parent_index is None:
            break

        current_index = state.parent_index

    return {
        "x": [state.x for state in selected],
        "y": [state.y for state in selected],
        "segment_index": [state.segment_index for state in selected],
        "matched": [state.matched for state in selected],
        "snap_distance": [state.snap_distance for state in selected],
        "local_cost": [state.local_cost for state in selected],
    }


def process_map_run(no_map, network, map_origin, run_folder):
    data = no_map["data"]
    start_gps = first_valid_gps(data)

    if start_gps is None:
        raise ValueError("I do not have a valid first GPS anchor for this run.")

    start_x, start_y = latlon_to_xy(start_gps[0], start_gps[1], map_origin)
    initial_bearing = select_initial_bearing(
        network,
        no_map["x"],
        no_map["y"],
        start_x,
        start_y,
    )

    result = map_match_beam(
        network,
        no_map["x"],
        no_map["y"],
        no_map["heading"],
        data,
        start_x,
        start_y,
        initial_bearing,
    )

    gps_x, gps_y, _origin = local_xy_from_gps(data, origin=map_origin)
    errors, per_row_error = evaluate_position_errors(
        result["x"],
        result["y"],
        gps_x,
        gps_y,
        data,
    )
    metrics = metric_summary(errors)

    matched_moving = []
    snap_distances = []

    for row, matched, snap in zip(data, result["matched"], result["snap_distance"]):
        if (row.get("speed_mph") or 0.0) > 2.0:
            matched_moving.append(bool(matched))

        if matched and snap is not None:
            snap_distances.append(snap)

    matched_percent = (
        round(sum(matched_moving) / len(matched_moving) * 100.0, 2)
        if matched_moving
        else 0.0
    )

    highway = []

    for segment_index in result["segment_index"]:
        if segment_index is None:
            highway.append("")
        else:
            highway.append(network.segments[segment_index].highway)

    points_path = Path(run_folder) / "v2_map_points.csv"

    write_points_csv(
        points_path,
        {
            "time_seconds": no_map["elapsed"],
            "speed_mph": [row.get("speed_mph") for row in data],
            "relative_heading_deg": no_map["heading"],
            "map_assisted_x_m": result["x"],
            "map_assisted_y_m": result["y"],
            "matched_to_road": [int(value) for value in result["matched"]],
            "matched_highway_class": highway,
            "road_snap_distance_m": result["snap_distance"],
            "map_local_cost": result["local_cost"],
            "gps_ground_truth_x_m": gps_x,
            "gps_ground_truth_y_m": gps_y,
            "position_error_m": per_row_error,
        },
    )

    return {
        "metrics": metrics,
        "initial_bearing_deg": round(initial_bearing, 3),
        "matched_percent": matched_percent,
        "median_snap_distance_m": round(median(snap_distances), 3) if snap_distances else "",
        "points_path": points_path,
    }
