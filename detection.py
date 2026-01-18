"""Robust sticker detection with multi-point sampling and confidence scoring.

This module provides hardened color detection for Rubik's cube stickers using:
- 9-point grid sampling per sticker (3x3 within each cell)
- MAD (Median Absolute Deviation) outlier rejection
- Per-sticker confidence scores based on consistency, distance, and margin
"""

from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from config import COLOR_RANGES, COLOR_LETTERS


@dataclass
class SamplePoint:
    """A single HSV sample point from a sticker."""
    x: int
    y: int
    h: float
    s: float
    v: float


@dataclass
class StickerSample:
    """Aggregated sample data for one sticker cell.

    Attributes:
        row: Row index (0-2) in the face grid.
        col: Column index (0-2) in the face grid.
        points: List of individual sample points (after outlier rejection).
        consensus_hsv: Robust median HSV after outlier rejection.
        spread: MAD of hue values normalized to 0-1 (0 = perfect agreement).
        color_name: Full color name (e.g., 'red', 'blue') or None if unknown.
        color_letter: Single letter (W/Y/O/R/G/B/?) for state representation.
        confidence: 0.0-1.0 confidence score for this classification.
        alternatives: List of (color_letter, confidence) for runner-up colors.
    """
    row: int
    col: int
    points: list[SamplePoint] = field(default_factory=list)
    consensus_hsv: tuple[float, float, float] = (0.0, 0.0, 0.0)
    spread: float = 1.0  # 1.0 = max uncertainty
    color_name: Optional[str] = None
    color_letter: str = '?'
    confidence: float = 0.0
    alternatives: list[tuple[str, float]] = field(default_factory=list)


def sample_sticker_multipoint(
    hsv_frame: np.ndarray,
    center_x: int,
    center_y: int,
    row: int,
    col: int,
    region_size: int = 30,
    grid_points: int = 3,
) -> StickerSample:
    """Sample multiple points within a sticker cell with outlier rejection.

    Samples a 3x3 grid of points within the sticker region, applies MAD-based
    outlier rejection on hue values, and computes a robust consensus HSV.

    Args:
        hsv_frame: Full HSV image.
        center_x: X coordinate of sticker cell center.
        center_y: Y coordinate of sticker cell center.
        row: Row index in face grid (0-2).
        col: Column index in face grid (0-2).
        region_size: Total size of sampling region in pixels (default 30).
        grid_points: Number of points per axis (default 3 = 9 total points).

    Returns:
        StickerSample with consensus HSV, spread metric, and sample points.
    """
    samples: list[SamplePoint] = []
    step = region_size // (grid_points + 1)

    # Sample at grid_points x grid_points positions
    for i in range(grid_points):
        for j in range(grid_points):
            # Offset from center to create grid
            dx = (i - (grid_points - 1) / 2) * step
            dy = (j - (grid_points - 1) / 2) * step

            x = int(center_x + dx)
            y = int(center_y + dy)

            # Bounds check with margin for micro-region
            if not (2 <= y < hsv_frame.shape[0] - 2 and 2 <= x < hsv_frame.shape[1] - 2):
                continue

            # Sample 5x5 micro-region at this point
            region = hsv_frame[y-2:y+3, x-2:x+3]
            if region.size == 0:
                continue

            # Use median of micro-region for robustness
            h = float(np.median(region[:, :, 0]))
            s = float(np.median(region[:, :, 1]))
            v = float(np.median(region[:, :, 2]))

            samples.append(SamplePoint(x, y, h, s, v))

    # Need at least 3 samples for meaningful statistics
    if len(samples) < 3:
        return StickerSample(
            row=row, col=col,
            points=samples,
            consensus_hsv=(0.0, 0.0, 0.0),
            spread=1.0,
            color_letter='?',
            confidence=0.0
        )

    # Compute MAD (Median Absolute Deviation) for outlier rejection on hue
    hues = np.array([s.h for s in samples])

    # Handle hue wraparound: if range spans 0/180 boundary, shift values
    if np.max(hues) - np.min(hues) > 90:
        # Likely wraparound case (e.g., red spans 170-10)
        hues = np.where(hues < 90, hues + 180, hues)

    median_h = np.median(hues)
    mad = np.median(np.abs(hues - median_h))

    # Filter outliers (> 2.5 MAD from median)
    # MAD of 0 means perfect agreement - use small threshold
    threshold = max(2.5 * mad, 5.0) if mad > 0 else 10.0

    inliers = []
    for s, h in zip(samples, hues):
        if abs(h - median_h) <= threshold:
            inliers.append(s)

    # If too few inliers, keep all samples
    if len(inliers) < 3:
        inliers = samples

    # Compute consensus HSV from inliers
    inlier_h = np.array([s.h for s in inliers])
    inlier_s = np.array([s.s for s in inliers])
    inlier_v = np.array([s.v for s in inliers])

    # Handle hue wraparound for consensus
    if np.max(inlier_h) - np.min(inlier_h) > 90:
        inlier_h = np.where(inlier_h < 90, inlier_h + 180, inlier_h)

    consensus_h = float(np.median(inlier_h)) % 180
    consensus_s = float(np.median(inlier_s))
    consensus_v = float(np.median(inlier_v))

    # Recalculate MAD for spread metric using original hues
    final_mad = np.median(np.abs(np.array([s.h for s in inliers]) - consensus_h))
    spread = min(final_mad / 36.0, 1.0)  # Normalize: MAD of 36 (20% of 180) = 1.0

    return StickerSample(
        row=row, col=col,
        points=inliers,
        consensus_hsv=(consensus_h, consensus_s, consensus_v),
        spread=spread,
        color_letter='?',  # Will be filled by classify
        confidence=0.0     # Will be filled by compute_confidence
    )


def compute_color_distance(
    hsv: tuple[float, float, float],
    ranges: dict,
) -> float:
    """Compute distance from HSV value to a color range centroid.

    Args:
        hsv: (H, S, V) tuple.
        ranges: Color range dict with 'h', 's', 'v' keys.

    Returns:
        Weighted distance (lower = better match). Returns inf if outside range.
    """
    h, s, v = hsv
    h_range = ranges['h']
    s_range = ranges['s']
    v_range = ranges['v']

    # Check if within S/V ranges first
    if not (s_range[0] <= s <= s_range[1]):
        return float('inf')
    if not (v_range[0] <= v <= v_range[1]):
        return float('inf')

    # Check hue range (handle red wraparound)
    if isinstance(h_range, list):
        # Red has two ranges
        in_range = any(r[0] <= h <= r[1] for r in h_range)
        if not in_range:
            return float('inf')
        # Use closest range for centroid calculation
        centroids = [(r[0] + r[1]) / 2 for r in h_range]
        h_center = min(centroids, key=lambda c: min(abs(h - c), 180 - abs(h - c)))
    else:
        if not (h_range[0] <= h <= h_range[1]):
            return float('inf')
        h_center = (h_range[0] + h_range[1]) / 2

    s_center = (s_range[0] + s_range[1]) / 2
    v_center = (v_range[0] + v_range[1]) / 2

    # Weighted Euclidean distance in HSV space
    # Hue is most important, then saturation, then value
    dh = min(abs(h - h_center), 180 - abs(h - h_center))  # Handle wraparound
    ds = abs(s - s_center)
    dv = abs(v - v_center)

    # Normalize each component and weight
    # Hue: 0-180, Sat: 0-255, Val: 0-255
    distance = np.sqrt(
        (dh / 180) ** 2 * 4.0 +  # Hue weighted 4x
        (ds / 255) ** 2 * 1.0 +  # Saturation weighted 1x
        (dv / 255) ** 2 * 0.5    # Value weighted 0.5x
    )

    return distance


def compute_confidence(
    sample: StickerSample,
    best_color: str,
    best_distance: float,
    second_distance: float,
) -> float:
    """Compute confidence score for a sticker classification.

    Confidence is based on three factors:
    - Sample consistency (40%): Low spread = high confidence
    - Color distance (35%): Proximity to color centroid
    - Classification margin (25%): Gap between best and second-best match

    Args:
        sample: The StickerSample with spread metric.
        best_color: The best matching color name.
        best_distance: Distance to best matching color.
        second_distance: Distance to second-best color (or inf if none).

    Returns:
        Confidence score from 0.0 to 1.0.
    """
    # 1. Sample consistency (low spread = high confidence)
    # spread of 0 = perfect, spread of 0.2+ = uncertain
    consistency = max(0.0, 1.0 - sample.spread * 5.0)

    # 2. Color distance score (0 = far, 1 = exact centroid match)
    # distance of 0 = perfect, distance of 0.5+ = poor
    if best_distance == float('inf'):
        distance_score = 0.0
    else:
        distance_score = max(0.0, 1.0 - best_distance * 2.0)

    # 3. Classification margin (how much better than second choice)
    if second_distance == float('inf'):
        margin_score = 1.0  # No competition
    else:
        margin = second_distance - best_distance
        margin_score = min(margin * 3.0, 1.0)

    # Weighted combination
    confidence = (
        0.40 * consistency +
        0.35 * distance_score +
        0.25 * margin_score
    )

    return round(max(0.0, min(1.0, confidence)), 3)


def classify_sticker(
    sample: StickerSample,
    hsv_offsets: dict | None = None,
) -> StickerSample:
    """Classify a sticker sample to a color with confidence.

    Updates the sample in-place with color_name, color_letter, confidence,
    and alternatives.

    Args:
        sample: StickerSample with consensus_hsv computed.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.

    Returns:
        The same StickerSample with classification filled in.
    """
    h, s, v = sample.consensus_hsv

    # Apply global offsets if provided
    if hsv_offsets:
        h = (h + hsv_offsets.get('h', 0)) % 180
        s = max(0, min(255, s + hsv_offsets.get('s', 0)))
        v = max(0, min(255, v + hsv_offsets.get('v', 0)))

    adjusted_hsv = (h, s, v)

    # Compute distance to all colors
    distances: list[tuple[str, float]] = []
    for color_name, ranges in COLOR_RANGES.items():
        dist = compute_color_distance(adjusted_hsv, ranges)
        distances.append((color_name, dist))

    # Sort by distance
    distances.sort(key=lambda x: x[1])

    # Best match
    best_color, best_dist = distances[0]
    second_dist = distances[1][1] if len(distances) > 1 else float('inf')

    # Compute confidence
    confidence = compute_confidence(sample, best_color, best_dist, second_dist)

    # Determine color letter
    if best_dist == float('inf') or confidence < 0.15:
        # Too uncertain - mark as unknown
        sample.color_name = None
        sample.color_letter = '?'
        sample.confidence = confidence
    else:
        sample.color_name = best_color
        sample.color_letter = COLOR_LETTERS[best_color]
        sample.confidence = confidence

    # Track alternatives (runner-ups with non-infinite distance)
    sample.alternatives = [
        (COLOR_LETTERS[name], max(0, 1.0 - dist * 2.0))
        for name, dist in distances[1:4]
        if dist != float('inf')
    ]

    return sample


def detect_face_grid_robust(
    hsv_frame: np.ndarray,
    polygon: list[tuple[int, int]],
    face_name: str,
    hsv_offsets: dict | None = None,
    inward_bias: float = 0.15,
) -> tuple[list[list[str]], list[list[float]], list[StickerSample]]:
    """Detect 3x3 color grid using robust multi-point sampling.

    This is the main entry point for hardened detection, replacing the
    single-point sampling approach.

    Args:
        hsv_frame: HSV image.
        polygon: 4 corner points of face polygon.
        face_name: Name of face for debugging.
        hsv_offsets: Optional HSV offsets for color tuning.
        inward_bias: Bias to pull edge samples toward center (default 0.15).

    Returns:
        Tuple of:
        - 3x3 grid of color letters
        - 3x3 grid of confidence scores
        - Flat list of all 9 StickerSample objects
    """
    from pipeline import order_polygon_corners, perspective_grid_point

    ordered = order_polygon_corners(polygon)

    colors: list[list[str]] = []
    confidences: list[list[float]] = []
    all_samples: list[StickerSample] = []

    for row in range(3):
        row_colors: list[str] = []
        row_confidences: list[float] = []

        for col in range(3):
            # Get center point for this cell
            x, y = perspective_grid_point(col, row, ordered, inward_bias)

            # Multi-point sampling
            sample = sample_sticker_multipoint(hsv_frame, x, y, row, col)

            # Classify with confidence
            sample = classify_sticker(sample, hsv_offsets)

            row_colors.append(sample.color_letter)
            row_confidences.append(sample.confidence)
            all_samples.append(sample)

        colors.append(row_colors)
        confidences.append(row_confidences)

    # Apply center sticker majority voting (same as original)
    # Center stickers often have logos that confuse detection
    neighbors = [
        colors[0][0], colors[0][1], colors[0][2],
        colors[1][0],               colors[1][2],
        colors[2][0], colors[2][1], colors[2][2],
    ]
    neighbor_confs = [
        confidences[0][0], confidences[0][1], confidences[0][2],
        confidences[1][0],                     confidences[1][2],
        confidences[2][0], confidences[2][1], confidences[2][2],
    ]

    # Filter to high-confidence neighbors
    valid_neighbors = [
        (c, conf) for c, conf in zip(neighbors, neighbor_confs)
        if c != '?' and conf > 0.5
    ]

    if len(valid_neighbors) >= 5:
        from collections import Counter
        counts = Counter(c for c, _ in valid_neighbors)
        most_common, count = counts.most_common(1)[0]
        if count >= 5:
            # Override center with majority vote
            colors[1][1] = most_common
            # Boost confidence for voted center
            confidences[1][1] = min(count / 8.0, 0.95)
            # Update the sample object too
            center_sample = all_samples[4]  # Index 4 is (1,1)
            center_sample.color_letter = most_common
            center_sample.confidence = confidences[1][1]

    return colors, confidences, all_samples
