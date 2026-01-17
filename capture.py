#!/usr/bin/env python3
"""Capture a single frame from the IP camera and save it."""
import cv2
import sys
from pathlib import Path

from config import CAMERA_URL, CAMERA_ROTATION

OUTPUT = Path(__file__).parent / "snapshot.jpg"


def capture_frame() -> cv2.typing.MatLike | None:
    """Capture a single frame from the IP camera.

    Returns:
        The captured frame (rotated), or None if capture failed.
    """
    cap = cv2.VideoCapture(CAMERA_URL)
    if not cap.isOpened():
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        return None

    # Rotate to correct for camera orientation
    frame = cv2.rotate(frame, CAMERA_ROTATION)
    return frame


if __name__ == "__main__":
    frame = capture_frame()
    if frame is None:
        print("ERROR: Cannot connect to camera or failed to capture frame")
        sys.exit(1)

    cv2.imwrite(str(OUTPUT), frame)
    print(f"Saved: {OUTPUT}")
