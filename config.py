"""Configuration for Rubik's Cube CV pipeline."""
import json
import cv2
from pathlib import Path

# Camera configuration
CAMERA_URL = "http://192.168.1.237:8081/video"
CAMERA_DISTANCE_MM = 150
CAMERA_PITCH_DEG = 53.5    # Downward tilt
CAMERA_ROLL_DEG = -21.5    # Rightward tilt
CAMERA_ROTATION = cv2.ROTATE_90_CLOCKWISE

# Cube dimensions
CUBE_SIZE_MM = 57  # Standard 3x3

# Paths
OUTPUT_DIR = Path(__file__).parent / "output"
CALIBRATION_PATH = OUTPUT_DIR / "calibration.json"
DEFAULTS_DIR = Path(__file__).parent / "defaults"
DEFAULT_CALIBRATION_PATH = DEFAULTS_DIR / "calibration.json"


def load_face_polygons() -> dict[str, list[tuple[int, int]]] | None:
    """Load face polygon ROIs from calibration.json.

    Tries output/calibration.json first (user session), then falls back
    to defaults/calibration.json (application defaults).

    Returns:
        Dict mapping face name (U, F, R) to list of 4 corner points,
        or None if no calibration file exists.
    """
    # Try output calibration first (user's current session)
    if CALIBRATION_PATH.exists():
        path = CALIBRATION_PATH
    # Fallback to defaults (checked into repo)
    elif DEFAULT_CALIBRATION_PATH.exists():
        path = DEFAULT_CALIBRATION_PATH
    else:
        return None

    with open(path) as f:
        data = json.load(f)

    face_polygons = data.get('face_polygons')
    if not face_polygons:
        return None

    # Convert lists to tuples for consistency
    return {
        face: [tuple(pt) for pt in points]
        for face, points in face_polygons.items()
    }


# Load face polygons from calibration (or None if not calibrated)
FACE_POLYGONS = load_face_polygons()

# HSV color ranges for detection
# Format: {'h': (min, max), 's': (min, max), 'v': (min, max)}
# Note: red wraps around 0/180, so it has two hue ranges
# Tuned for stickerless cube under warm indoor lighting - 2026-01-17
COLOR_RANGES = {
    'white':  {'h': (0, 180), 's': (0, 80), 'v': (180, 255)},    # High value, low-medium sat
    'yellow': {'h': (18, 40), 's': (80, 255), 'v': (150, 255)},  # Warm yellow
    'orange': {'h': (5, 20), 's': (150, 255), 'v': (150, 255)},  # Orange-red
    'red':    {'h': [(0, 10), (170, 180)], 's': (120, 255), 'v': (80, 255)},  # Saturated red
    'green':  {'h': (45, 85), 's': (80, 255), 'v': (80, 255)},   # Green range
    'blue':   {'h': (90, 130), 's': (80, 255), 'v': (80, 255)},  # Blue range
}

# Color name to single letter mapping (for state representation)
COLOR_LETTERS = {
    'white': 'W',
    'yellow': 'Y',
    'orange': 'O',
    'red': 'R',
    'green': 'G',
    'blue': 'B',
    'unknown': '?',
}
