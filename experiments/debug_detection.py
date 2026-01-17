#!/usr/bin/env python3
"""Debug script to visualize detection pipeline step by step."""
import cv2
import numpy as np
import json
from pathlib import Path
import sys

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import COLOR_RANGES, OUTPUT_DIR, CALIBRATION_PATH

def main():
    # Load raw image (already rotated by pipeline)
    img = cv2.imread(str(OUTPUT_DIR / "raw.jpg"))
    print(f"Image shape: {img.shape} (H={img.shape[0]}, W={img.shape[1]})")

    # Apply same preprocessing as pipeline
    filtered = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)

    # Load calibration
    with open(CALIBRATION_PATH) as f:
        calib = json.load(f)

    print(f"\nCalibration faces: {list(calib['face_polygons'].keys())}")

    # For each face, check what the color masks look like
    for face_name, polygon in calib['face_polygons'].items():
        print(f"\n{'='*50}")
        print(f"Face: {face_name}")
        pts = np.array(polygon, dtype=np.int32)
        poly_area = cv2.contourArea(pts)
        print(f"Polygon area: {poly_area:.0f} px²")

        # Create polygon mask
        poly_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        cv2.fillPoly(poly_mask, [pts], 255)

        # Sample center
        cx, cy = int(np.mean(pts[:,0])), int(np.mean(pts[:,1]))
        region = hsv[cy-15:cy+15, cx-15:cx+15]
        h, s, v = np.median(region[:,:,0]), np.median(region[:,:,1]), np.median(region[:,:,2])
        print(f"Center HSV: H={h:.0f}, S={s:.0f}, V={v:.0f}")

        # Test each color mask
        kernel = np.ones((5, 5), np.uint8)

        for color_name, ranges in COLOR_RANGES.items():
            h_range = ranges['h']
            s_range = ranges['s']
            v_range = ranges['v']

            # Create color mask
            if isinstance(h_range, list):
                color_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
                for hr in h_range:
                    lower = np.array([hr[0], s_range[0], v_range[0]])
                    upper = np.array([hr[1], s_range[1], v_range[1]])
                    color_mask |= cv2.inRange(hsv, lower, upper)
            else:
                lower = np.array([h_range[0], s_range[0], v_range[0]])
                upper = np.array([h_range[1], s_range[1], v_range[1]])
                color_mask = cv2.inRange(hsv, lower, upper)

            # Apply polygon mask
            combined = cv2.bitwise_and(color_mask, poly_mask)

            # Morphological cleanup
            combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel)
            combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel)

            # Count pixels and contours
            pixel_count = np.sum(combined > 0)
            contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if pixel_count > 100:  # Significant detection
                print(f"  {color_name}: {pixel_count} pixels, {len(contours)} contours")

                # Check contour areas
                for i, c in enumerate(contours[:3]):  # First 3
                    area = cv2.contourArea(c)
                    pct = (area / poly_area) * 100
                    x, y, w, h = cv2.boundingRect(c)
                    aspect = w / h if h > 0 else 0
                    print(f"    contour {i}: area={area:.0f} ({pct:.1f}% of face), aspect={aspect:.2f}")

    # Save debug visualization
    debug = img.copy()
    for face_name, polygon in calib['face_polygons'].items():
        pts = np.array(polygon, dtype=np.int32)
        cv2.polylines(debug, [pts], True, (0, 255, 0), 2)
        cx, cy = int(np.mean(pts[:,0])), int(np.mean(pts[:,1]))
        cv2.putText(debug, face_name, (cx-10, cy), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    debug_path = OUTPUT_DIR / "debug_polygons.jpg"
    cv2.imwrite(str(debug_path), debug)
    print(f"\nSaved polygon overlay: {debug_path}")

if __name__ == "__main__":
    main()
