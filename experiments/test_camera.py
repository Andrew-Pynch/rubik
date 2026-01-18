#!/usr/bin/env python3
"""Quick test of camera capture."""
import cv2
import sys

CAMERA_URL = "http://192.168.1.237:8081/video"

print(f"Attempting to connect to: {CAMERA_URL}")
print("This may take a few seconds...")

cap = cv2.VideoCapture(CAMERA_URL)
print(f"VideoCapture created, isOpened: {cap.isOpened()}")

if not cap.isOpened():
    print("ERROR: Could not open camera stream")
    print("Check that:")
    print("  1. iPhone IP Camera app is running")
    print("  2. iPhone is on same network as this computer")
    print("  3. URL is correct (try opening in browser)")
    sys.exit(1)

print("Reading frame...")
ret, frame = cap.read()
cap.release()

if not ret:
    print("ERROR: Could not read frame")
    sys.exit(1)

print(f"SUCCESS: Got frame with shape {frame.shape}")
print(f"Saving to experiments/test_frame.jpg")
cv2.imwrite("experiments/test_frame.jpg", frame)
