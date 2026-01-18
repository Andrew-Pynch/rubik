#!/usr/bin/env python3
"""CV processing pipeline for Rubik's cube detection."""
from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from config import (
    CAMERA_ROTATION,
    CAMERA_TIMEOUT_MS,
    CAMERA_URL,
    COLOR_LETTERS,
    COLOR_RANGES,
    FACE_POLYGONS,
    OUTPUT_DIR,
    load_face_polygons,
)
from cube_model import CubeState
from detection import (
    StickerSample,
    detect_face_grid_robust,
    sample_sticker_multipoint,
    classify_sticker,
)


@dataclass
class DetectedSticker:
    """A detected sticker with its properties."""
    contour: np.ndarray
    center: tuple[int, int]
    area: float
    color_name: str
    color_letter: str


class CameraManager:
    """Manages persistent camera connection with auto-reconnect."""

    def __init__(self, url: str, timeout_ms: int = 5000):
        self.url = url
        self.timeout_ms = timeout_ms
        self.cap: cv2.VideoCapture | None = None
        self.connected = False
        self.last_error: str | None = None
        self._lock = threading.Lock()

    def _connect(self) -> bool:
        """Establish camera connection with timeout."""
        if self.cap:
            self.cap.release()
            self.cap = None

        # Create VideoCapture with FFmpeg backend
        self.cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

        # Set timeouts (may not work on all OpenCV builds)
        self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, self.timeout_ms)
        self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, self.timeout_ms)

        if self.cap.isOpened():
            self.connected = True
            self.last_error = None
            return True
        else:
            self.connected = False
            self.last_error = "Failed to open camera"
            return False

    def get_frame(self) -> np.ndarray | None:
        """Get a frame, reconnecting if needed."""
        with self._lock:
            if not self.connected or self.cap is None:
                if not self._connect():
                    return None

            ret, frame = self.cap.read()
            if not ret:
                self.connected = False
                self.last_error = "Frame read failed"
                return None

            return frame

    def get_status(self) -> dict:
        """Return connection status for UI."""
        return {
            "connected": self.connected,
            "error": self.last_error,
            "url": self.url
        }

    def disconnect(self):
        """Release camera connection."""
        with self._lock:
            if self.cap:
                self.cap.release()
                self.cap = None
            self.connected = False


# Global camera manager instance
_camera_manager: CameraManager | None = None


def get_camera_manager() -> CameraManager:
    """Get or create the global camera manager."""
    global _camera_manager
    if _camera_manager is None:
        _camera_manager = CameraManager(CAMERA_URL, timeout_ms=CAMERA_TIMEOUT_MS)
    return _camera_manager


def capture_frame() -> np.ndarray | None:
    """Capture single frame from IP camera using persistent connection.

    Returns:
        Captured frame or None if capture failed.
    """
    return get_camera_manager().get_frame()


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


def order_polygon_corners(polygon: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Order polygon corners as: top-left, top-right, bottom-right, bottom-left.

    Args:
        polygon: List of 4 (x, y) corner points.

    Returns:
        Corners ordered as TL, TR, BR, BL.
    """
    pts = np.array(polygon)

    # Sort by y first to get top vs bottom
    sorted_by_y = pts[np.argsort(pts[:, 1])]
    top_pts = sorted_by_y[:2]
    bottom_pts = sorted_by_y[2:]

    # Sort each pair by x to get left vs right
    top_pts = top_pts[np.argsort(top_pts[:, 0])]
    bottom_pts = bottom_pts[np.argsort(bottom_pts[:, 0])]

    return [
        tuple(top_pts[0]),
        tuple(top_pts[1]),
        tuple(bottom_pts[1]),
        tuple(bottom_pts[0])
    ]


def perspective_grid_point(
    col: int,
    row: int,
    ordered_corners: list[tuple[int, int]],
    inward_bias: float = 0.0,
) -> tuple[int, int]:
    """Get image coordinates for a cell in the 3x3 grid.

    Uses perspective transform to handle non-rectangular polygons.

    Args:
        col: Column index (0-2).
        row: Row index (0-2).
        ordered_corners: 4 corners in TL, TR, BR, BL order.
        inward_bias: Bias to pull corner samples toward center (0.0-0.3).
            Applied only to edge cells (col/row 0 or 2) to avoid sampling
            outside the sticker area.

    Returns:
        (x, y) coordinates of cell center in image space.
    """
    src = np.array(ordered_corners, dtype=np.float32)
    dst = np.array([[0, 0], [3, 0], [3, 3], [0, 3]], dtype=np.float32)

    # Calculate sample point with optional inward bias for edges
    col_offset = 0.5
    row_offset = 0.5

    if inward_bias > 0:
        # Pull edge cells toward center to avoid sampling outside stickers
        if col == 0:
            col_offset += inward_bias
        elif col == 2:
            col_offset -= inward_bias

        if row == 0:
            row_offset += inward_bias
        elif row == 2:
            row_offset -= inward_bias

    M = cv2.getPerspectiveTransform(dst, src)
    pt = np.array([[[col + col_offset, row + row_offset]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, M)

    return int(transformed[0, 0, 0]), int(transformed[0, 0, 1])


def detect_face_grid(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
    inward_bias: float = 0.15,
) -> list[list[str]] | None:
    """Detect 3x3 color grid using perspective-corrected sampling.

    This approach works for stickerless cubes where colors blend together.
    Center sticker (1,1) uses majority voting from neighbors to handle logos.

    Args:
        hsv_frame: HSV image.
        polygon: 4 corner points of face polygon.
        face_name: Name of face for debugging.
        inward_bias: Bias to pull edge samples toward center (default 0.15).
            Helps avoid sampling outside stickers at polygon edges.

    Returns:
        3x3 grid of color letters, or None if detection fails.
    """
    ordered = order_polygon_corners(polygon)

    grid: list[list[str]] = []
    for row in range(3):
        row_colors: list[str] = []
        for col in range(3):
            x, y = perspective_grid_point(col, row, ordered, inward_bias)

            # Bounds check
            if not (0 <= y < hsv_frame.shape[0] and 0 <= x < hsv_frame.shape[1]):
                row_colors.append('?')
                continue

            # Sample 15x15 region
            y1, y2 = max(0, y - 7), min(hsv_frame.shape[0], y + 8)
            x1, x2 = max(0, x - 7), min(hsv_frame.shape[1], x + 8)
            region = hsv_frame[y1:y2, x1:x2]

            if region.size == 0:
                row_colors.append('?')
                continue

            hsv_values = region.reshape(-1, 3)
            result = classify_color(hsv_values)

            if result:
                row_colors.append(result[1])  # color letter
            else:
                row_colors.append('?')

        grid.append(row_colors)

    # Fix center sticker using majority voting from neighbors
    # Center stickers often have logos that confuse detection
    neighbors = [
        grid[0][0], grid[0][1], grid[0][2],
        grid[1][0],             grid[1][2],
        grid[2][0], grid[2][1], grid[2][2],
    ]
    # Filter out unknown
    valid_neighbors = [c for c in neighbors if c != '?']
    if valid_neighbors:
        # Use most common neighbor color for center
        from collections import Counter
        most_common = Counter(valid_neighbors).most_common(1)[0][0]
        # Only override if majority agrees (at least 5 of 8)
        count = Counter(valid_neighbors)[most_common]
        if count >= 5:
            grid[1][1] = most_common

    return grid


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
        face_name: Name of the face (U, F, R) for debugging.

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
            min_area = poly_area * 0.005  # At least 0.5% of face
            max_area = poly_area * 0.25   # At most 25% of face
            if not (min_area < area < max_area):
                continue

            # Filter by aspect ratio (relaxed for stickerless cube pillows)
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / h if h > 0 else 0
            if not (0.3 < aspect < 3.5):
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
        Dict mapping face name (U, F, R) to list of 9 stickers.
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
    colors: dict[str, list[list[str]]] | None = None,
) -> np.ndarray:
    """Draw detected stickers and grid points on frame.

    Args:
        frame: BGR frame to annotate.
        faces: Grouped face stickers (from contour detection).
        face_polygons: Face polygon ROIs to draw (or None).
        colors: Grid-based color detection results (or None).

    Returns:
        Annotated frame.
    """
    debug = frame.copy()

    # Face polygon colors
    face_draw_colors = {
        'U': (255, 255, 255),  # White
        'F': (0, 0, 255),      # Red
        'R': (255, 100, 0),    # Blue
    }

    # Color letter to BGR
    letter_bgr = {
        'W': (255, 255, 255),
        'Y': (0, 255, 255),
        'O': (0, 165, 255),
        'R': (0, 0, 255),
        'G': (0, 255, 0),
        'B': (255, 0, 0),
        '?': (128, 128, 128),
    }

    total_stickers = 0

    # Draw face polygons and grid points
    if face_polygons:
        for face_name, polygon in face_polygons.items():
            poly_color = face_draw_colors.get(face_name, (255, 255, 0))
            pts = np.array(polygon, dtype=np.int32)
            cv2.polylines(debug, [pts], isClosed=True, color=poly_color, thickness=2)

            # Draw grid sampling points if we have grid results
            if colors and face_name in colors:
                ordered = order_polygon_corners(polygon)
                grid = colors[face_name]

                for row in range(3):
                    for col in range(3):
                        x, y = perspective_grid_point(col, row, ordered)
                        letter = grid[row][col]
                        bgr = letter_bgr.get(letter, (128, 128, 128))

                        # Draw filled circle at sample point
                        cv2.circle(debug, (x, y), 12, bgr, -1)
                        cv2.circle(debug, (x, y), 12, (0, 0, 0), 2)

                        # Draw letter
                        cv2.putText(
                            debug, letter, (x - 8, y + 6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2,
                        )

                        if letter != '?':
                            total_stickers += 1

                # Face label
                cx = int(np.mean([p[0] for p in polygon]))
                cy = int(np.mean([p[1] for p in polygon]))
                cv2.putText(
                    debug, f"[{face_name}]", (cx - 20, cy - 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2,
                )

    # Fall back to contour-based overlay if no grid results
    elif faces:
        color_bgr = {
            'white': (255, 255, 255), 'yellow': (0, 255, 255),
            'orange': (0, 165, 255), 'red': (0, 0, 255),
            'green': (0, 255, 0), 'blue': (255, 0, 0),
        }

        for face_name, face_stickers in faces.items():
            if not face_stickers:
                continue
            total_stickers += len(face_stickers)
            for sticker in face_stickers:
                bgr = color_bgr.get(sticker.color_name, (128, 128, 128))
                cv2.drawContours(debug, [sticker.contour], -1, bgr, 2)

    # Status text
    num_faces = len(colors) if colors else len(faces)
    cv2.putText(
        debug,
        f"Detected: {total_stickers} stickers, {num_faces} faces",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )

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


def grid_edge_point(
    col: float,
    row: float,
    ordered_corners: list[tuple[int, int]],
) -> tuple[int, int]:
    """Get image coordinates for a point on the grid (edge, not cell center).

    Unlike perspective_grid_point which returns cell centers, this maps
    raw grid coordinates directly (0-3 range maps to polygon corners).

    Args:
        col: Column position (0-3, where 0 and 3 are polygon edges).
        row: Row position (0-3, where 0 and 3 are polygon edges).
        ordered_corners: 4 corners in TL, TR, BR, BL order.

    Returns:
        (x, y) coordinates in image space.
    """
    src = np.array(ordered_corners, dtype=np.float32)
    dst = np.array([[0, 0], [3, 0], [3, 3], [0, 3]], dtype=np.float32)

    M = cv2.getPerspectiveTransform(dst, src)
    pt = np.array([[[col, row]]], dtype=np.float32)  # No +0.5 offset
    transformed = cv2.perspectiveTransform(pt, M)

    return int(transformed[0, 0, 0]), int(transformed[0, 0, 1])


def draw_grid_lines(debug: np.ndarray, polygon: list[tuple[int, int]]) -> None:
    """Draw perspective-correct grid lines on a face polygon.

    Draws 2 horizontal and 2 vertical lines marking sticker boundaries.

    Args:
        debug: Image to draw on (modified in place).
        polygon: 4 corner points of face polygon.
    """
    ordered = order_polygon_corners(polygon)

    # Draw horizontal dividers (between rows 0-1 and 1-2)
    # Line at y=1 separates row 0 from row 1
    # Line at y=2 separates row 1 from row 2
    for row in [1, 2]:
        p1 = grid_edge_point(0, row, ordered)
        p2 = grid_edge_point(3, row, ordered)
        cv2.line(debug, p1, p2, (0, 255, 255), 1, cv2.LINE_AA)

    # Draw vertical dividers (between cols 0-1 and 1-2)
    for col in [1, 2]:
        p1 = grid_edge_point(col, 0, ordered)
        p2 = grid_edge_point(col, 3, ordered)
        cv2.line(debug, p1, p2, (0, 255, 255), 1, cv2.LINE_AA)


def process_frame_for_stream(
    bgr_frame: np.ndarray,
    hsv_frame: np.ndarray,
    hsv_offsets: dict | None = None,
) -> np.ndarray:
    """Process a single frame for streaming with detection overlay.

    Uses robust multi-point detection and shows confidence visually.

    Args:
        bgr_frame: BGR frame to annotate.
        hsv_frame: HSV frame for color classification.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.

    Returns:
        Annotated BGR frame.
    """
    from config import load_face_polygons

    debug = bgr_frame.copy()
    face_polygons = load_face_polygons()

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

    # Color letter to BGR
    letter_bgr = {
        'W': (255, 255, 255),
        'Y': (0, 255, 255),
        'O': (0, 165, 255),
        'R': (0, 0, 255),
        'G': (0, 255, 0),
        'B': (255, 0, 0),
        '?': (128, 128, 128),
    }

    # Face polygon colors
    face_draw_colors = {
        'U': (255, 255, 255),
        'F': (0, 0, 255),
        'R': (255, 100, 0),
    }

    total_stickers = 0
    total_confidence = 0.0
    num_confidences = 0

    for face_name, polygon in face_polygons.items():
        poly_color = face_draw_colors.get(face_name, (255, 255, 0))
        pts = np.array(polygon, dtype=np.int32)
        cv2.polylines(debug, [pts], isClosed=True, color=poly_color, thickness=2)

        # Draw grid lines
        draw_grid_lines(debug, polygon)

        # Detect colors with confidence using robust sampling
        result = detect_face_grid_with_offsets(
            hsv_frame, polygon, face_name, hsv_offsets, return_confidence=True
        )

        if result is None:
            continue

        # Handle both tuple (with confidence) and list-only (legacy fallback)
        if isinstance(result, tuple):
            grid, confidences = result
        else:
            grid = result
            confidences = [[0.5] * 3 for _ in range(3)]  # Default confidence

        ordered = order_polygon_corners(polygon)
        for row in range(3):
            for col in range(3):
                x, y = perspective_grid_point(col, row, ordered)
                letter = grid[row][col]
                conf = confidences[row][col] if confidences else 0.5
                bgr = letter_bgr.get(letter, (128, 128, 128))

                # Draw filled circle at sample point
                cv2.circle(debug, (x, y), 12, bgr, -1)

                # Draw confidence ring: green=high, yellow=medium, red=low
                if conf >= 0.7:
                    ring_color = (0, 200, 0)  # Green
                    ring_thickness = 2
                elif conf >= 0.4:
                    ring_color = (0, 200, 200)  # Yellow
                    ring_thickness = 2
                else:
                    ring_color = (0, 0, 200)  # Red
                    ring_thickness = 3  # Thicker for low confidence
                cv2.circle(debug, (x, y), 12, ring_color, ring_thickness)

                # Draw letter
                cv2.putText(
                    debug, letter, (x - 8, y + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2,
                )

                if letter != '?':
                    total_stickers += 1
                total_confidence += conf
                num_confidences += 1

        # Face label with average confidence
        face_avg_conf = sum(sum(row) for row in confidences) / 9 if confidences else 0
        cx = int(np.mean([p[0] for p in polygon]))
        cy = int(np.mean([p[1] for p in polygon]))
        cv2.putText(
            debug, f"[{face_name}] {face_avg_conf:.0%}", (cx - 40, cy - 60),
            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2,
        )

    # Status text with average confidence
    avg_conf = total_confidence / num_confidences if num_confidences > 0 else 0
    cv2.putText(
        debug,
        f"Detected: {total_stickers} stickers, {len(face_polygons)} faces | Conf: {avg_conf:.0%}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0) if avg_conf >= 0.6 else (0, 200, 200),
        2,
    )

    return debug


def detect_face_grid_with_offsets(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
    hsv_offsets: dict | None = None,
    return_confidence: bool = False,
) -> list[list[str]] | tuple[list[list[str]], list[list[float]]] | None:
    """Detect 3x3 color grid with optional HSV offsets.

    Uses robust multi-point sampling with outlier rejection.

    Args:
        hsv_frame: HSV image.
        polygon: 4 corner points of face polygon.
        face_name: Name of face for debugging.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.
        return_confidence: If True, return (colors, confidences) tuple.

    Returns:
        3x3 grid of color letters, or (colors, confidences) if return_confidence=True,
        or None if detection fails.
    """
    try:
        colors, confidences, _ = detect_face_grid_robust(
            hsv_frame, polygon, face_name, hsv_offsets
        )
        if return_confidence:
            return colors, confidences
        return colors
    except Exception as e:
        print(f"Warning: Robust detection failed for {face_name}: {e}")
        # Fall back to original single-point detection
        return _detect_face_grid_legacy(hsv_frame, polygon, face_name, hsv_offsets)


def _detect_face_grid_legacy(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
    hsv_offsets: dict | None = None,
) -> list[list[str]] | None:
    """Legacy single-point detection (fallback).

    Args:
        hsv_frame: HSV image.
        polygon: 4 corner points of face polygon.
        face_name: Name of face for debugging.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.

    Returns:
        3x3 grid of color letters, or None if detection fails.
    """
    ordered = order_polygon_corners(polygon)

    grid: list[list[str]] = []
    for row in range(3):
        row_colors: list[str] = []
        for col in range(3):
            x, y = perspective_grid_point(col, row, ordered)

            # Bounds check
            if not (0 <= y < hsv_frame.shape[0] and 0 <= x < hsv_frame.shape[1]):
                row_colors.append('?')
                continue

            # Sample 15x15 region
            y1, y2 = max(0, y - 7), min(hsv_frame.shape[0], y + 8)
            x1, x2 = max(0, x - 7), min(hsv_frame.shape[1], x + 8)
            region = hsv_frame[y1:y2, x1:x2]

            if region.size == 0:
                row_colors.append('?')
                continue

            hsv_values = region.reshape(-1, 3)
            result = classify_color_with_offsets(hsv_values, hsv_offsets)

            if result:
                row_colors.append(result[1])  # color letter
            else:
                row_colors.append('?')

        grid.append(row_colors)

    # Fix center sticker using majority voting from neighbors
    neighbors = [
        grid[0][0], grid[0][1], grid[0][2],
        grid[1][0],             grid[1][2],
        grid[2][0], grid[2][1], grid[2][2],
    ]
    valid_neighbors = [c for c in neighbors if c != '?']
    if valid_neighbors:
        from collections import Counter
        most_common = Counter(valid_neighbors).most_common(1)[0][0]
        count = Counter(valid_neighbors)[most_common]
        if count >= 5:
            grid[1][1] = most_common

    return grid


def classify_color_with_offsets(
    hsv_values: np.ndarray,
    hsv_offsets: dict | None = None,
) -> tuple[str, str] | None:
    """Classify HSV values to a cube color with optional offsets.

    Args:
        hsv_values: Array of HSV values (Nx3) to classify.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.

    Returns:
        Tuple of (color_name, color_letter) or None if no match.
    """
    # Calculate median for robustness
    h = np.median(hsv_values[:, 0])
    s = np.median(hsv_values[:, 1])
    v = np.median(hsv_values[:, 2])

    # Apply global offsets if provided
    if hsv_offsets:
        h = (h + hsv_offsets.get('h', 0)) % 180
        s = max(0, min(255, s + hsv_offsets.get('s', 0)))
        v = max(0, min(255, v + hsv_offsets.get('v', 0)))

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
            h_match = any(r[0] <= h <= r[1] for r in h_range)
        else:
            h_match = h_range[0] <= h <= h_range[1]

        if h_match:
            return color_name, COLOR_LETTERS[color_name]

    return None


def detect_current_frame() -> dict[str, list[list[str]]] | None:
    """Capture and detect faces, returning grids without saving files.

    Used by capture session for multi-capture workflow.

    Returns:
        Dict mapping positional face names (U/F/R) to 3x3 color grids,
        or None if capture/detection failed.
    """
    # Capture frame
    frame = capture_frame()
    if frame is None:
        return None

    # Preprocess
    bgr_frame, hsv_frame = preprocess(frame)

    # Load face polygons
    face_polygons = load_face_polygons()
    if not face_polygons:
        return None

    # Detect each face
    colors: dict[str, list[list[str]]] = {}
    for face_name, polygon in face_polygons.items():
        grid = detect_face_grid(hsv_frame, polygon, face_name)
        if grid:
            colors[face_name] = grid

    # Also save raw/debug for visualization (user still sees these)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT_DIR / "raw.jpg"), bgr_frame)

    faces: dict[str, list[DetectedSticker]] = {}
    debug_frame = draw_debug_overlay(bgr_frame, faces, face_polygons, colors)
    cv2.imwrite(str(OUTPUT_DIR / "debug.jpg"), debug_frame)

    return colors if colors else None


def detect_from_frames(
    bgr_frame: np.ndarray,
    hsv_frame: np.ndarray,
    return_confidence: bool = False,
) -> dict[str, list[list[str]]] | tuple[dict[str, list[list[str]]], dict[str, list[list[float]]]] | None:
    """Detect faces from pre-captured frames.

    Used when livestream is running and we already have frames.

    Args:
        bgr_frame: Preprocessed BGR frame.
        hsv_frame: Preprocessed HSV frame.
        return_confidence: If True, return (colors, confidences) tuple.

    Returns:
        Dict mapping positional face names (U/F/R) to 3x3 color grids,
        or (colors, confidences) tuple if return_confidence=True,
        or None if detection failed.
    """
    # Load face polygons
    face_polygons = load_face_polygons()
    if not face_polygons:
        return None

    # Detect each face with confidence
    colors: dict[str, list[list[str]]] = {}
    confidences: dict[str, list[list[float]]] = {}

    for face_name, polygon in face_polygons.items():
        result = detect_face_grid_with_offsets(
            hsv_frame, polygon, face_name, return_confidence=True
        )
        if result:
            if isinstance(result, tuple):
                grid, conf_grid = result
                colors[face_name] = grid
                confidences[face_name] = conf_grid
            else:
                colors[face_name] = result
                # Default confidence of 0.5 for legacy fallback
                confidences[face_name] = [[0.5] * 3 for _ in range(3)]

    # Save raw/debug for visualization
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUTPUT_DIR / "raw.jpg"), bgr_frame)

    faces: dict[str, list[DetectedSticker]] = {}
    debug_frame = draw_debug_overlay(bgr_frame, faces, face_polygons, colors)
    cv2.imwrite(str(OUTPUT_DIR / "debug.jpg"), debug_frame)

    if not colors:
        return None

    if return_confidence:
        return colors, confidences
    return colors


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

        # Use robust multi-point detection with confidence scoring
        print("Detecting colors using robust multi-point sampling...")
        colors: dict[str, list[list[str]]] = {}
        confidences: dict[str, list[list[float]]] = {}

        for face_name, polygon in face_polygons.items():
            result = detect_face_grid_with_offsets(
                hsv_frame, polygon, face_name, return_confidence=True
            )
            if result:
                if isinstance(result, tuple):
                    grid, conf_grid = result
                    colors[face_name] = grid
                    confidences[face_name] = conf_grid
                else:
                    colors[face_name] = result
                    confidences[face_name] = [[0.5] * 3 for _ in range(3)]

                # Count detected (non-'?') stickers and average confidence
                detected = sum(1 for row in colors[face_name] for c in row if c != '?')
                avg_conf = sum(sum(row) for row in confidences[face_name]) / 9
                print(f"  {face_name}: {detected}/9 stickers detected (avg conf: {avg_conf:.2f})")

        total = sum(sum(1 for row in g for c in row if c != '?') for g in colors.values())
        print(f"Total: {total} stickers in {len(colors)} faces")

        # Create empty faces dict for debug overlay (no contours in grid mode)
        faces: dict[str, list[DetectedSticker]] = {}
    else:
        print("WARNING: No calibration found - detection will be limited")
        print("Use the web UI to calibrate face polygons")
        faces = {}
        colors = {}
        confidences = {}

    # Create cube state with confidence data
    overall_confidence = len(colors) / 3.0  # 3 visible faces expected
    state = CubeState.from_detected(
        colors,
        confidence=min(overall_confidence, 1.0),
        confidences=confidences if confidences else None
    )

    # Save debug overlay
    debug_frame = draw_debug_overlay(bgr_frame, faces, face_polygons, colors)
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

    # Capture 3D visualization screenshot for verification
    try:
        from screenshot_3d import capture_with_server
        screenshot_path = capture_with_server()
        print(f"3D screenshot: {screenshot_path}")
    except Exception as e:
        print(f"Warning: Could not capture 3D screenshot: {e}")
