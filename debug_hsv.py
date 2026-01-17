#!/usr/bin/env python3
"""Debug script to check image dimensions and sample HSV."""
import cv2
import numpy as np
import json
from config import CAMERA_ROTATION, OUTPUT_DIR, CALIBRATION_PATH

# Load raw image
img = cv2.imread(str(OUTPUT_DIR / "raw.jpg"))
print(f"Raw image shape: {img.shape}")

rotated = cv2.rotate(img, CAMERA_ROTATION)
print(f"After 90° CW rotation: {rotated.shape}")

# Load calibration
with open(CALIBRATION_PATH) as f:
    calib = json.load(f)

# Print polygon bounds
for face, polygon in calib['face_polygons'].items():
    pts = np.array(polygon)
    print(f"{face} polygon: x=[{pts[:,0].min()}-{pts[:,0].max()}], y=[{pts[:,1].min()}-{pts[:,1].max()}]")
    
print()
print("Calibration was likely done on the ROTATED image shown in web UI")
print("Let's sample from the rotated image which is what the web UI shows")

# The web UI shows the rotated image, so calibration coords should work on it
filtered = cv2.bilateralFilter(rotated, d=9, sigmaColor=75, sigmaSpace=75)
hsv = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)

# Sample specific points that should be on each face
# Looking at the debug image, U face is at top, L is bottom-left, R is bottom-right
test_points = {
    'U_top_center': (680, 650),      # Top face, middle area
    'U_middle': (550, 800),           # Top face, center
    'L_center': (350, 1100),          # Left face center
    'R_center': (800, 900),           # Right face center
}

print("\nTesting specific points:")
for name, (x, y) in test_points.items():
    if y >= rotated.shape[0] or x >= rotated.shape[1]:
        print(f"{name} ({x},{y}): OUT OF BOUNDS")
        continue
    region = hsv[max(0,y-10):y+10, max(0,x-10):x+10]
    if region.size > 0:
        h = np.median(region[:,:,0])
        s = np.median(region[:,:,1])
        v = np.median(region[:,:,2])
        print(f"{name} ({x},{y}): H={h:.0f}, S={s:.0f}, V={v:.0f}")
