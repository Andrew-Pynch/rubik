#!/usr/bin/env python3
"""Test lighting normalization approaches for Rubik's cube detection.

Compares detection results with and without CLAHE normalization,
measuring per-face detection rate, confidence, and V-channel statistics.

Usage:
    .venv/bin/python experiments/test_lighting_normalization.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from dataclasses import dataclass

from config import CAMERA_ROTATION, load_face_polygons, COLOR_RANGES, OUTPUT_DIR
from pipeline import capture_frame, order_polygon_corners, perspective_grid_point

GROUND_TRUTH_PATH = OUTPUT_DIR / "ground_truth.json"


def load_ground_truth() -> dict | None:
    """Load ground truth colors from file if available."""
    if GROUND_TRUTH_PATH.exists():
        import json
        with open(GROUND_TRUTH_PATH) as f:
            data = json.load(f)
            return data.get('colors')
    return None


def compare_to_ground_truth(
    detected: dict[str, list[list[str]]],
    ground_truth: dict[str, list[list[str | None]]]
) -> dict:
    """Compare detected colors to ground truth.

    Returns dict with accuracy stats.
    """
    correct = 0
    incorrect = 0
    missing_gt = 0
    unknown_detected = 0

    mismatches = []

    for face in ['U', 'F', 'R']:
        if face not in detected or face not in ground_truth:
            continue
        for row in range(3):
            for col in range(3):
                gt_color = ground_truth[face][row][col]
                det_color = detected[face][row][col]

                if gt_color is None:
                    missing_gt += 1
                elif det_color == '?':
                    unknown_detected += 1
                elif det_color == gt_color:
                    correct += 1
                else:
                    incorrect += 1
                    mismatches.append(f"{face}[{row},{col}]: expected {gt_color}, got {det_color}")

    total = correct + incorrect + unknown_detected
    accuracy = correct / total if total > 0 else 0

    return {
        'correct': correct,
        'incorrect': incorrect,
        'unknown': unknown_detected,
        'missing_gt': missing_gt,
        'accuracy': accuracy,
        'mismatches': mismatches,
    }


@dataclass
class FaceMetrics:
    """Detection metrics for a single face."""
    face_name: str
    detected: int        # Stickers with color != '?'
    total: int           # Always 9
    avg_confidence: float
    min_confidence: float
    median_v_before: float
    median_v_after: float
    std_v_before: float
    std_v_after: float


def get_polygon_mask(shape: tuple, polygon: list[tuple[int, int]]) -> np.ndarray:
    """Create a binary mask for a polygon region."""
    mask = np.zeros(shape[:2], dtype=np.uint8)
    pts = np.array(polygon, dtype=np.int32)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def get_v_channel_stats(hsv_frame: np.ndarray, polygon: list[tuple[int, int]]) -> tuple[float, float]:
    """Get median and std of V channel within polygon."""
    mask = get_polygon_mask(hsv_frame.shape, polygon)
    v_values = hsv_frame[:, :, 2][mask > 0]
    return float(np.median(v_values)), float(np.std(v_values))


def apply_clahe_to_frame(bgr_frame: np.ndarray, clip_limit: float = 2.0,
                          tile_grid: tuple[int, int] = (8, 8)) -> np.ndarray:
    """Apply CLAHE to V channel of entire frame."""
    hsv = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2HSV)
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)
    hsv[:, :, 2] = clahe.apply(hsv[:, :, 2])
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)


def apply_clahe_per_face(bgr_frame: np.ndarray, polygons: dict,
                          clip_limit: float = 2.0,
                          tile_grid: tuple[int, int] = (4, 4)) -> np.ndarray:
    """Apply CLAHE to V channel independently for each face region."""
    result = bgr_frame.copy()
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid)

    for face_name, polygon in polygons.items():
        pts = np.array(polygon)
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)

        # Add small margin
        margin = 5
        x_min = max(0, x_min - margin)
        y_min = max(0, y_min - margin)
        x_max = min(bgr_frame.shape[1], x_max + margin)
        y_max = min(bgr_frame.shape[0], y_max + margin)

        # Extract region, apply CLAHE to V channel
        region = result[y_min:y_max, x_min:x_max]
        hsv_region = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hsv_region[:, :, 2] = clahe.apply(hsv_region[:, :, 2])
        result[y_min:y_max, x_min:x_max] = cv2.cvtColor(hsv_region, cv2.COLOR_HSV2BGR)

    return result


def run_detection(hsv_frame: np.ndarray, polygons: dict) -> tuple[dict[str, FaceMetrics], dict[str, list[list[str]]]]:
    """Run detection and collect metrics per face.

    Returns:
        Tuple of (metrics dict, detected colors dict)
    """
    from detection import sample_sticker_multipoint, classify_sticker

    results = {}
    colors = {}

    for face_name, polygon in polygons.items():
        ordered = order_polygon_corners(polygon)
        confidences = []
        detected = 0
        face_colors = []

        for row in range(3):
            row_colors = []
            for col in range(3):
                x, y = perspective_grid_point(col, row, ordered)
                sample = sample_sticker_multipoint(hsv_frame, x, y, row, col)
                sample = classify_sticker(sample, is_center=(row == 1 and col == 1))
                confidences.append(sample.confidence)
                row_colors.append(sample.color_letter)
                if sample.color_letter != '?':
                    detected += 1
            face_colors.append(row_colors)

        results[face_name] = FaceMetrics(
            face_name=face_name,
            detected=detected,
            total=9,
            avg_confidence=float(np.mean(confidences)),
            min_confidence=float(min(confidences)),
            median_v_before=0.0,  # Filled in later
            median_v_after=0.0,
            std_v_before=0.0,
            std_v_after=0.0,
        )
        colors[face_name] = face_colors

    return results, colors


def test_approach(name: str, bgr_frame: np.ndarray, polygons: dict,
                  hsv_before: np.ndarray) -> tuple[dict[str, FaceMetrics], dict[str, list[list[str]]]]:
    """Test a specific approach and return metrics and colors."""
    # Apply filters and convert to HSV
    filtered = cv2.bilateralFilter(bgr_frame, d=9, sigmaColor=75, sigmaSpace=75)
    hsv_after = cv2.cvtColor(filtered, cv2.COLOR_BGR2HSV)

    # Run detection
    results, colors = run_detection(hsv_after, polygons)

    # Add V-channel stats
    for face_name, polygon in polygons.items():
        v_med_before, v_std_before = get_v_channel_stats(hsv_before, polygon)
        v_med_after, v_std_after = get_v_channel_stats(hsv_after, polygon)
        results[face_name].median_v_before = v_med_before
        results[face_name].median_v_after = v_med_after
        results[face_name].std_v_before = v_std_before
        results[face_name].std_v_after = v_std_after

    return results, colors


def print_results(name: str, results: dict[str, FaceMetrics], baseline: dict[str, FaceMetrics] = None):
    """Print formatted results for an approach."""
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    print(f"{'Face':<6} {'Det.':<8} {'Avg Conf':<10} {'Min Conf':<10} {'V med':<10} {'V std':<8}")
    print(f"{'-' * 60}")

    for face in ['U', 'F', 'R']:
        if face not in results:
            continue
        m = results[face]

        # Delta from baseline
        delta_str = ""
        if baseline and face in baseline:
            delta_det = m.detected - baseline[face].detected
            delta_conf = m.avg_confidence - baseline[face].avg_confidence
            if delta_det != 0 or abs(delta_conf) > 0.01:
                sign_det = '+' if delta_det > 0 else ''
                sign_conf = '+' if delta_conf > 0 else ''
                delta_str = f" ({sign_det}{delta_det}, {sign_conf}{delta_conf:.2f})"

        print(f"{face:<6} {m.detected}/9{'':<4} {m.avg_confidence:<10.3f} {m.min_confidence:<10.3f} "
              f"{m.median_v_after:<10.1f} {m.std_v_after:<8.1f}{delta_str}")


def main():
    print("\n" + "=" * 60)
    print("  LIGHTING NORMALIZATION TEST")
    print("=" * 60)

    # Capture frame
    print("\nCapturing frame from camera...")
    frame = capture_frame()
    if frame is None:
        print("ERROR: Failed to capture frame from camera")
        return 1

    # Rotate frame
    rotated = cv2.rotate(frame, CAMERA_ROTATION)
    print(f"Frame captured: {rotated.shape[1]}x{rotated.shape[0]}")

    # Load polygons
    polygons = load_face_polygons()
    if not polygons:
        print("ERROR: No calibration found")
        return 1
    print(f"Loaded {len(polygons)} face polygons: {list(polygons.keys())}")

    # Get baseline HSV for V-channel comparison
    hsv_baseline = cv2.cvtColor(rotated, cv2.COLOR_BGR2HSV)

    # Print initial V-channel stats
    print("\nInitial V-channel statistics per face:")
    for face, polygon in polygons.items():
        v_med, v_std = get_v_channel_stats(hsv_baseline, polygon)
        brightness = "LOW" if v_med < 100 else "HIGH" if v_med > 200 else "NORMAL"
        print(f"  {face}: median_v={v_med:.1f}, std={v_std:.1f} [{brightness}]")

    # Load ground truth if available
    ground_truth = load_ground_truth()
    if ground_truth:
        print(f"\nGround truth loaded from {GROUND_TRUTH_PATH}")
        marked = sum(1 for f in ground_truth.values() for r in f for c in r if c)
        print(f"  {marked}/27 stickers marked")
    else:
        print("\nNo ground truth file found - accuracy comparison not available")
        print(f"  Create one via the web UI or manually edit {GROUND_TRUTH_PATH}")

    # Test 1: Baseline (no normalization)
    print("\nRunning baseline detection...")
    baseline, baseline_colors = test_approach("Baseline", rotated.copy(), polygons, hsv_baseline)
    print_results("BASELINE (no normalization)", baseline)
    if ground_truth:
        gt_result = compare_to_ground_truth(baseline_colors, ground_truth)
        print(f"  Ground truth: {gt_result['correct']}/{gt_result['correct']+gt_result['incorrect']+gt_result['unknown']} correct ({gt_result['accuracy']:.0%})")
        if gt_result['mismatches']:
            print(f"  Mismatches: {', '.join(gt_result['mismatches'][:3])}")

    # Test 2: Global CLAHE
    print("\nTesting global CLAHE...")
    for clip in [1.5, 2.0, 2.5, 3.0]:
        clahe_frame = apply_clahe_to_frame(rotated.copy(), clip_limit=clip)
        results, colors = test_approach(f"Global CLAHE (clip={clip})", clahe_frame, polygons, hsv_baseline)
        print_results(f"GLOBAL CLAHE (clip_limit={clip})", results, baseline)

    # Test 3: Per-face CLAHE
    print("\nTesting per-face CLAHE...")
    for clip in [1.5, 2.0, 2.5, 3.0]:
        clahe_frame = apply_clahe_per_face(rotated.copy(), polygons, clip_limit=clip)
        results, colors = test_approach(f"Per-face CLAHE (clip={clip})", clahe_frame, polygons, hsv_baseline)
        print_results(f"PER-FACE CLAHE (clip_limit={clip})", results, baseline)

    # Test 4: Per-face CLAHE with different tile sizes
    print("\nTesting per-face CLAHE with different tile sizes...")
    for tile_size in [(2, 2), (4, 4), (8, 8)]:
        clahe_frame = apply_clahe_per_face(rotated.copy(), polygons, clip_limit=2.0, tile_grid=tile_size)
        results, colors = test_approach(f"Per-face CLAHE (tiles={tile_size})", clahe_frame, polygons, hsv_baseline)
        print_results(f"PER-FACE CLAHE (tiles={tile_size[0]}x{tile_size[1]})", results, baseline)

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print("\nTarget: R face detection should improve from current to 7-9/9")
    print("Watch for: U and F faces should not regress")

    # Save debug images
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Save original
    cv2.imwrite(str(output_dir / "test_original.jpg"), rotated)

    # Save best CLAHE result (per-face, clip=2.0)
    best_clahe = apply_clahe_per_face(rotated.copy(), polygons, clip_limit=2.0)
    cv2.imwrite(str(output_dir / "test_clahe.jpg"), best_clahe)

    print(f"\nSaved test images to {output_dir}/test_*.jpg")

    return 0


if __name__ == "__main__":
    sys.exit(main())
