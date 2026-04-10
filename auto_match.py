"""Auto-match camera ROIs to 3D cube faces based on center sticker colors.

Computes the mapping from camera ROI positions (U/F/R in image space) to
actual cube faces (U/D/L/R/F/B based on center colors), plus the rotation
transform needed to align the detected grid with the 3D model.
"""

from typing import Any


# Map center sticker color to face name (standard Rubik's cube color scheme)
CENTER_TO_FACE = {
    'W': 'U',  # White center = Up
    'Y': 'D',  # Yellow center = Down
    'R': 'F',  # Red center = Front
    'O': 'B',  # Orange center = Back
    'B': 'R',  # Blue center = Right
    'G': 'L',  # Green center = Left
}

# Reverse mapping for getting expected center color from face
FACE_TO_CENTER = {v: k for k, v in CENTER_TO_FACE.items()}

# Corner positions on each face for all 8 cube corners
# Each entry maps a set of 3 visible faces to the expected corner position on each face
# Position (row, col) where the corner sticker appears in standard orientation
CORNER_POSITIONS = {
    frozenset(['U', 'F', 'R']): {'U': (2, 2), 'F': (0, 2), 'R': (0, 0)},
    frozenset(['U', 'F', 'L']): {'U': (2, 0), 'F': (0, 0), 'L': (0, 2)},
    frozenset(['U', 'B', 'R']): {'U': (0, 2), 'B': (0, 0), 'R': (0, 2)},
    frozenset(['U', 'B', 'L']): {'U': (0, 0), 'B': (0, 2), 'L': (0, 0)},
    frozenset(['D', 'F', 'R']): {'D': (0, 2), 'F': (2, 2), 'R': (2, 0)},
    frozenset(['D', 'F', 'L']): {'D': (0, 0), 'F': (2, 0), 'L': (2, 2)},
    frozenset(['D', 'B', 'R']): {'D': (2, 2), 'B': (2, 0), 'R': (2, 2)},
    frozenset(['D', 'B', 'L']): {'D': (2, 0), 'B': (2, 2), 'L': (2, 0)},
}

# Corner positions cycle with 90-degree rotations (clockwise)
CORNER_CYCLE = [(0, 0), (0, 2), (2, 2), (2, 0)]


def compute_rotation(detected_pos: tuple[int, int] | None,
                     expected_pos: tuple[int, int]) -> int:
    """Compute rotation (0, 90, 180, 270) degrees clockwise.

    Args:
        detected_pos: Where the corner was detected (row, col), or None
        expected_pos: Where the corner should be (row, col)

    Returns:
        Rotation in degrees (0, 90, 180, 270)
    """
    if detected_pos is None:
        return 0

    try:
        detected_idx = CORNER_CYCLE.index(tuple(detected_pos))
        expected_idx = CORNER_CYCLE.index(tuple(expected_pos))
        return ((expected_idx - detected_idx) % 4) * 90
    except ValueError:
        return 0


def find_corner_in_grid(grid: list[list[str]],
                        this_face: str,
                        all_faces: list[str]) -> tuple[int, int] | None:
    """Find which corner position in the grid contains the corner sticker.

    The corner sticker is identified by having a color that matches
    one of the OTHER visible faces' center colors.

    Args:
        grid: 3x3 color grid for this face
        this_face: Name of this face (e.g., 'U')
        all_faces: List of all visible face names

    Returns:
        (row, col) position of corner sticker, or None if not found
    """
    # Get colors of adjacent faces at the corner
    other_faces = [f for f in all_faces if f != this_face]
    adjacent_colors = {FACE_TO_CENTER.get(f) for f in other_faces}

    # Check each corner position
    for pos in CORNER_CYCLE:
        row, col = pos
        color = grid[row][col]
        # The corner has stickers from 3 faces; check if this matches an adjacent face
        if color in adjacent_colors:
            return pos

    return None


def compute_auto_match(detected_grids: dict[str, list[list[str]]]) -> dict[str, Any]:
    """Compute face mappings and rotations from detected camera ROI grids.

    Args:
        detected_grids: Dict mapping camera ROI names ('U', 'F', 'R') to 3x3 color grids

    Returns:
        {
            'valid': True/False,
            'roi_to_face': {'U': 'R', 'F': 'F', 'R': 'U'},  # camera ROI -> actual face
            'face_rotations': {'R': 90, 'F': 0, 'U': 270},  # actual face -> rotation
            'detected_corner': 'FRU',  # sorted face names
            'error': None or error message
        }
    """
    if not detected_grids:
        return {
            'valid': False,
            'roi_to_face': {},
            'face_rotations': {},
            'detected_corner': None,
            'error': 'No grids provided',
        }

    # Step 1: Map ROIs to actual faces using center colors
    roi_to_face = {}
    for roi_name, grid in detected_grids.items():
        if not grid or len(grid) < 3 or len(grid[1]) < 3:
            continue
        center_color = grid[1][1]
        if center_color == '?' or center_color not in CENTER_TO_FACE:
            return {
                'valid': False,
                'roi_to_face': {},
                'face_rotations': {},
                'detected_corner': None,
                'error': f'Unknown center color "{center_color}" in ROI {roi_name}',
            }
        roi_to_face[roi_name] = CENTER_TO_FACE[center_color]

    # Check for duplicate faces (shouldn't see same face twice)
    if len(set(roi_to_face.values())) != len(roi_to_face):
        return {
            'valid': False,
            'roi_to_face': roi_to_face,
            'face_rotations': {},
            'detected_corner': None,
            'error': 'Duplicate face detected - check cube placement',
        }

    # Step 2: Identify which corner we're seeing
    actual_faces = list(roi_to_face.values())
    face_set = frozenset(actual_faces)
    expected_positions = CORNER_POSITIONS.get(face_set)

    if expected_positions is None:
        return {
            'valid': False,
            'roi_to_face': roi_to_face,
            'face_rotations': {},
            'detected_corner': None,
            'error': f'Invalid face combination: {sorted(actual_faces)}',
        }

    # Step 3: Compute rotation for each face based on corner position
    face_rotations = {}
    for roi_name, grid in detected_grids.items():
        actual_face = roi_to_face.get(roi_name)
        if actual_face and actual_face in expected_positions:
            expected_corner_pos = expected_positions[actual_face]
            detected_corner_pos = find_corner_in_grid(grid, actual_face, actual_faces)
            rotation = compute_rotation(detected_corner_pos, expected_corner_pos)
            face_rotations[actual_face] = rotation

    corner_name = ''.join(sorted(actual_faces))

    return {
        'valid': True,
        'roi_to_face': roi_to_face,
        'face_rotations': face_rotations,
        'detected_corner': corner_name,
        'error': None,
    }
