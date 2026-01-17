"""Color detection and sticker finding for Rubik's cube."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from config import COLOR_LETTERS, COLOR_RANGES


@dataclass
class DetectedSticker:
    """A detected sticker with its properties."""
    contour: np.ndarray
    center: tuple[int, int]
    area: float
    color_name: str
    color_letter: str


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


def classify_color(hsv_frame: np.ndarray, x: int, y: int, size: int = 15) -> tuple[str, str] | None:
    """Classify the color at a given position.

    Returns:
        Tuple of (color_name, color_letter) or None if no match.
    """
    h, w = hsv_frame.shape[:2]
    x1, y1 = max(0, x - size), max(0, y - size)
    x2, y2 = min(w, x + size), min(h, y + size)

    region = hsv_frame[y1:y2, x1:x2]
    if region.size == 0:
        return None

    mean_h = np.mean(region[:, :, 0])
    mean_s = np.mean(region[:, :, 1])
    mean_v = np.mean(region[:, :, 2])

    for color_name, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']

        # Check S and V
        if not (s_range[0] <= mean_s <= s_range[1]):
            continue
        if not (v_range[0] <= mean_v <= v_range[1]):
            continue

        # Check H (handle red wraparound)
        if isinstance(h_range, list):
            h_match = any(r[0] <= mean_h <= r[1] for r in h_range)
        else:
            h_match = h_range[0] <= mean_h <= h_range[1]

        if h_match:
            return color_name, COLOR_LETTERS[color_name]

    return None


def detect_stickers(
    bgr_frame: np.ndarray,
    hsv_frame: np.ndarray,
) -> list[DetectedSticker]:
    """Find cube stickers using edge detection + color classification.

    Args:
        bgr_frame: BGR frame for visualization.
        hsv_frame: HSV frame for color classification.

    Returns:
        List of detected stickers with color information.
    """
    detected: list[DetectedSticker] = []
    frame_area = bgr_frame.shape[0] * bgr_frame.shape[1]

    # Convert to grayscale
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)

    # Apply blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Use adaptive thresholding to find edges (better for stickerless cubes)
    adaptive = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # Also try Canny with lower thresholds
    edges = cv2.Canny(blurred, 30, 80)

    # Combine both methods
    combined = cv2.bitwise_or(adaptive, edges)

    # Dilate to connect edges
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(combined, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    for contour in contours:
        # Approximate to polygon
        epsilon = 0.05 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)

        # Filter: roughly quadrilateral (4-6 vertices)
        if not (4 <= len(approx) <= 6):
            continue

        # Filter by area
        area = cv2.contourArea(contour)
        min_area = frame_area * 0.001  # 0.1% of frame
        max_area = frame_area * 0.05   # 5% of frame
        if not (min_area < area < max_area):
            continue

        # Filter by aspect ratio (looser for perspective)
        x, y, w, h = cv2.boundingRect(contour)
        aspect = w / h if h > 0 else 0
        if not (0.4 < aspect < 2.5):
            continue

        # Get center
        M = cv2.moments(contour)
        if M['m00'] == 0:
            continue
        cx = int(M['m10'] / M['m00'])
        cy = int(M['m01'] / M['m00'])

        # Classify color at center
        color_result = classify_color(hsv_frame, cx, cy, size=min(w, h) // 4)
        if color_result is None:
            # Try with "unknown" for debugging
            color_name, color_letter = 'unknown', '?'
        else:
            color_name, color_letter = color_result

        detected.append(DetectedSticker(
            contour=contour,
            center=(cx, cy),
            area=area,
            color_name=color_name,
            color_letter=color_letter,
        ))

    return detected


def group_into_faces(stickers: list[DetectedSticker]) -> dict[str, list[DetectedSticker]]:
    """Group detected stickers into faces based on spatial position."""
    if len(stickers) < 9:
        return {}

    centers = np.array([s.center for s in stickers])
    median_area = np.median([s.area for s in stickers])
    sticker_size = int(np.sqrt(median_area))
    cluster_threshold = sticker_size * 2

    faces: dict[str, list[DetectedSticker]] = {}
    used = set()

    for i, sticker in enumerate(stickers):
        if i in used:
            continue

        cluster = [sticker]
        used.add(i)

        for j, other in enumerate(stickers):
            if j in used:
                continue

            for cs in cluster:
                dist = np.sqrt((cs.center[0] - other.center[0])**2 +
                              (cs.center[1] - other.center[1])**2)
                if dist < cluster_threshold * 3:
                    cluster.append(other)
                    used.add(j)
                    break

            if len(cluster) >= 9:
                break

        if len(cluster) >= 9:
            cluster = sorted(cluster, key=lambda s: abs(s.area - median_area))[:9]

            avg_y = np.mean([s.center[1] for s in cluster])
            avg_x = np.mean([s.center[0] for s in cluster])
            frame_h = max(s.center[1] for s in stickers)
            frame_w = max(s.center[0] for s in stickers)

            if avg_y < frame_h * 0.4:
                face_name = 'U'
            elif avg_x < frame_w * 0.5:
                face_name = 'L'
            else:
                face_name = 'R'

            if face_name not in faces:
                faces[face_name] = cluster

    return faces


def extract_face_colors(faces: dict[str, list[DetectedSticker]]) -> dict[str, list[list[str]]]:
    """Extract 3x3 color grid from each detected face."""
    result: dict[str, list[list[str]]] = {}

    for face_name, stickers in faces.items():
        if len(stickers) != 9:
            continue

        sorted_stickers = sorted(stickers, key=lambda s: (s.center[1], s.center[0]))

        grid: list[list[str]] = []
        for row_idx in range(3):
            row_stickers = sorted_stickers[row_idx * 3:(row_idx + 1) * 3]
            row_stickers = sorted(row_stickers, key=lambda s: s.center[0])
            row = [s.color_letter for s in row_stickers]
            grid.append(row)

        result[face_name] = grid

    return result


def draw_debug_overlay(
    frame: np.ndarray,
    stickers: list[DetectedSticker],
    faces: dict[str, list[DetectedSticker]],
) -> np.ndarray:
    """Draw detected contours and color labels on frame."""
    debug = frame.copy()

    color_bgr = {
        'white': (255, 255, 255),
        'yellow': (0, 255, 255),
        'orange': (0, 165, 255),
        'red': (0, 0, 255),
        'green': (0, 255, 0),
        'blue': (255, 0, 0),
        'unknown': (128, 128, 128),
    }

    for sticker in stickers:
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

    for face_name, face_stickers in faces.items():
        if face_stickers:
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

    cv2.putText(
        debug,
        f"Detected: {len(stickers)} stickers, {len(faces)} faces",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2,
    )

    return debug
