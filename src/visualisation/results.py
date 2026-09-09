"""Generate dissertation-ready SVG comparisons from my completed analysis outputs."""

import csv
from pathlib import Path

from src.core.paths import (
    find_run_folder,
    newest_folder,
    normalise_run_name,
    resolve_cleaned_dataset,
    short_run_label,
    versioned_output_folder,
)
from src.visualisation.svg_charts import write_grouped_bar, write_line_chart, write_route_overlay


def to_float(value):
    try:
        value = str(value).strip()
        return None if value == "" else float(value)
    except (TypeError, ValueError):
        return None


def read_rows(path):
    if path is None or not Path(path).exists():
        return []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def latest_result(cleaned_root, prefix, summary_name):
    folder = newest_folder(cleaned_root, (prefix,))

    if folder is None:
        return None, None

    summary = folder / summary_name
    return (folder, summary) if summary.exists() else (None, None)


def read_xy(path, x_key, y_key):
    rows = read_rows(path)
    result = []

    for row in rows:
        x = to_float(row.get(x_key))
        y = to_float(row.get(y_key))
        result.append((x, y) if x is not None and y is not None else (None, None))

    return result or None


def read_error_distance(path, distance_key="cumulative_obd_distance_m"):
    rows = read_rows(path)
    values = []

    for row in rows:
        distance = to_float(row.get(distance_key))
        error = to_float(row.get("position_error_m"))

        if distance is not None and error is not None:
            values.append((distance, error))

    return values or None


def translate(points, offset):
    if not points or offset is None:
        return points

    ox, oy = offset
    return [
        (x + ox, y + oy) if x is not None and y is not None else (None, None)
        for x, y in points
    ]


def first_valid(points):
    if not points:
        return None

    for point in points:
        if point[0] is not None and point[1] is not None:
            return point

    return None


def build_summary_records(v1_rows, v2_rows):
    v1 = {normalise_run_name(row.get("source_file", "")): row for row in v1_rows}
    v2 = {normalise_run_name(row.get("source_file", "")): row for row in v2_rows}
    keys = sorted(set(v1) | set(v2))
    records = []

    for key in keys:
        a = v1.get(key, {})
        b = v2.get(key, {})
        source = b.get("source_file") or a.get("source_file") or key

        records.append({
            "run": source,
            "v1_rmse_m": to_float(a.get("rmse_position_error_m", b.get("v1_rmse_position_error_m"))),
            "v2_rmse_m": to_float(b.get("v2_no_map_rmse_position_error_m")),
            "v2_map_rmse_m": to_float(b.get("v2_map_rmse_position_error_m")),
            "v1_final_error_m": to_float(a.get("final_position_error_m")),
            "v2_final_error_m": to_float(b.get("v2_no_map_final_error_m")),
            "v2_map_final_error_m": to_float(b.get("v2_map_final_error_m")),
        })

    return records


def write_comparison_csv(path, records):
    if not records:
        return

    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)


def generate_run_figures(output, record, v1_folder, v2_folder):
    run_name = record["run"]
    label = short_run_label(run_name)
    run_output = output / label
    run_output.mkdir(parents=True, exist_ok=True)
    v1_run = find_run_folder(v1_folder, run_name)
    v2_run = find_run_folder(v2_folder, run_name)

    v1_points = v1_run / "v1_points.csv" if v1_run else None
    v2_points = v2_run / "v2_no_map_points.csv" if v2_run else None
    map_points = v2_run / "v2_map_points.csv" if v2_run else None

    v1_route = read_xy(v1_points, "evaluation_aligned_x_m", "evaluation_aligned_y_m") if v1_points else None
    v2_route = read_xy(v2_points, "evaluation_aligned_x_m", "evaluation_aligned_y_m") if v2_points else None
    gps_local = read_xy(v2_points or v1_points, "gps_ground_truth_x_m", "gps_ground_truth_y_m") if (v2_points or v1_points) else None
    map_route = read_xy(map_points, "map_assisted_x_m", "map_assisted_y_m") if map_points and map_points.exists() else None
    map_gps = read_xy(map_points, "gps_ground_truth_x_m", "gps_ground_truth_y_m") if map_points and map_points.exists() else None

    if map_route and map_gps:
        offset = first_valid(map_gps)
        gps_plot = map_gps
        v1_plot = translate(v1_route, offset)
        v2_plot = translate(v2_route, offset)
    else:
        gps_plot = gps_local
        v1_plot = v1_route
        v2_plot = v2_route

    write_route_overlay(
        run_output / "route_progression.svg",
        f"Route reconstruction progression - {label}",
        [
            ("GPS ground truth", gps_plot),
            ("V1 baseline", v1_plot),
            ("V2 no-map", v2_plot),
            ("V2 + OSM", map_route),
        ],
    )

    error_series = []

    if v1_points and v1_points.exists():
        error_series.append(("V1 baseline", read_error_distance(v1_points)))

    if v2_points and v2_points.exists():
        v2_error = read_error_distance(v2_points)
        error_series.append(("V2 no-map", v2_error))

        if map_points and map_points.exists():
            map_rows = read_rows(map_points)
            v2_rows = read_rows(v2_points)
            map_error = []

            for map_row, v2_row in zip(map_rows, v2_rows):
                distance = to_float(v2_row.get("cumulative_obd_distance_m"))
                error = to_float(map_row.get("position_error_m"))

                if distance is not None and error is not None:
                    map_error.append((distance, error))

            error_series.append(("V2 + OSM", map_error))

    write_line_chart(
        run_output / "error_over_distance.svg",
        f"Position error growth - {label}",
        error_series,
        "Cumulative distance (km)",
        "Position error (m)",
    )


def write_dataset_overview(output, cleaned_root):
    manifest = cleaned_root / "dataset_manifest.csv"
    rows = read_rows(manifest)

    if not rows:
        return

    primary = [row for row in rows if row.get("status") == "PRIMARY DEAD RECKONING"]

    if not primary:
        return

    categories = [short_run_label(row["source_file"]) for row in primary]
    write_grouped_bar(
        output / "primary_dataset_duration.svg",
        "Primary dataset duration by run",
        categories,
        [("V1 baseline", [to_float(row.get("duration_minutes")) for row in primary])],
        "Duration (minutes)",
    )


def run(cleaned_source):
    cleaned_root = resolve_cleaned_dataset(cleaned_source)
    v1_folder, v1_summary = latest_result(
        cleaned_root,
        "dead_reckoning_v1",
        "dead_reckoning_v1_summary.csv",
    )
    v2_folder, v2_summary = latest_result(
        cleaned_root,
        "dead_reckoning_v2",
        "dead_reckoning_v2_summary.csv",
    )

    if v1_summary is None and v2_summary is None:
        raise ValueError("I need V1 or V2 result summaries before I can visualise them.")

    records = build_summary_records(read_rows(v1_summary), read_rows(v2_summary))
    output = versioned_output_folder(cleaned_root, "comparison_visuals")
    write_comparison_csv(output / "dead_reckoning_comparison.csv", records)
    categories = [short_run_label(record["run"]) for record in records]

    write_grouped_bar(
        output / "rmse_comparison.svg",
        "Dead-reckoning RMSE by run",
        categories,
        [
            ("V1 baseline", [record["v1_rmse_m"] for record in records]),
            ("V2 no-map", [record["v2_rmse_m"] for record in records]),
            ("V2 + OSM", [record["v2_map_rmse_m"] for record in records]),
        ],
        "RMSE (m)",
    )

    write_grouped_bar(
        output / "final_error_comparison.svg",
        "Final position error by run",
        categories,
        [
            ("V1 baseline", [record["v1_final_error_m"] for record in records]),
            ("V2 no-map", [record["v2_final_error_m"] for record in records]),
            ("V2 + OSM", [record["v2_map_final_error_m"] for record in records]),
        ],
        "Final error (m)",
    )

    write_dataset_overview(output, cleaned_root)

    for record in records:
        generate_run_figures(output, record, v1_folder, v2_folder)

    (output / "README.txt").write_text(
        """MY DEAD-RECKONING COMPARISON FIGURES
=====================================

rmse_comparison.svg
    My main numerical comparison across V1, V2 no-map and V2 + OSM.

final_error_comparison.svg
    My final-position drift comparison.

primary_dataset_duration.svg
    Duration of each primary recording.

<run>/route_progression.svg
    GPS ground truth overlaid with each available reconstruction version.

<run>/error_over_distance.svg
    Shows how positional error grows along each journey.

All geographic plots use local X/Y metres rather than raw latitude/longitude.
""",
        encoding="utf-8",
    )

    return output, records


def main(default_source=None):
    print()
    print("Visualise and Compare My Results")
    print("=" * 42)

    if default_source is not None:
        print("My default cleaned dataset is:")
        print(f"  {default_source}")
        print("Press Enter to use it, or type another cleaned dataset.")

    raw = input("Cleaned dataset: ").strip().strip('"')

    if not raw and default_source is not None:
        raw = str(default_source)

    if not raw:
        print("Cancelled.")
        return None

    try:
        output, _records = run(raw)
    except Exception as error:
        print(f"[ERROR] {error}")
        return None

    print("\nMy comparison figures are ready:")
    print(f"  {output}")
    return output


if __name__ == "__main__":
    main()
