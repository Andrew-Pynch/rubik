#!/usr/bin/env python3
"""Grid-based color detection for stickerless cubes.

Instead of finding contours, we divide each face polygon into a 3x3 grid
and sample the color at each cell center.
"""
import cv2
import numpy as np
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import COLOR_RANGES, COLOR_LETTERS, OUTPUT_DIR, CALIBRATION_PATH


def perspective_transform_point(pt, src_quad, dst_size=3):
    """Transform a point from normalized grid coords to polygon coords.

    Uses perspective transform to handle non-rectangular polygons.
    """
    # src_quad: 4 corners of polygon [top-left, top-right, bottom-right, bottom-left]
    # pt: (col, row) in range [0, dst_size)
    src = np.array(src_quad, dtype=np.float32)
    dst = np.array([
        [0, 0],
        [dst_size, 0],
        [dst_size, dst_size],
        [0, dst_size]
    ], dtype=np.float32)

    # Get inverse transform (dst -> src)
    M = cv2.getPerspectiveTransform(dst, src)

    # Transform point (add 0.5 to get cell center)
    pt_normalized = np.array([[[pt[0] + 0.5, pt[1] + 0.5]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt_normalized, M)

    return int(transformed[0,0,0]), int(transformed[0,0,1])


def order_polygon_corners(polygon):
    """Order polygon corners as: top-left, top-right, bottom-right, bottom-left.

    Based on the perspective view of the cube.
    """
    pts = np.array(polygon)

    # Sort by y first to get top vs bottom
    sorted_by_y = pts[np.argsort(pts[:, 1])]
    top_pts = sorted_by_y[:2]
    bottom_pts = sorted_by_y[2:]

    # Sort each pair by x to get left vs right
    top_pts = top_pts[np.argsort(top_pts[:, 0])]
    bottom_pts = bottom_pts[np.argsort(bottom_pts[:, 0])]

    # Return in order: TL, TR, BR, BL
    return [
        tuple(top_pts[0]),
        tuple(top_pts[1]),
        tuple(bottom_pts[1]),
        tuple(bottom_pts[0])
    ]


def classify_hsv(h, s, v):
    """Classify a single HSV value to a color name."""
    for color_name, ranges in COLOR_RANGES.items():
        h_range = ranges['h']
        s_range = ranges['s']
        v_range = ranges['v']

        # Check saturation and value
        if not (s_range[0] <= s <= s_range[1]):
            continue
        if not (v_range[0] <= v <= v_range[1]):
            continue

        # Check hue
        if isinstance(h_range, list):
            h_match = any(r[0] <= h <= r[1] for r in h_range)
        else:
            h_match = h_range[0] <= h <= h_range[1]

        if h_match:
            return color_name

    return 'unknown'


def detect_face_grid(hsv, polygon, face_name):
    """Detect 3x3 color grid for a face using perspective sampling."""
    ordered = order_polygon_corners(polygon)

    grid = []
    for row in range(3):
        row_colors = []
        for col in range(3):
            # Get sample point in image coordinates
            x, y = perspective_transform_point((col, row), ordered)

            # Sample 15x15 region around point
            y1, y2 = max(0, y-7), min(hsv.shape[0], y+8)
            x1, x2 = max(0, x-7), min(hsv.shape[1], x+8)
            region = hsv[y1:y2, x1:x2]

            if region.size == 0:
                row_colors.append('?')
                continue

            h = np.median(region[:,:,0])
            s = np.median(region[:,:,1])
            v = np.median(region[:,:,2])

            color = classify_hsv(h, s, v)
            letter = COLOR_LETTERS.get(color, '?')
            row_colors.append(letter)

        grid.append(row_colors)

    return grid


def main():
    # Load image
    img = cv2.imread(str(OUTPUT_DIR / "raw.jpg"))
    filtered = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)

    # Load calibration
    with open(CALIBRATION_PATH) as f:
        calib = json.load(f)

    print("Grid-based detection results:")
    print("=" * 40)

    results = {}
    for face_name, polygon in calib['face_polygons'].items():
        grid = detect_face_grid(hsv, polygon, face_name)
        results[face_name] = grid

        print(f"\n{face_name} face:")
        for row in grid:
            print(f"  {row}")

    # Count accuracy for solved cube
    expected = {'U': 'W', 'L': 'R', 'R': 'B'}
    print("\n" + "=" * 40)
    print("Accuracy check (assuming solved cube):")
    for face, expected_letter in expected.items():
        if face in results:
            grid = results[face]
            correct = sum(1 for row in grid for c in row if c == expected_letter)
            print(f"  {face}: {correct}/9 correct ({expected_letter})")

    # Draw debug visualization
    debug = img.copy()
    for face_name, polygon in calib['face_polygons'].items():
        ordered = order_polygon_corners(polygon)

        # Draw polygon
        pts = np.array(ordered, dtype=np.int32)
        cv2.polylines(debug, [pts], True, (0, 255, 0), 2)

        # Draw grid sample points
        for row in range(3):
            for col in range(3):
                x, y = perspective_transform_point((col, row), ordered)
                cv2.circle(debug, (x, y), 5, (0, 0, 255), -1)

                # Add detected letter
                if face_name in results:
                    letter = results[face_name][row][col]
                    cv2.putText(debug, letter, (x+8, y+5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    debug_path = OUTPUT_DIR / "debug_grid.jpg"
    cv2.imwrite(str(debug_path), debug)
    print(f"\nSaved: {debug_path}")


if __name__ == "__main__":
    main()
