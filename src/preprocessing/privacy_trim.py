"""Privacy trimming for my OBDLink telemetry recordings."""

import csv
import json
from pathlib import Path

from src.core.paths import versioned_output_folder
from src.core.settings import METRES_PER_MILE, PRIVACY_CONFIG_FILE
from src.core.telemetry_io import (
    collect_csv_files,
    find_column,
    parse_times,
    read_obdlink_csv,
    write_obdlink_csv,
)
from src.core.telemetry_math import haversine_metres


def load_config(config_path=PRIVACY_CONFIG_FILE):
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Missing configuration file: {config_path.name}")

    config = json.loads(config_path.read_text(encoding="utf-8"))

    if not isinstance(config.get("locations"), list):
        raise ValueError("privacy_locations.json must contain a locations list.")

    return config


def config_uses_examples(config):
    locations = config.get("locations", [])

    if not locations:
        return True

    return all(
        str(location.get("name", "")).strip().lower().startswith("example ")
        for location in locations
    )


def first_last_valid_gps(header, rows):
    lat_index = find_column(header, "latitude")
    lon_index = find_column(header, "longitude")

    if lat_index is None or lon_index is None:
        return None, None

    valid = []

    for row in rows:
        try:
            lat = float(row[lat_index])
            lon = float(row[lon_index])
        except (ValueError, IndexError):
            continue

        if (
            -90.0 <= lat <= 90.0
            and -180.0 <= lon <= 180.0
            and not (lat == 0.0 and lon == 0.0)
        ):
            valid.append((lat, lon))

    if not valid:
        return None, None

    return valid[0], valid[-1]


def cumulative_distance_metres(header, rows):
    speed_index = find_column(header, "vehicle speed")

    if speed_index is None:
        raise ValueError("I could not find a Vehicle speed column.")

    times = parse_times(header, rows)
    speed_header = header[speed_index].lower()
    speed_factor = 1000.0 / 3600.0 if "km" in speed_header else 0.44704

    speeds = []

    for row in rows:
        try:
            speed = max(0.0, float(row[speed_index]))
        except (ValueError, IndexError):
            speed = 0.0

        speeds.append(speed * speed_factor)

    cumulative = [0.0] * len(rows)

    for index in range(1, len(rows)):
        dt = times[index] - times[index - 1]

        if dt <= 0.0 or dt > 10.0:
            dt = 0.0

        cumulative[index] = (
            cumulative[index - 1]
            + (speeds[index - 1] + speeds[index]) * 0.5 * dt
        )

    return cumulative


def nearby_location(point, locations, radius_metres, end_name):
    if point is None:
        return None

    lat, lon = point

    for location in locations:
        enabled = bool(location.get(end_name, True))

        if not enabled:
            continue

        distance = haversine_metres(
            lat,
            lon,
            float(location["latitude"]),
            float(location["longitude"]),
        )

        if distance <= radius_metres:
            return location

    return None


def trim_rows(header, rows, trim_start, trim_end, trim_metres):
    if not rows or (not trim_start and not trim_end):
        return rows, 0, 0

    cumulative = cumulative_distance_metres(header, rows)
    total_distance = cumulative[-1] if cumulative else 0.0

    start_index = 0
    end_index = len(rows)

    if trim_start:
        start_index = len(rows)

        for index, distance in enumerate(cumulative):
            if distance >= trim_metres:
                start_index = index
                break

    if trim_end:
        target = total_distance - trim_metres

        if target <= 0.0:
            end_index = 0
        else:
            for index, distance in enumerate(cumulative):
                if distance > target:
                    end_index = index
                    break

    if start_index >= end_index:
        return [], start_index, len(rows) - end_index

    return (
        rows[start_index:end_index],
        start_index,
        len(rows) - end_index,
    )


def process_file(source, output_folder, config):
    preamble, header, rows = read_obdlink_csv(source)
    first_gps, last_gps = first_last_valid_gps(header, rows)

    radius_metres = float(config.get("near_radius_miles", 1.0)) * METRES_PER_MILE
    trim_metres = float(config.get("trim_distance_miles", 1.0)) * METRES_PER_MILE

    start_match = nearby_location(
        first_gps,
        config["locations"],
        radius_metres,
        "trim_start",
    )

    end_match = nearby_location(
        last_gps,
        config["locations"],
        radius_metres,
        "trim_end",
    )

    trimmed_rows, removed_start, removed_end = trim_rows(
        header,
        rows,
        start_match is not None,
        end_match is not None,
        trim_metres,
    )

    output_path = output_folder / f"{source.stem}_privacy_trimmed.csv"
    write_obdlink_csv(output_path, preamble, header, trimmed_rows)

    actions = []

    if start_match is not None:
        actions.append(f"trimmed first {config.get('trim_distance_miles', 1.0)} mile(s)")

    if end_match is not None:
        actions.append(f"trimmed last {config.get('trim_distance_miles', 1.0)} mile(s)")

    if not actions:
        actions.append("copied unchanged")

    return {
        "source_file": source.name,
        "output_file": output_path.name,
        "source_rows": len(rows),
        "output_rows": len(trimmed_rows),
        "start_trim_applied": start_match is not None,
        "end_trim_applied": end_match is not None,
        "rows_removed_from_start": removed_start,
        "rows_removed_from_end": removed_end,
        "action": "; ".join(actions),
    }


def write_manifest(output_folder, records):
    path = output_folder / "privacy_manifest.csv"

    if not records:
        return path

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)

    return path


def run(source, config_path=PRIVACY_CONFIG_FILE):
    source = Path(source).expanduser()
    config = load_config(config_path)

    if config_uses_examples(config):
        raise ValueError(
            "privacy_locations.json still contains example coordinates. "
            "I replace them locally before processing real recordings."
        )

    if source.is_file() and source.suffix.lower() == ".csv":
        files = [source]
        parent = source.parent
    elif source.is_dir():
        files = [
            path
            for path in collect_csv_files(source)
            if "_privacy_trimmed" not in path.stem.lower()
            and "_clean" not in path.stem.lower()
            and path.name.lower() not in {"privacy_manifest.csv", "dataset_manifest.csv"}
        ]
        parent = source
    else:
        raise ValueError("I need a CSV file or a folder containing CSV files.")

    if not files:
        raise ValueError("I could not find any source CSV files to privacy-trim.")

    output_folder = versioned_output_folder(parent, "privacy_trimmed")
    records = []

    for file_path in files:
        records.append(process_file(file_path, output_folder, config))

    write_manifest(output_folder, records)
    return output_folder, records


def main(default_source=None):
    print()
    print("Privacy Trim")
    print("=" * 42)
    print("I use my local privacy_locations.json and never overwrite the raw logs.")

    if default_source:
        print(f"Default source: {default_source}")

    raw = input("CSV file/folder: ").strip().strip('"')

    if not raw and default_source:
        raw = str(default_source)

    if not raw:
        print("Cancelled.")
        return None

    try:
        output_folder, records = run(raw)
    except Exception as error:
        print(f"[ERROR] {error}")
        return None

    print(f"\nProcessed {len(records)} recording(s).")

    for record in records:
        print(f"[{record['action'].upper()}] {record['source_file']}")

    print("\nMy privacy-trimmed dataset is ready:")
    print(f"  {output_folder}")
    return output_folder


if __name__ == "__main__":
    main()
