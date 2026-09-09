"""CSV loading helpers for my OBDLink telemetry files."""

import csv
from datetime import datetime
from pathlib import Path


def find_column(header, prefix):
    prefix = str(prefix).strip().lower()

    for index, value in enumerate(header):
        if str(value).strip().lower().startswith(prefix):
            return index

    return None


def find_columns_containing(header, terms):
    terms = [str(term).lower() for term in terms]

    return [
        index
        for index, value in enumerate(header)
        if any(term in str(value).lower() for term in terms)
    ]


def to_float(value, default=None):
    try:
        value = str(value).strip()
        return default if value == "" else float(value)
    except (TypeError, ValueError):
        return default


def read_obdlink_csv(path):
    path = Path(path)

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        lines = file.readlines()

    header_index = None

    for index, line in enumerate(lines):
        if line.lstrip().lower().startswith("time"):
            header_index = index
            break

    if header_index is None:
        raise ValueError("I could not find the OBDLink CSV header.")

    preamble = lines[:header_index]
    reader = csv.reader(lines[header_index:])

    try:
        header = next(reader)
    except StopIteration as error:
        raise ValueError("The CSV does not contain a header row.") from error

    rows = [row for row in reader if row]
    return preamble, header, rows


def write_obdlink_csv(path, preamble, header, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8", newline="") as file:
        for line in preamble:
            file.write(line)

        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(rows)


def parse_times(header, rows):
    time_index = find_column(header, "time")

    if time_index is None:
        raise ValueError("I could not find a Time column.")

    heading = str(header[time_index]).strip().lower()

    if "sec" in heading:
        values = []

        for row in rows:
            if time_index >= len(row):
                raise ValueError("A row is missing its timestamp value.")
            values.append(float(row[time_index]))

        return values

    # OBDLink normally exports numeric elapsed seconds, but I keep these
    # formats so the same code also works with timestamped exports.
    formats = (
        "%m/%d/%Y %I:%M:%S.%f %p",
        "%m/%d/%Y %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
    )

    result = []

    for row in rows:
        value = row[time_index].strip()
        parsed = None

        for fmt in formats:
            try:
                parsed = datetime.strptime(value, fmt)
                break
            except ValueError:
                pass

        if parsed is None:
            raise ValueError(f"Unsupported timestamp: {value}")

        result.append(parsed.timestamp())

    return result


def elapsed_seconds(header, rows):
    raw = parse_times(header, rows)

    if not raw:
        return []

    start = raw[0]
    return [value - start for value in raw]


def numeric_column(header, rows, prefix, required=True):
    index = find_column(header, prefix)

    if index is None:
        if required:
            raise ValueError(f"I could not find required column: {prefix}")
        return [None] * len(rows)

    return [
        to_float(row[index], None) if index < len(row) else None
        for row in rows
    ]


def normalise_headers(header):
    result = []
    counts = {}

    for value in header:
        name = str(value).strip()
        counts[name] = counts.get(name, 0) + 1

        if counts[name] == 1:
            result.append(name)
        else:
            result.append(f"{name} #{counts[name]}")

    return result


def load_run(path):
    """Load the signals used by my reconstruction and behaviour stages."""

    _preamble, header, rows = read_obdlink_csv(path)
    header = [str(value).strip() for value in header]
    elapsed = elapsed_seconds(header, rows)

    columns = {
        "speed_mph": numeric_column(header, rows, "vehicle speed"),
        "rpm": numeric_column(header, rows, "engine rpm", required=False),
        "throttle_percent": numeric_column(
            header,
            rows,
            "absolute throttle position",
            required=False,
        ),
        "boost_psi": numeric_column(header, rows, "boost", required=False),
        "latitude": numeric_column(header, rows, "latitude", required=False),
        "longitude": numeric_column(header, rows, "longitude", required=False),
        "gps_bearing_deg": numeric_column(header, rows, "bearing", required=False),
        "gps_accuracy_ft": numeric_column(
            header,
            rows,
            "horz accuracy",
            required=False,
        ),
        "rot_x": numeric_column(header, rows, "rotation rate x", required=False),
        "rot_y": numeric_column(header, rows, "rotation rate y", required=False),
        "rot_z": numeric_column(header, rows, "rotation rate z", required=False),
        "grav_x": numeric_column(header, rows, "accel (grav) x", required=False),
        "grav_y": numeric_column(header, rows, "accel (grav) y", required=False),
        "grav_z": numeric_column(header, rows, "accel (grav) z", required=False),
        "mag_x": numeric_column(header, rows, "magnetometer x", required=False),
        "mag_y": numeric_column(header, rows, "magnetometer y", required=False),
        "mag_z": numeric_column(header, rows, "magnetometer z", required=False),
    }

    data = []

    for index in range(len(rows)):
        data.append({name: values[index] for name, values in columns.items()})

    return elapsed, data


def collect_csv_files(folder):
    folder = Path(folder)
    return sorted(path for path in folder.glob("*.csv") if path.is_file())
