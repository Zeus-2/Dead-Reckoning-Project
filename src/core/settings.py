"""Central settings for my vehicle-telemetry dissertation toolkit."""

from pathlib import Path

TOOLKIT_VERSION = "1.1-final"

# All repository resources are resolved relative to this project root.
# I can therefore move/clone the repository without editing absolute paths.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FOLDER = PROJECT_ROOT / "config"
DATA_FOLDER = PROJECT_ROOT / "data"
RAW_DATA_FOLDER = DATA_FOLDER / "raw"
PROCESSED_DATA_FOLDER = DATA_FOLDER / "processed"
MAP_FOLDER = DATA_FOLDER / "maps"
STATE_FOLDER = PROJECT_ROOT / ".state"

STATE_FILE = STATE_FOLDER / "tool_state.json"
PRIVACY_CONFIG_FILE = CONFIG_FOLDER / "privacy_locations.json"
MAP_PBF_FILE = MAP_FOLDER / "study_area_roads.osm.pbf"

METRES_PER_MILE = 1609.344
EARTH_RADIUS_M = 6_371_000.0

# I keep my final primary dataset focused on substantial journeys.
PRIMARY_MIN_DURATION_MINUTES = 10.0
PRIMARY_MIN_DISTANCE_MILES = 3.0
PRIMARY_MIN_SIGNAL_COVERAGE = 0.80

# Shared dead-reckoning settings.
STATIONARY_SPEED_MPH = 0.5
MAX_YAW_RATE_DEG_S = 90.0
YAW_SIGN = -1.0

# V1 baseline settings.
V1_GYRO_DEADBAND_DEG_S = 0.15

# V2 inertial settings.
V2_MIN_STATIONARY_WINDOW_SECONDS = 1.5
V2_MAX_STATIONARY_WINDOW_MAD_DEG_S = 1.5
V2_MIN_DEADBAND_DEG_S = 0.10
V2_MAX_DEADBAND_DEG_S = 1.20
V2_SMOOTHING_ALPHA = 0.35

# I only use the magnetometer as a weak heading-change reference.
V2_MAG_MIN_SPEED_MPH = 3.0
V2_MAG_REFERENCE_SPEED_MPH = 5.0
V2_MAG_MIN_HORIZONTAL_FIELD_UT = 5.0
V2_MAG_FIELD_MAD_MULTIPLIER = 4.0
V2_MAG_MAX_RATE_DEG_S = 80.0
V2_MAG_MAX_RATE_DISAGREEMENT_DEG_S = 18.0
V2_MAG_BLEND_PER_SECOND = 0.06
V2_MAG_MAX_SAMPLE_BLEND = 0.10
V2_MAG_MIN_VALID_INTERVALS = 20

# OSM map-matching settings.
ROAD_CELL_M = 250.0
MAP_SEARCH_RADIUS_M = 80.0
MAP_INITIAL_SEARCH_RADIUS_M = 120.0
MAP_INITIAL_SCORE_SAMPLE_STEP = 3
MAP_INITIAL_SCORE_MAX_POINTS = 45
MAP_HEADING_COST_M_PER_DEG = 0.70
MAP_CORRIDOR_MARGIN_M = 3000.0
MAP_SAME_SEGMENT_PENALTY_M = 0.0
MAP_SAME_WAY_PENALTY_M = 2.0
MAP_CONNECTED_SEGMENT_PENALTY_M = 8.0
MAP_DISCONNECTED_SEGMENT_PENALTY_M = 95.0
MAP_SEGMENT_SWITCH_PENALTY_M = 4.0
MAP_UNMATCHED_PENALTY_M = 18.0
MAP_MAX_LOCAL_COST_M = 135.0
MAP_BEAM_WIDTH = 6
MAP_CANDIDATES_PER_STATE = 16

DRIVABLE_HIGHWAYS = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified", "residential",
    "living_street", "service", "road",
}
