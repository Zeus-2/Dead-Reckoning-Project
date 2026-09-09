"""Conservative cleaning and classification for my telemetry dataset."""

import csv
from pathlib import Path

from src.core.paths import CLASSIFICATION_FOLDERS, versioned_output_folder
from src.core.settings import (
    METRES_PER_MILE,
    PRIMARY_MIN_DISTANCE_MILES,
    PRIMARY_MIN_DURATION_MINUTES,
    PRIMARY_MIN_SIGNAL_COVERAGE,
)
from src.core.telemetry_io import (
    collect_csv_files,
    find_column,
    find_columns_containing,
    normalise_headers,
    parse_times,
    read_obdlink_csv,
    write_obdlink_csv,
)
from src.preprocessing.privacy_trim import cumulative_distance_metres


def clean_rows(header, rows):
    expected = len(header)
    cleaned = []
    seen = set()
    removed = 0

    for row in rows:
        if len(row) != expected:
            removed += 1
            continue

        key = tuple(row)

        if key in seen:
            removed += 1
            continue

        seen.add(key)
        cleaned.append(list(row))

    return cleaned, removed


def blank_invalid_gps(header, rows):
    lat_index = find_column(header, "latitude")
    lon_index = find_column(header, "longitude")

    if lat_index is None or lon_index is None:
        return 0

    changed = 0

    for row in rows:
        try:
            lat = float(row[lat_index])
            lon = float(row[lon_index])
        except (ValueError, IndexError):
            continue

        if lat == 0.0 and lon == 0.0:
            row[lat_index] = ""
            row[lon_index] = ""
            changed += 1

    return changed


def column_is_blank_or_zero(rows, index):
    values = []

    for row in rows:
        if index >= len(row):
            continue

        value = row[index].strip()

        if value:
            values.append(value)

    if not values:
        return True

    for value in values:
        try:
            if float(value) != 0.0:
                return False
        except ValueError:
            return False

    return True


def remove_columns(header, rows, indices):
    remove = set(indices)
    keep = [index for index in range(len(header)) if index not in remove]

    return (
        [header[index] for index in keep],
        [[row[index] for index in keep] for row in rows],
    )


def remove_useless_columns(header, rows):
    remove = []

    for index, name in enumerate(header):
        if "current gear" in name.lower() and column_is_blank_or_zero(rows, index):
            remove.append(index)

    if not remove:
        return header, rows, []

    header, rows = remove_columns(header, rows, remove)
    return (
        header,
        rows,
        [f"Removed {len(remove)} blank/zero-only Current Gear column(s)"],
    )


def numeric_coverage(rows, indices):
    if not rows or not indices:
        return 0.0

    valid_rows = 0

    for row in rows:
        valid = False

        for index in indices:
            try:
                value = row[index].strip()

                if value:
                    float(value)
                    valid = True
                    break
            except (ValueError, IndexError):
                pass

        if valid:
            valid_rows += 1

    return valid_rows / len(rows)


def gps_coverage(header, rows):
    lat_index = find_column(header, "latitude")
    lon_index = find_column(header, "longitude")

    if lat_index is None or lon_index is None or not rows:
        return 0.0

    valid = 0

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
            valid += 1

    return valid / len(rows)


def duration_minutes(header, rows):
    if len(rows) < 2:
        return 0.0

    try:
        times = parse_times(header, rows)
        return max(0.0, (times[-1] - times[0]) / 60.0)
    except Exception:
        return 0.0


def travelled_distance_metres(header, rows):
    if len(rows) < 2:
        return 0.0

    try:
        cumulative = cumulative_distance_metres(header, rows)
        return cumulative[-1] if cumulative else 0.0
    except Exception:
        return 0.0


def classify_file(header, rows):
    if not rows:
        return (
            "04_UNUSABLE",
            "UNUSABLE",
            "No usable rows remain after privacy trimming and cleaning.",
        )

    speed_index = find_column(header, "vehicle speed")

    if speed_index is None:
        return (
            "04_UNUSABLE",
            "UNUSABLE",
            "No Vehicle speed column was found.",
        )

    gps_cov = gps_coverage(header, rows)
    imu_indices = find_columns_containing(
        header,
        ["rotation rate", "gyro", "gyroscope"],
    )
    imu_cov = numeric_coverage(rows, imu_indices)
    duration = duration_minutes(header, rows)
    distance_miles = travelled_distance_metres(header, rows) / METRES_PER_MILE

    substantial = (
        duration >= PRIMARY_MIN_DURATION_MINUTES
        and distance_miles >= PRIMARY_MIN_DISTANCE_MILES
    )

    if (
        gps_cov >= PRIMARY_MIN_SIGNAL_COVERAGE
        and imu_cov >= PRIMARY_MIN_SIGNAL_COVERAGE
        and substantial
    ):
        return (
            "01_PRIMARY_DEAD_RECKONING",
            "PRIMARY DEAD RECKONING",
            "Substantial run with vehicle speed, phone rotation data and GPS ground truth.",
        )

    if gps_cov >= PRIMARY_MIN_SIGNAL_COVERAGE and substantial:
        return (
            "02_SUPPLEMENTARY_DISTANCE_ONLY",
            "SUPPLEMENTARY DISTANCE",
            "Substantial speed/GPS run without enough rotation data for primary reconstruction.",
        )

    return (
        "03_PRELIMINARY_METHOD_DEVELOPMENT",
        "PRELIMINARY ONLY",
        "Useful telemetry exists, but the run is too short or lacks sufficient GPS/IMU coverage for my main evaluation.",
    )


def process_file(source, output_root):
    preamble, header, rows = read_obdlink_csv(source)
    original_rows = len(rows)
    actions = []

    header = normalise_headers(header)
    rows, removed = clean_rows(header, rows)

    if removed:
        actions.append(f"Removed {removed} malformed/exact duplicate row(s)")

    zero_gps = blank_invalid_gps(header, rows)

    if zero_gps:
        actions.append(f"Blanked {zero_gps} invalid 0,0 GPS placeholder sample(s)")

    header, rows, column_actions = remove_useless_columns(header, rows)
    actions.extend(column_actions)

    folder_name, status, reason = classify_file(header, rows)
    output_folder = output_root / folder_name
    output_path = output_folder / f"{source.stem}_clean.csv"

    write_obdlink_csv(output_path, preamble, header, rows)

    gps_cov = gps_coverage(header, rows)
    imu_indices = find_columns_containing(
        header,
        ["rotation rate", "gyro", "gyroscope"],
    )
    imu_cov = numeric_coverage(rows, imu_indices)

    return {
        "source_file": source.name,
        "clean_file": str(output_path.relative_to(output_root)),
        "status": status,
        "classification_reason": reason,
        "original_rows": original_rows,
        "clean_rows": len(rows),
        "duration_minutes": round(duration_minutes(header, rows), 3),
        "distance_miles": round(
            travelled_distance_metres(header, rows) / METRES_PER_MILE,
            3,
        ),
        "gps_coverage_percent": round(gps_cov * 100.0, 1),
        "imu_coverage_percent": round(imu_cov * 100.0, 1),
        "cleaning_actions": "; ".join(actions) if actions else "No destructive cleaning required",
    }


def write_manifest(output_root, records):
    path = output_root / "dataset_manifest.csv"

    if records:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)

    return path


def write_readme(output_root):
    text = f"""MY CLEANED VEHICLE TELEMETRY DATASET
====================================

01_PRIMARY_DEAD_RECKONING
I use this for my main route reconstruction and evaluation. My final
primary threshold is at least {PRIMARY_MIN_DURATION_MINUTES:.0f} minutes,
at least {PRIMARY_MIN_DISTANCE_MILES:.0f} miles, and at least
{PRIMARY_MIN_SIGNAL_COVERAGE * 100:.0f}% GPS/IMU coverage.

02_SUPPLEMENTARY_DISTANCE_ONLY
I use this for distance/speed validation where heading data is incomplete.

03_PRELIMINARY_METHOD_DEVELOPMENT
I keep these recordings as evidence of method development, PID/sensor
availability, short tests and practical limitations.

04_UNUSABLE
These files do not contain the minimum vehicle-speed input or no usable
rows remain.

I keep cleaning deliberately conservative:
- I never overwrite the source recordings;
- I remove malformed and exact duplicate rows;
- I blank invalid GPS 0,0 placeholders;
- I remove blank/zero-only Current Gear columns;
- I do not interpolate, resample or invent telemetry values.
"""

    (output_root / "README.txt").write_text(text, encoding="utf-8")


def run(source_folder):
    source_folder = Path(source_folder).expanduser()

    if not source_folder.exists() or not source_folder.is_dir():
        raise ValueError("The source folder does not exist.")

    files = []

    for path in collect_csv_files(source_folder):
        lower = path.name.lower()

        if lower in {"privacy_manifest.csv", "dataset_manifest.csv"}:
            continue

        if "_clean.csv" in lower:
            continue

        files.append(path)

    if not files:
        raise ValueError("I could not find source CSV files to clean.")

    output_root = versioned_output_folder(source_folder, "cleaned_dataset")

    for folder_name in CLASSIFICATION_FOLDERS:
        (output_root / folder_name).mkdir(parents=True, exist_ok=True)

    records = []

    for source in files:
        records.append(process_file(source, output_root))

    write_manifest(output_root, records)
    write_readme(output_root)
    return output_root, records


def main(default_source=None):
    print()
    print("Clean and Classify My Dataset")
    print("=" * 42)

    if default_source is not None:
        print("My default source is the latest privacy-trimmed folder:")
        print(f"  {default_source}")
        print("Press Enter to use it, or type another folder.")

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

    print(f"\nI classified {len(records)} recording(s):")

    for record in records:
        print(f"[{record['status']}] {record['source_file']}")

    print("\nMy cleaned dataset is ready:")
    print(f"  {output_root}")
    return output_root


if __name__ == "__main__":
    main()
