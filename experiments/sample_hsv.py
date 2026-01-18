#!/usr/bin/env python3
"""Sample HSV values from current camera frame at face centers.

Usage:
    python experiments/sample_hsv.py

This script captures a frame and samples HSV values at the center
of each calibrated face polygon. Use this to tune COLOR_RANGES in config.py.
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from pipeline import capture_frame, preprocess
from config import load_face_polygons, COLOR_RANGES


def sample_hsv_at_point(hsv, x, y, size=15):
    """Sample HSV values in a region around a point."""
    half = size // 2
    y1, y2 = max(0, y - half), min(hsv.shape[0], y + half + 1)
    x1, x2 = max(0, x - half), min(hsv.shape[1], x + half + 1)
    region = hsv[y1:y2, x1:x2]

    if region.size == 0:
        return None

    h = np.median(region[:, :, 0])
    s = np.median(region[:, :, 1])
    v = np.median(region[:, :, 2])
    return {'h': h, 's': s, 'v': v}


def classify_hsv(h, s, v):
    """Try to classify HSV values against current COLOR_RANGES."""
    for color_name, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']

        # Check saturation and value
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
            return color_name

    return None


def main():
    print("Sampling HSV values from camera frame...")
    print("=" * 60)

    frame = capture_frame()
    if frame is None:
        print("ERROR: Failed to capture frame")
        return 1

    bgr, hsv = preprocess(frame)
    polygons = load_face_polygons()

    if not polygons:
        print("ERROR: No calibration found. Run calibration first.")
        return 1

    print(f"\nFrame shape: {hsv.shape}")
    print(f"Calibrated faces: {list(polygons.keys())}")
    print()

    print("Face Center HSV Samples:")
    print("-" * 60)

    for face, polygon in polygons.items():
        # Calculate center
        cx = sum(p[0] for p in polygon) // 4
        cy = sum(p[1] for p in polygon) // 4

        hsv_vals = sample_hsv_at_point(hsv, cx, cy)
        if hsv_vals:
            h, s, v = hsv_vals['h'], hsv_vals['s'], hsv_vals['v']
            detected = classify_hsv(h, s, v)
            detected_str = detected.upper() if detected else "???"

            print(f"  [{face}] center=({cx}, {cy})")
            print(f"       H={h:5.1f}  S={s:5.1f}  V={v:5.1f}  -> {detected_str}")
        else:
            print(f"  [{face}] Failed to sample")

    print()
    print("Current COLOR_RANGES from config.py:")
    print("-" * 60)
    for color, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']
        if isinstance(h_range, list):
            h_str = f"[{h_range[0]}, {h_range[1]}]"
        else:
            h_str = f"({h_range[0]}-{h_range[1]})"
        print(f"  {color:8s}: H={h_str:20s} S=({s_range[0]}-{s_range[1]}) V=({v_range[0]}-{v_range[1]})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
