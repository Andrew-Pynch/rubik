"""Image preprocessing for Rubik's cube detection."""
from dataclasses import dataclass

import cv2
import numpy as np

from config import CAMERA_ROTATION


@dataclass
class FaceLightingProfile:
    """Lighting analysis for a single face region."""
    face_name: str
    median_v: float           # Median brightness (0-255)
    std_v: float              # Brightness variation
    brightness_level: str     # 'low' | 'normal' | 'high'
    clahe_recommended: bool   # Whether CLAHE should be applied


def analyze_face_lighting(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
    low_threshold: float = 100.0,
    high_threshold: float = 200.0,
) -> FaceLightingProfile:
    """Analyze lighting conditions for a face region.

    Args:
        hsv_frame: HSV image.
        polygon: 4 corner points of face polygon.
        face_name: Name of face (U/F/R).
        low_threshold: V below this = low light.
        high_threshold: V above this = high light.

    Returns:
        FaceLightingProfile with lighting analysis.
    """
    # Create mask for polygon region
    mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)

    # Extract V channel within polygon
    v_values = hsv_frame[:, :, 2][mask > 0]

    median_v = float(np.median(v_values))
    std_v = float(np.std(v_values))

    # Classify brightness level
    if median_v < low_threshold:
        brightness_level = 'low'
        clahe_recommended = True
    elif median_v > high_threshold:
        brightness_level = 'high'
        clahe_recommended = False  # Already bright, don't enhance
    else:
        brightness_level = 'normal'
        clahe_recommended = False

    return FaceLightingProfile(
        face_name=face_name,
        median_v=median_v,
        std_v=std_v,
        brightness_level=brightness_level,
        clahe_recommended=clahe_recommended,
    )


def apply_clahe_to_region(
    bgr_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    clip_limit: float = 2.0,
    tile_grid_size: tuple[int, int] = (4, 4),
) -> np.ndarray:
    """Apply CLAHE to V channel within a face polygon region.

    Args:
        bgr_frame: BGR image (will be modified in place).
        polygon: 4 corner points of face polygon.
        clip_limit: CLAHE contrast limit (1.0-4.0 typical).
        tile_grid_size: Tile size for local histogram.

    Returns:
        BGR image with CLAHE applied to the region.
    """
    result = bgr_frame.copy()
    pts = np.array(polygon)
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)

    # Add small margin
    margin = 5
    x_min = max(0, x_min - margin)
    y_min = max(0, y_min - margin)
    x_max = min(bgr_frame.shape[1], x_max + margin)
    y_max = min(bgr_frame.shape[0], y_max + margin)

    # Extract region, apply CLAHE to V channel
    region = result[y_min:y_max, x_min:x_max]
    hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
    hsv_region[:, :, 2] = clahe.apply(hsv_region[:, :, 2])

    result[y_min:y_max, x_min:x_max] = cv2.cvtColor(hsv_region, cv2.COLOR_HSV2BGR)
    return result


def apply_adaptive_clahe(
    bgr_frame: np.ndarray,
    polygons: dict[str, list[tuple[int, int]]],
    clip_limit: float = 2.0,
    tile_grid_size: tuple[int, int] = (4, 4),
    low_threshold: float = 100.0,
) -> tuple[np.ndarray, dict[str, FaceLightingProfile]]:
    """Apply CLAHE adaptively only to faces that need it.

    Args:
        bgr_frame: BGR image.
        polygons: Dict mapping face name to polygon corners.
        clip_limit: CLAHE contrast limit.
        tile_grid_size: Tile size for local histogram.
        low_threshold: V below this triggers CLAHE.

    Returns:
        Tuple of (processed BGR frame, dict of lighting profiles).
    """
    result = bgr_frame.copy()
    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
    profiles = {}

    for face_name, polygon in polygons.items():
        profile = analyze_face_lighting(hsv, polygon, face_name, low_threshold)
        profiles[face_name] = profile

        if profile.clahe_recommended:
            result = apply_clahe_to_region(result, polygon, clip_limit, tile_grid_size)

    return result, profiles


def rotate_frame(frame: np.ndarray) -> np.ndarray:
    """Rotate frame to correct camera orientation."""
    return cv2.rotate(frame, CAMERA_ROTATION)


def apply_filters(frame: np.ndarray) -> np.ndarray:
    """Apply noise reduction filters while preserving edges."""
    return cv2.bilateralFilter(frame, d=9, sigmaColor=75, sigmaSpace=75)


def to_hsv(frame: np.ndarray) -> np.ndarray:
    """Convert BGR frame to HSV color space."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)


def preprocess(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Full preprocessing pipeline.

    Args:
        frame: Raw camera frame (BGR).

    Returns:
        Tuple of (rotated BGR frame, HSV frame).
    """
    rotated = rotate_frame(frame)
    filtered = apply_filters(rotated)
    hsv = to_hsv(filtered)
    return rotated, hsv
