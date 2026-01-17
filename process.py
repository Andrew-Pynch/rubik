#!/usr/bin/env python3
"""Main processing script - captures frame and runs full CV pipeline."""
from __future__ import annotations

import json
import sys

import cv2

from config import CAMERA_URL, OUTPUT_DIR
from preprocess import preprocess
from detect import detect_stickers, group_into_faces, extract_face_colors, draw_debug_overlay
from cube_model import CubeState


def capture_frame():
    """Capture a single frame from the IP camera."""
    print(f"Connecting to {CAMERA_URL}...")
    cap = cv2.VideoCapture(CAMERA_URL)

    if not cap.isOpened():
        print("ERROR: Cannot connect to camera")
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("ERROR: Failed to read frame")
        return None

    print(f"Captured frame: {frame.shape}")
    return frame


def run_pipeline(frame):
    """Run the full CV pipeline on a frame."""
    # Preprocess
    print("Preprocessing...")
    bgr_frame, hsv_frame = preprocess(frame)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save raw frame
    raw_path = OUTPUT_DIR / "raw.jpg"
    cv2.imwrite(str(raw_path), bgr_frame)
    print(f"Saved: {raw_path}")

    # Detect stickers
    print("Detecting stickers...")
    stickers = detect_stickers(bgr_frame, hsv_frame)
    print(f"Found {len(stickers)} potential stickers")

    # Show color distribution
    color_counts = {}
    for s in stickers:
        color_counts[s.color_name] = color_counts.get(s.color_name, 0) + 1
    if color_counts:
        print(f"Colors: {color_counts}")

    # Group into faces
    print("Grouping into faces...")
    faces = group_into_faces(stickers)
    print(f"Identified {len(faces)} faces: {list(faces.keys())}")

    # Extract colors
    colors = extract_face_colors(faces)
    for face, grid in colors.items():
        print(f"  {face}: {grid}")

    # Create cube state
    confidence = len(colors) / 3.0
    state = CubeState.from_detected(colors, confidence=min(confidence, 1.0))

    # Save debug overlay
    debug_frame = draw_debug_overlay(bgr_frame, stickers, faces)
    debug_path = OUTPUT_DIR / "debug.jpg"
    cv2.imwrite(str(debug_path), debug_frame)
    print(f"Saved: {debug_path}")

    # Save state JSON
    state_path = OUTPUT_DIR / "state.json"
    with open(state_path, 'w') as f:
        json.dump(state.to_json(), f, indent=2)
    print(f"Saved: {state_path}")

    return state


def main():
    """Main entry point."""
    # Capture
    frame = capture_frame()
    if frame is None:
        sys.exit(1)

    # Process
    state = run_pipeline(frame)

    print(f"\nResult: {state}")
    return state


if __name__ == "__main__":
    main()
