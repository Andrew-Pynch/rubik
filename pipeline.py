#!/usr/bin/env python3
"""CV processing pipeline for Rubik's cube detection."""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from config import (
    CAMERA_ROTATION,
    CAMERA_URL,
    COLOR_LETTERS,
    COLOR_RANGES,
    FACE_POLYGONS,
    OUTPUT_DIR,
    load_face_polygons,
)
from cube_model import CubeState


@dataclass
class DetectedSticker:
    """A detected sticker with its properties."""
    contour: np.ndarray
    center: tuple[int, int]
    area: float
    color_name: str
    color_letter: str


def capture_frame() -> np.ndarray | None:
    """Capture single frame from IP camera.

    Returns:
        Captured frame or None if capture failed.
    """
    cap = cv2.VideoCapture(CAMERA_URL)
    if not cap.isOpened():
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    return frame


def preprocess(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rotate and filter frame for CV processing.

    Args:
        frame: Raw camera frame.

    Returns:
        Tuple of (rotated BGR frame, HSV frame).
    """
    # Rotate to correct camera orientation
    rotated = cv2.rotate(frame, CAMERA_ROTATION)

    # Apply bilateral filter to reduce noise while preserving edges
    filtered = cv2.bilateralFilter(rotated, d=9, sigmaColor=75, sigmaSpace=75)

    # Convert to HSV for color detection
    hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)

    return rotated, hsv


def create_polygon_mask(
    frame_shape: tuple[int, int, int],
    polygon: list[tuple[int, int]],
) -> np.ndarray:
    """Create a binary mask for a polygon region.

    Args:
        frame_shape: Shape of the frame (h, w, c).
        polygon: List of (x, y) corner points.

    Returns:
        Binary mask (255 inside polygon, 0 outside).
    """
    mask = np.zeros(frame_shape[:2], dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def get_polygon_bounding_box(polygon: list[tuple[int, int]]) -> dict[str, int]:
    """Get axis-aligned bounding box for a polygon.

    Args:
        polygon: List of (x, y) corner points.

    Returns:
        Dict with 'x1', 'y1', 'x2', 'y2' bounds.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return {
        'x1': min(xs),
        'y1': min(ys),
        'x2': max(xs),
        'y2': max(ys),
    }


def classify_color(hsv_values: np.ndarray) -> tuple[str, str] | None:
    """Classify HSV values to a cube color.

    Args:
        hsv_values: Array of HSV values (Nx3) to classify.

    Returns:
        Tuple of (color_name, color_letter) or None if no match.
    """
    # Calculate median for robustness
    h = np.median(hsv_values[:, 0])
    s = np.median(hsv_values[:, 1])
    v = np.median(hsv_values[:, 2])

    for color_name, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']

        # Check saturation and value first
        if not (s_range[0] <= s <= s_range[1]):
            continue
        if not (v_range[0] <= v <= v_range[1]):
            continue

        # Check hue (handle red's wraparound)
        if isinstance(h_range, list):
            # Red has two ranges
            h_match = any(r[0] <= h <= r[1] for r in h_range)
        else:
            h_match = h_range[0] <= h <= h_range[1]

        if h_match:
            return color_name, COLOR_LETTERS[color_name]

    return None


def create_color_mask(hsv_frame: np.ndarray, color_name: str) -> np.ndarray:
    """Create a binary mask for a specific color.

    Args:
        hsv_frame: HSV image.
        color_name: Name of color to detect.

    Returns:
        Binary mask where color is present.
    """
    ranges = COLOR_RANGES[color_name]
    h_range = ranges['h']
    s_range = ranges['s']
    v_range = ranges['v']

    if isinstance(h_range, list):
        # Red has two hue ranges (wraps around 0/180)
        mask = np.zeros(hsv_frame.shape[:2], dtype=np.uint8)
        for hr in h_range:
            lower = np.array([hr[0], s_range[0], v_range[0]])
            upper = np.array([hr[1], s_range[1], v_range[1]])
            mask |= cv2.inRange(hsv_frame, lower, upper)
    else:
        lower = np.array([h_range[0], s_range[0], v_range[0]])
        upper = np.array([h_range[1], s_range[1], v_range[1]])
        mask = cv2.inRange(hsv_frame, lower, upper)

    return mask


def detect_stickers_in_polygon(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
) -> list[DetectedSticker]:
    """Detect stickers within a face polygon region.

    Args:
        hsv_frame: HSV frame for color classification.
        polygon: List of (x, y) corner points defining the face region.
        face_name: Name of the face (U, L, R) for debugging.

    Returns:
        List of detected stickers within this polygon.
    """
    detected: list[DetectedSticker] = []

    # Create polygon mask
    poly_mask = create_polygon_mask(hsv_frame.shape, polygon)

    # Calculate polygon area for relative size filtering
    poly_area = cv2.contourArea(np.array(polygon, dtype=np.int32))

    # Morphological kernel for cleaning up masks
    kernel = np.ones((5, 5), np.uint8)

    # Detect each color separately
    for color_name in COLOR_RANGES.keys():
        # Create color mask
        color_mask = create_color_mask(hsv_frame, color_name)

        # Apply polygon mask
        mask = cv2.bitwise_and(color_mask, poly_mask)

        # Clean up mask with morphological operations
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        # Find contours in the mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for contour in contours:
            # Filter by area (relative to polygon, not full frame)
            area = cv2.contourArea(contour)
            min_area = poly_area * 0.01   # At least 1% of face
            max_area = poly_area * 0.20   # At most 20% of face
            if not (min_area < area < max_area):
                continue

            # Filter by aspect ratio (should be roughly square)
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / h if h > 0 else 0
            if not (0.4 < aspect < 2.5):
                continue

            # Get center point
            M = cv2.moments(contour)
            if M['m00'] == 0:
                continue
            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])

            detected.append(DetectedSticker(
                contour=contour,
                center=(cx, cy),
                area=area,
                color_name=color_name,
                color_letter=COLOR_LETTERS[color_name],
            ))

    return detected


def detect_all_faces(
    hsv_frame: np.ndarray,
    face_polygons: dict[str, list[tuple[int, int]]],
) -> dict[str, list[DetectedSticker]]:
    """Detect stickers in all face polygons.

    Args:
        hsv_frame: HSV frame for color classification.
        face_polygons: Dict mapping face name to polygon points.

    Returns:
        Dict mapping face name to list of detected stickers.
    """
    faces: dict[str, list[DetectedSticker]] = {}

    for face_name, polygon in face_polygons.items():
        stickers = detect_stickers_in_polygon(hsv_frame, polygon, face_name)
        if stickers:
            # Take the 9 best stickers (by area consistency)
            if len(stickers) > 9:
                median_area = np.median([s.area for s in stickers])
                stickers = sorted(stickers, key=lambda s: abs(s.area - median_area))[:9]
            faces[face_name] = stickers

    return faces


def group_into_faces(
    stickers: list[DetectedSticker],
    roi: dict[str, int],
) -> dict[str, list[DetectedSticker]]:
    """Group detected stickers into faces based on spatial position.

    Args:
        stickers: List of detected stickers.
        roi: ROI bounds for face position calculation.

    Returns:
        Dict mapping face name (U, L, R) to list of 9 stickers.
    """
    if len(stickers) < 9:
        return {}

    # Use ROI dimensions for face position calculation
    roi_h = roi['y2'] - roi['y1']
    roi_w = roi['x2'] - roi['x1']
    roi_x1, roi_y1 = roi['x1'], roi['y1']

    # Use median area to estimate sticker size
    median_area = np.median([s.area for s in stickers])
    sticker_size = int(np.sqrt(median_area))
    cluster_threshold = sticker_size * 2  # Distance threshold for same face

    # Simple clustering: group stickers that are close together
    faces: dict[str, list[DetectedSticker]] = {}
    used = set()

    # Find clusters of 9 stickers
    for i, sticker in enumerate(stickers):
        if i in used:
            continue

        cluster = [sticker]
        used.add(i)

        for j, other in enumerate(stickers):
            if j in used:
                continue

            # Check if close enough to any sticker in cluster
            for cs in cluster:
                dist = np.sqrt((cs.center[0] - other.center[0])**2 +
                              (cs.center[1] - other.center[1])**2)
                if dist < cluster_threshold * 3:  # Allow for 3x3 grid
                    cluster.append(other)
                    used.add(j)
                    break

            if len(cluster) >= 9:
                break

        if len(cluster) >= 9:
            # Take the 9 with most consistent sizes
            cluster = sorted(cluster, key=lambda s: abs(s.area - median_area))[:9]

            # Determine face name based on position relative to ROI
            avg_y = np.mean([s.center[1] for s in cluster])
            avg_x = np.mean([s.center[0] for s in cluster])

            # Relative position within ROI (0.0 to 1.0)
            rel_y = (avg_y - roi_y1) / roi_h
            rel_x = (avg_x - roi_x1) / roi_w

            # Assign face using FACE_REGIONS config
            face_name = None
            for name, region in FACE_REGIONS.items():
                y_ok = True
                x_ok = True

                if 'y_max' in region and rel_y > region['y_max']:
                    y_ok = False
                if 'y_min' in region and rel_y < region['y_min']:
                    y_ok = False
                if 'x_max' in region and rel_x > region['x_max']:
                    x_ok = False
                if 'x_min' in region and rel_x < region['x_min']:
                    x_ok = False

                if y_ok and x_ok:
                    face_name = name
                    break

            if face_name and face_name not in faces:
                faces[face_name] = cluster

    return faces


def extract_face_colors(
    faces: dict[str, list[DetectedSticker]],
) -> dict[str, list[list[str]]]:
    """Extract 3x3 color grid from each detected face.

    Args:
        faces: Dict of face name to list of 9 stickers.

    Returns:
        Dict mapping face name to 3x3 color letter grid.
    """
    result: dict[str, list[list[str]]] = {}

    for face_name, stickers in faces.items():
        if len(stickers) != 9:
            continue

        # Sort stickers into 3x3 grid by position
        # Sort by y first (rows), then by x (columns)
        sorted_stickers = sorted(stickers, key=lambda s: (s.center[1], s.center[0]))

        # Build 3x3 grid
        grid: list[list[str]] = []
        for row_idx in range(3):
            row_stickers = sorted_stickers[row_idx * 3:(row_idx + 1) * 3]
            # Sort row by x position
            row_stickers = sorted(row_stickers, key=lambda s: s.center[0])
            row = [s.color_letter for s in row_stickers]
            grid.append(row)

        result[face_name] = grid

    return result


def draw_debug_overlay(
    frame: np.ndarray,
    faces: dict[str, list[DetectedSticker]],
    face_polygons: dict[str, list[tuple[int, int]]] | None,
) -> np.ndarray:
    """Draw detected contours and color labels on frame.

    Args:
        frame: BGR frame to annotate.
        faces: Grouped face stickers.
        face_polygons: Face polygon ROIs to draw (or None).

    Returns:
        Annotated frame.
    """
    debug = frame.copy()

    # Face polygon colors
    face_colors = {
        'U': (255, 255, 255),  # White
        'L': (0, 0, 255),      # Red
        'R': (255, 100, 0),    # Blue
    }

    # Draw face polygon ROIs
    if face_polygons:
        for face_name, polygon in face_polygons.items():
            color = face_colors.get(face_name, (255, 255, 0))
            pts = np.array(polygon, dtype=np.int32)
            cv2.polylines(debug, [pts], isClosed=True, color=color, thickness=2)

    # Color map for drawing stickers
    color_bgr = {
        'white': (255, 255, 255),
        'yellow': (0, 255, 255),
        'orange': (0, 165, 255),
        'red': (0, 0, 255),
        'green': (0, 255, 0),
        'blue': (255, 0, 0),
    }

    # Draw all detected stickers and face labels
    total_stickers = 0
    for face_name, face_stickers in faces.items():
        if not face_stickers:
            continue

        total_stickers += len(face_stickers)

        for sticker in face_stickers:
            bgr = color_bgr.get(sticker.color_name, (128, 128, 128))
            cv2.drawContours(debug, [sticker.contour], -1, bgr, 2)
            cv2.putText(
                debug,
                sticker.color_letter,
                (sticker.center[0] - 10, sticker.center[1] + 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                bgr,
                2,
            )

        # Draw face label
        avg_x = int(np.mean([s.center[0] for s in face_stickers]))
        avg_y = int(np.mean([s.center[1] for s in face_stickers]))
        cv2.putText(
            debug,
            f"[{face_name}]",
            (avg_x - 20, avg_y - 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2,
        )

    # Add status text
    cv2.putText(
        debug,
        f"Detected: {total_stickers} stickers, {len(faces)} faces",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )

    # Add calibration warning if no polygons
    if not face_polygons:
        cv2.putText(
            debug,
            "NOT CALIBRATED - Click 'Calibrate' in web UI",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
        )

    return debug


def run_pipeline() -> CubeState | None:
    """Main entry point - captures, processes, saves outputs.

    Returns:
        CubeState if detection successful, None otherwise.
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Capture frame
    print("Capturing frame...")
    frame = capture_frame()
    if frame is None:
        print("ERROR: Failed to capture frame")
        return None

    # Preprocess
    print("Preprocessing...")
    bgr_frame, hsv_frame = preprocess(frame)

    # Save raw frame
    raw_path = OUTPUT_DIR / "raw.jpg"
    cv2.imwrite(str(raw_path), bgr_frame)
    print(f"Saved: {raw_path}")

    # Load face polygons (reload in case calibration changed)
    face_polygons = load_face_polygons()

    if face_polygons:
        print(f"Using calibrated face polygons: {list(face_polygons.keys())}")

        # Detect stickers using polygon ROIs
        print("Detecting stickers in face polygons...")
        faces = detect_all_faces(hsv_frame, face_polygons)

        total_stickers = sum(len(s) for s in faces.values())
        print(f"Found {total_stickers} stickers in {len(faces)} faces")
    else:
        print("WARNING: No calibration found - detection will be limited")
        print("Use the web UI to calibrate face polygons")
        faces = {}

    # Extract colors
    colors = extract_face_colors(faces)

    # Create cube state
    confidence = len(colors) / 3.0  # 3 visible faces expected
    state = CubeState.from_detected(colors, confidence=min(confidence, 1.0))

    # Save debug overlay
    debug_frame = draw_debug_overlay(bgr_frame, faces, face_polygons)
    debug_path = OUTPUT_DIR / "debug.jpg"
    cv2.imwrite(str(debug_path), debug_frame)
    print(f"Saved: {debug_path}")

    # Save state JSON
    state_path = OUTPUT_DIR / "state.json"
    with open(state_path, 'w') as f:
        json.dump(state.to_json(), f, indent=2)
    print(f"Saved: {state_path}")

    print(f"\nResult: {state}")
    return state


if __name__ == "__main__":
    result = run_pipeline()
    if result is None:
        sys.exit(1)
