"""Image preprocessing for Rubik's cube detection."""
import cv2
import numpy as np

from config import CAMERA_ROTATION


def rotate_frame(frame: np.ndarray) -> np.ndarray:
    """Rotate frame to correct camera orientation."""
    return cv2.rotate(frame, CAMERA_ROTATION)


def apply_filters(frame: np.ndarray) -> np.ndarray:
    """Apply noise reduction filters while preserving edges."""
    return cv2.bilateralFilter(frame, d=9, sigmaColor=75, sigmaSpace=75)


def to_hsv(frame: np.ndarray) -> np.ndarray:
    """Convert BGR frame to HSV color space."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)


def preprocess(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Full preprocessing pipeline.

    Args:
        frame: Raw camera frame (BGR).

    Returns:
        Tuple of (rotated BGR frame, HSV frame).
    """
    rotated = rotate_frame(frame)
    filtered = apply_filters(rotated)
    hsv = to_hsv(filtered)
    return rotated, hsv
