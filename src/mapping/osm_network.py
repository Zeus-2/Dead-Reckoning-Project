"""OpenStreetMap road-network loading and spatial indexing for my V2 map stage."""

import math
from pathlib import Path

from src.core.settings import (
    DRIVABLE_HIGHWAYS,
    MAP_CONNECTED_SEGMENT_PENALTY_M,
    MAP_CORRIDOR_MARGIN_M,
    MAP_DISCONNECTED_SEGMENT_PENALTY_M,
    MAP_HEADING_COST_M_PER_DEG,
    MAP_SAME_SEGMENT_PENALTY_M,
    MAP_SAME_WAY_PENALTY_M,
    ROAD_CELL_M,
)
from src.core.telemetry_math import first_valid_gps, latlon_to_xy, undirected_heading_difference_deg


class RoadSegment:
    __slots__ = (
        "x1", "y1", "x2", "y2",
        "way_id", "highway", "heading",
        "node1", "node2",
    )

    def __init__(self, x1, y1, x2, y2, way_id, highway, node1, node2):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2
        self.way_id = way_id
        self.highway = highway
        self.node1 = node1
        self.node2 = node2
        self.heading = math.degrees(math.atan2(x2 - x1, y2 - y1)) % 360.0


class RoadNetwork:
    def __init__(self, origin, cell_size=ROAD_CELL_M):
        self.origin = origin
        self.cell_size = cell_size
        self.segments = []
        self.grid = {}

    def _cell(self, x, y):
        return (
            math.floor(x / self.cell_size),
            math.floor(y / self.cell_size),
        )

    def add(self, segment):
        index = len(self.segments)
        self.segments.append(segment)

        min_cx, min_cy = self._cell(min(segment.x1, segment.x2), min(segment.y1, segment.y2))
        max_cx, max_cy = self._cell(max(segment.x1, segment.x2), max(segment.y1, segment.y2))

        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                self.grid.setdefault((cx, cy), []).append(index)

    def nearby_indices(self, x, y, radius):
        min_cx, min_cy = self._cell(x - radius, y - radius)
        max_cx, max_cy = self._cell(x + radius, y + radius)
        found = set()

        for cx in range(min_cx, max_cx + 1):
            for cy in range(min_cy, max_cy + 1):
                found.update(self.grid.get((cx, cy), []))

        return found

    def connected(self, first_index, second_index):
        if first_index is None or second_index is None:
            return False

        if first_index == second_index:
            return True

        first = self.segments[first_index]
        second = self.segments[second_index]
        first_nodes = {first.node1, first.node2}
        second_nodes = {second.node1, second.node2}
        return bool(first_nodes & second_nodes)

    def continuity_penalty(self, previous_index, candidate_index):
        if previous_index is None:
            return 0.0

        if previous_index == candidate_index:
            return MAP_SAME_SEGMENT_PENALTY_M

        previous = self.segments[previous_index]
        candidate = self.segments[candidate_index]

        if previous.way_id == candidate.way_id:
            return MAP_SAME_WAY_PENALTY_M

        if self.connected(previous_index, candidate_index):
            return MAP_CONNECTED_SEGMENT_PENALTY_M

        return MAP_DISCONNECTED_SEGMENT_PENALTY_M


def project_point_to_segment(px, py, segment):
    dx = segment.x2 - segment.x1
    dy = segment.y2 - segment.y1
    length_sq = dx * dx + dy * dy

    if length_sq <= 1e-12:
        return segment.x1, segment.y1, math.hypot(px - segment.x1, py - segment.y1)

    t = ((px - segment.x1) * dx + (py - segment.y1) * dy) / length_sq
    t = max(0.0, min(1.0, t))
    sx = segment.x1 + t * dx
    sy = segment.y1 + t * dy
    return sx, sy, math.hypot(px - sx, py - sy)


def road_speed_penalty(segment, speed_mph):
    if speed_mph >= 45.0:
        if segment.highway in {"service", "living_street"}:
            return 35.0
        if segment.highway == "residential":
            return 18.0

    if speed_mph >= 35.0 and segment.highway in {"service", "living_street"}:
        return 20.0

    return 0.0


def road_candidates(network, x, y, radius, heading=None, limit=16):
    candidates = []

    for segment_index in network.nearby_indices(x, y, radius):
        segment = network.segments[segment_index]
        sx, sy, distance = project_point_to_segment(x, y, segment)

        if distance > radius:
            continue

        heading_difference = (
            undirected_heading_difference_deg(heading, segment.heading)
            if heading is not None
            else 0.0
        )

        candidates.append(
            (distance, heading_difference, sx, sy, segment_index)
        )

    candidates.sort(key=lambda item: item[0] + MAP_HEADING_COST_M_PER_DEG * item[1])
    return candidates[:limit]


def route_bbox_for_anchor(lat, lon, radius_m):
    lat_span = radius_m / 111_320.0
    lon_scale = max(math.cos(math.radians(lat)), 0.2)
    lon_span = radius_m / (111_320.0 * lon_scale)
    return (lat - lat_span, lon - lon_span, lat + lat_span, lon + lon_span)


def in_any_bbox(lat, lon, bboxes):
    return any(
        min_lat <= lat <= max_lat and min_lon <= lon <= max_lon
        for min_lat, min_lon, max_lat, max_lon in bboxes
    )


def build_network_for_runs(pbf_path, run_results):
    try:
        import osmium
    except ImportError as error:
        raise RuntimeError(
            "I need the osmium package for .osm.pbf map assistance. "
            "On Windows I install it with: py -m pip install osmium"
        ) from error

    starts = []

    for result in run_results:
        start = first_valid_gps(result["data"])

        if start is not None:
            starts.append((start, result["distance"][-1] if result["distance"] else 0.0))

    if not starts:
        raise ValueError("I do not have a valid post-privacy GPS start anchor for map matching.")

    map_origin = starts[0][0]
    bboxes = [
        route_bbox_for_anchor(lat, lon, max(distance + MAP_CORRIDOR_MARGIN_M, 4000.0))
        for (lat, lon), distance in starts
    ]
    network = RoadNetwork(map_origin)

    class Handler(osmium.SimpleHandler):
        def way(self, way):
            highway = way.tags.get("highway")

            if highway not in DRIVABLE_HIGHWAYS:
                return

            nodes = []

            for node in way.nodes:
                try:
                    if not node.location.valid():
                        continue
                    lat = node.location.lat
                    lon = node.location.lon
                except Exception:
                    continue

                nodes.append((int(node.ref), lat, lon))

            for first, second in zip(nodes, nodes[1:]):
                node1, lat1, lon1 = first
                node2, lat2, lon2 = second

                if not (
                    in_any_bbox(lat1, lon1, bboxes)
                    or in_any_bbox(lat2, lon2, bboxes)
                ):
                    continue

                x1, y1 = latlon_to_xy(lat1, lon1, map_origin)
                x2, y2 = latlon_to_xy(lat2, lon2, map_origin)

                if math.hypot(x2 - x1, y2 - y1) < 0.5:
                    continue

                network.add(
                    RoadSegment(
                        x1,
                        y1,
                        x2,
                        y2,
                        int(way.id),
                        highway,
                        node1,
                        node2,
                    )
                )

    handler = Handler()
    handler.apply_file(str(Path(pbf_path)), locations=True)

    if not network.segments:
        raise ValueError("I did not find drivable OSM road segments around my route starts.")

    return network, map_origin

