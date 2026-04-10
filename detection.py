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

from config import (
    COLOR_RANGES, COLOR_LETTERS,
    WHITE_DETECTION_THRESHOLD, WHITE_DETECTION_CENTER_THRESHOLD,
    WHITE_SAT_MAX, WHITE_VAL_MIN,
    DETECTION_SAMPLING,
)


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
    region_size: int | None = None,
    grid_points: int | None = None,
) -> StickerSample:
    """Sample multiple points within a sticker cell with outlier rejection.

    Samples a 5x5 grid of points (25 total) within the sticker region with
    Gaussian center weighting, applies MAD-based outlier rejection on hue
    values, and computes a robust consensus HSV.

    Args:
        hsv_frame: Full HSV image.
        center_x: X coordinate of sticker cell center.
        center_y: Y coordinate of sticker cell center.
        row: Row index in face grid (0-2).
        col: Column index in face grid (0-2).
        region_size: Total size of sampling region in pixels (default 30).
        grid_points: Number of points per axis (default 5 = 25 total points).

    Returns:
        StickerSample with consensus HSV, spread metric, and sample points.
    """
    # Use config defaults if not specified
    if region_size is None:
        region_size = DETECTION_SAMPLING['region_size']
    if grid_points is None:
        grid_points = DETECTION_SAMPLING['grid_points']

    samples: list[SamplePoint] = []
    weights: list[float] = []
    step = region_size // (grid_points + 1)

    # Gaussian weighting parameters (center samples count more)
    center_idx = (grid_points - 1) / 2
    sigma = grid_points / 3.0  # Spread of Gaussian

    # Sample at grid_points x grid_points positions
    for i in range(grid_points):
        for j in range(grid_points):
            # Offset from center to create grid
            dx = (i - center_idx) * step
            dy = (j - center_idx) * step

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

            # Gaussian weight: center=1.0, edges~0.4
            dist_from_center = np.sqrt((i - center_idx)**2 + (j - center_idx)**2)
            weight = float(np.exp(-0.5 * (dist_from_center / sigma)**2))
            weights.append(weight)

    # Need minimum samples for meaningful statistics
    min_samples = DETECTION_SAMPLING['min_samples_required']
    if len(samples) < min_samples:
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
    if len(inliers) < min_samples:
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
    spread_norm = DETECTION_SAMPLING['spread_normalization']
    spread = min(final_mad / spread_norm, 1.0)  # Normalize: MAD of spread_norm (20% of 180) = 1.0

    return StickerSample(
        row=row, col=col,
        points=inliers,
        consensus_hsv=(consensus_h, consensus_s, consensus_v),
        spread=spread,
        color_letter='?',  # Will be filled by classify
        confidence=0.0     # Will be filled by compute_confidence
    )


def compute_white_percentage(samples: list[SamplePoint]) -> float:
    """Compute percentage of samples that match white HSV criteria.

    White is defined as: low saturation (s < WHITE_SAT_MAX) and high value
    (v > WHITE_VAL_MIN). This is robust to logos since logos are typically
    saturated colors.

    Args:
        samples: List of SamplePoint with h, s, v values.

    Returns:
        Percentage of samples matching white criteria (0.0 to 1.0).
    """
    if not samples:
        return 0.0

    white_count = sum(
        1 for s in samples
        if s.s < WHITE_SAT_MAX and s.v > WHITE_VAL_MIN
    )

    return white_count / len(samples)


def detect_sticker_histogram(
    hsv_frame: np.ndarray,
    center_x: int,
    center_y: int,
    cell_size: int = 30,
) -> tuple[str, float] | None:
    """Histogram-based color detection as fallback for low-confidence cases.

    Analyzes color distribution in the sticker region rather than relying on
    point samples. Useful when point sampling has high spread or low confidence.

    Args:
        hsv_frame: HSV image.
        center_x, center_y: Center of sticker cell.
        cell_size: Approximate cell size in pixels.

    Returns:
        (color_letter, confidence) or None if no dominant color found.
    """
    # Extract region (50% of cell size to avoid edges)
    half_size = cell_size // 4
    y1 = max(0, center_y - half_size)
    y2 = min(hsv_frame.shape[0], center_y + half_size)
    x1 = max(0, center_x - half_size)
    x2 = min(hsv_frame.shape[1], center_x + half_size)

    region = hsv_frame[y1:y2, x1:x2]

    if region.size < 100:  # Need minimum pixels for meaningful histogram
        return None

    total_pixels = region.shape[0] * region.shape[1]
    color_scores: dict[str, float] = {}

    for color_name, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']

        # Create mask for saturation and value
        s_mask = (region[:, :, 1] >= s_range[0]) & (region[:, :, 1] <= s_range[1])
        v_mask = (region[:, :, 2] >= v_range[0]) & (region[:, :, 2] <= v_range[1])

        # Handle hue (including red wraparound)
        if isinstance(h_range, list):
            # Red has two ranges
            h_mask = np.zeros(region.shape[:2], dtype=bool)
            for hr in h_range:
                h_mask |= (region[:, :, 0] >= hr[0]) & (region[:, :, 0] <= hr[1])
        else:
            h_mask = (region[:, :, 0] >= h_range[0]) & (region[:, :, 0] <= h_range[1])

        full_mask = h_mask & s_mask & v_mask
        pixel_count = int(np.sum(full_mask))
        color_scores[color_name] = pixel_count / total_pixels

    if not color_scores:
        return None

    # Find dominant color
    best_color = max(color_scores, key=lambda k: color_scores[k])
    best_score = color_scores[best_color]

    # Need minimum pixel coverage
    min_coverage = DETECTION_SAMPLING['histogram_min_coverage']
    if best_score < min_coverage:
        return None

    # Confidence based on dominance
    sorted_scores = sorted(color_scores.values(), reverse=True)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0
    margin = best_score - second_best
    confidence = min(best_score + margin, 0.95)

    return COLOR_LETTERS[best_color], confidence


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
    is_center: bool = False,
) -> StickerSample:
    """Classify a sticker sample to a color with confidence.

    Updates the sample in-place with color_name, color_letter, confidence,
    and alternatives.

    Args:
        sample: StickerSample with consensus_hsv computed.
        hsv_offsets: Optional dict with 'h', 's', 'v' offset values.
        is_center: Whether this is a center sticker (row=1, col=1).
            Center stickers use a lower white detection threshold to handle logos.

    Returns:
        The same StickerSample with classification filled in.
    """
    # Check for white override based on pixel percentage
    # This handles logos on white stickers (e.g., GAN cube blue logo)
    white_pct = compute_white_percentage(sample.points)
    threshold = WHITE_DETECTION_CENTER_THRESHOLD if is_center else WHITE_DETECTION_THRESHOLD

    if white_pct >= threshold:
        sample.color_name = 'white'
        sample.color_letter = 'W'
        # Confidence based on how many white pixels, capped at 0.95
        sample.confidence = min(0.95, white_pct)
        sample.alternatives = []
        return sample

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

            # Classify with confidence (pass is_center for logo handling)
            is_center = (row == 1 and col == 1)
            sample = classify_sticker(sample, hsv_offsets, is_center=is_center)

            # Histogram fallback for low-confidence or unknown stickers
            low_conf_thresh = DETECTION_SAMPLING['low_confidence_threshold']
            if sample.confidence < low_conf_thresh or sample.color_letter == '?':
                hist_result = detect_sticker_histogram(
                    hsv_frame, x, y, cell_size=DETECTION_SAMPLING['region_size']
                )
                if hist_result:
                    hist_letter, hist_conf = hist_result
                    # Use histogram result if it's more confident
                    if hist_conf > sample.confidence:
                        sample.color_letter = hist_letter
                        # Blend confidences (histogram is backup, so slight discount)
                        sample.confidence = (sample.confidence + hist_conf * 0.9) / 2
                        # Find color name from letter
                        for name, letter in COLOR_LETTERS.items():
                            if letter == hist_letter:
                                sample.color_name = name
                                break

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
