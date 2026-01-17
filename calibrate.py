#!/usr/bin/env python3
"""Calibration script to sample cube colors and tune detection."""
import cv2
import numpy as np
from config import OUTPUT_DIR, COLOR_RANGES

def sample_region(hsv, x, y, size=15):
    """Sample HSV values from a region."""
    region = hsv[max(0,y-size):y+size, max(0,x-size):x+size]
    return region.mean(axis=(0,1))

def main():
    # Load the latest capture
    frame = cv2.imread(str(OUTPUT_DIR / "raw.jpg"))
    if frame is None:
        print("ERROR: No raw.jpg found. Run process.py first.")
        return

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    h, w = frame.shape[:2]
    print(f"Frame: {w}x{h}")

    # Define sample points on the actual cube
    # Cube position in frame (1080x1920): centered around x=450, y=750
    samples = {
        # White top face - 9 stickers (tilted perspective)
        'white': [
            (310, 590), (400, 560), (490, 530),  # top row
            (330, 680), (420, 650), (510, 620),  # middle row
            (350, 770), (440, 740), (530, 710),  # bottom row
        ],
        # Red left face - 9 stickers
        'red': [
            (250, 820), (310, 865), (365, 910),  # top row
            (235, 920), (290, 965), (345, 1010), # middle row
            (220, 1020), (275, 1065), (330, 1110), # bottom row
        ],
        # Blue right face - 9 stickers
        'blue': [
            (570, 670), (650, 720), (730, 765),  # top row
            (585, 775), (665, 820), (745, 865),  # middle row
            (600, 880), (680, 925), (760, 970),  # bottom row
        ],
    }

    print("\n=== Sampling actual cube colors ===\n")

    all_samples = {}
    for color_name, points in samples.items():
        print(f"{color_name.upper()} face:")
        hsv_values = []
        for i, (x, y) in enumerate(points):
            if 0 <= x < w and 0 <= y < h:
                mean_hsv = sample_region(hsv, x, y)
                hsv_values.append(mean_hsv)
                print(f"  [{i+1}] ({x:4d},{y:4d}): H={mean_hsv[0]:5.1f} S={mean_hsv[1]:5.1f} V={mean_hsv[2]:5.1f}")

        if hsv_values:
            arr = np.array(hsv_values)
            all_samples[color_name] = {
                'h_min': arr[:,0].min(),
                'h_max': arr[:,0].max(),
                's_min': arr[:,1].min(),
                's_max': arr[:,1].max(),
                'v_min': arr[:,2].min(),
                'v_max': arr[:,2].max(),
            }
            print(f"  Range: H=[{arr[:,0].min():.0f}-{arr[:,0].max():.0f}] "
                  f"S=[{arr[:,1].min():.0f}-{arr[:,1].max():.0f}] "
                  f"V=[{arr[:,2].min():.0f}-{arr[:,2].max():.0f}]")
        print()

    print("=== Suggested COLOR_RANGES (with margin) ===\n")
    margin_h = 10
    margin_sv = 30

    for color_name, stats in all_samples.items():
        h_lo = max(0, stats['h_min'] - margin_h)
        h_hi = min(180, stats['h_max'] + margin_h)
        s_lo = max(0, stats['s_min'] - margin_sv)
        s_hi = min(255, stats['s_max'] + margin_sv)
        v_lo = max(0, stats['v_min'] - margin_sv)
        v_hi = min(255, stats['v_max'] + margin_sv)

        print(f"'{color_name}': {{'h': ({h_lo:.0f}, {h_hi:.0f}), 's': ({s_lo:.0f}, {s_hi:.0f}), 'v': ({v_lo:.0f}, {v_hi:.0f})}},")

    # Draw sample points visualization
    debug = frame.copy()
    colors_bgr = {'white': (255,255,255), 'red': (0,0,255), 'blue': (255,0,0)}
    for color_name, points in samples.items():
        bgr = colors_bgr[color_name]
        for x, y in points:
            cv2.circle(debug, (x, y), 10, bgr, 2)

    cv2.imwrite(str(OUTPUT_DIR / "calibrate.jpg"), debug)
    print(f"\nSaved sample points to: {OUTPUT_DIR / 'calibrate.jpg'}")

if __name__ == "__main__":
    main()
