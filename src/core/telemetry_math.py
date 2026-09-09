"""Math helpers shared across my telemetry analysis stages."""

import math

from src.core.settings import EARTH_RADIUS_M


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else 0.0


def median(values):
    values = sorted(value for value in values if value is not None)

    if not values:
        return 0.0

    middle = len(values) // 2

    if len(values) % 2:
        return values[middle]

    return (values[middle - 1] + values[middle]) / 2.0


def percentile(values, percent):
    values = sorted(value for value in values if value is not None)

    if not values:
        return 0.0

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * percent / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))

    if lower == upper:
        return values[lower]

    fraction = position - lower
    return values[lower] * (1.0 - fraction) + values[upper] * fraction


def rmse(values):
    values = [value for value in values if value is not None]

    if not values:
        return 0.0

    return math.sqrt(sum(value * value for value in values) / len(values))


def mad(values):
    values = [value for value in values if value is not None]

    if not values:
        return 0.0

    centre = median(values)
    return median([abs(value - centre) for value in values])


def angular_delta_deg(current, previous):
    return (current - previous + 180.0) % 360.0 - 180.0


def angular_difference_deg(a, b):
    return abs(angular_delta_deg(a, b))


def undirected_heading_difference_deg(a, b):
    return min(
        angular_difference_deg(a, b),
        angular_difference_deg(a, (b + 180.0) % 360.0),
    )


def haversine_metres(lat1, lon1, lat2, lon2):
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    value = (
        math.sin(dp / 2.0) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    )

    return 2.0 * EARTH_RADIUS_M * math.asin(math.sqrt(value))


def first_valid_gps(data):
    for row in data:
        lat = row.get("latitude")
        lon = row.get("longitude")

        if (
            lat is not None
            and lon is not None
            and -90.0 <= lat <= 90.0
            and -180.0 <= lon <= 180.0
            and not (lat == 0.0 and lon == 0.0)
        ):
            return lat, lon

    return None


def latlon_to_xy(lat, lon, origin):
    lat0, lon0 = origin
    lat0_rad = math.radians(lat0)

    x = (
        EARTH_RADIUS_M
        * math.cos(lat0_rad)
        * math.radians(lon - lon0)
    )

    y = EARTH_RADIUS_M * math.radians(lat - lat0)
    return x, y


def local_xy_from_gps(data, origin=None):
    origin = origin or first_valid_gps(data)

    if origin is None:
        return [None] * len(data), [None] * len(data), None

    xs = []
    ys = []

    for row in data:
        lat = row.get("latitude")
        lon = row.get("longitude")

        if (
            lat is None
            or lon is None
            or not (-90.0 <= lat <= 90.0)
            or not (-180.0 <= lon <= 180.0)
            or (lat == 0.0 and lon == 0.0)
        ):
            xs.append(None)
            ys.append(None)
            continue

        x, y = latlon_to_xy(lat, lon, origin)
        xs.append(x)
        ys.append(y)

    return xs, ys, origin


def gps_track_distance(data):
    distance = 0.0
    previous = None

    for row in data:
        lat = row.get("latitude")
        lon = row.get("longitude")

        if (
            lat is None
            or lon is None
            or not (-90.0 <= lat <= 90.0)
            or not (-180.0 <= lon <= 180.0)
            or (lat == 0.0 and lon == 0.0)
        ):
            continue

        current = (lat, lon)

        if previous is not None:
            segment = haversine_metres(
                previous[0],
                previous[1],
                current[0],
                current[1],
            )

            # I reject impossible GPS jumps rather than allowing one bad fix
            # to dominate my distance ground truth.
            if segment <= 500.0:
                distance += segment

        previous = current

    return distance


def rotate_xy(xs, ys, angle_rad):
    cosine = math.cos(angle_rad)
    sine = math.sin(angle_rad)

    rotated_x = []
    rotated_y = []

    for x, y in zip(xs, ys):
        rotated_x.append(cosine * x - sine * y)
        rotated_y.append(sine * x + cosine * y)

    return rotated_x, rotated_y


def best_rigid_rotation(test_x, test_y, gps_x, gps_y, data, min_speed_mph=2.0):
    """Find one evaluation-only rotation; I never scale the inferred route."""

    dot_sum = 0.0
    cross_sum = 0.0
    used = 0

    for tx, ty, gx, gy, row in zip(test_x, test_y, gps_x, gps_y, data):
        speed = row.get("speed_mph")

        if (
            gx is None
            or gy is None
            or speed is None
            or speed <= min_speed_mph
        ):
            continue

        dot_sum += tx * gx + ty * gy
        cross_sum += tx * gy - ty * gx
        used += 1

    return math.atan2(cross_sum, dot_sum) if used >= 2 else 0.0


def evaluate_position_errors(test_x, test_y, gps_x, gps_y, data, min_speed_mph=2.0):
    values = []
    per_row = []

    for tx, ty, gx, gy, row in zip(test_x, test_y, gps_x, gps_y, data):
        speed = row.get("speed_mph")

        if (
            gx is None
            or gy is None
            or speed is None
            or speed <= min_speed_mph
        ):
            per_row.append(None)
            continue

        error = math.hypot(tx - gx, ty - gy)
        values.append(error)
        per_row.append(error)

    return values, per_row


def metric_summary(values):
    values = [value for value in values if value is not None]

    if not values:
        return {
            "mean": "",
            "median": "",
            "rmse": "",
            "p95": "",
            "final": "",
        }

    return {
        "mean": round(mean(values), 3),
        "median": round(median(values), 3),
        "rmse": round(rmse(values), 3),
        "p95": round(percentile(values, 95), 3),
        "final": round(values[-1], 3),
    }


def integrate_speed_distance(elapsed, speeds_mph):
    cumulative = [0.0] * len(elapsed)

    for index in range(1, len(elapsed)):
        dt = elapsed[index] - elapsed[index - 1]

        if dt <= 0.0 or dt > 10.0:
            cumulative[index] = cumulative[index - 1]
            continue

        previous = max(0.0, speeds_mph[index - 1] or 0.0) * 0.44704
        current = max(0.0, speeds_mph[index] or 0.0) * 0.44704

        cumulative[index] = (
            cumulative[index - 1]
            + (previous + current) * 0.5 * dt
        )

    return cumulative
