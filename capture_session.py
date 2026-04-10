"""Multi-capture session management with rotation tracking."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from cube_model import CubeState


@dataclass
class CaptureSnapshot:
    """Single capture result."""
    timestamp: float
    detected_faces: dict[str, list[list[str]]]  # face_name -> 3x3 grid
    corner: str  # e.g., "UFR" - which corner was visible


@dataclass
class Inconsistency:
    """Records when captured data conflicts with existing state."""
    face: str
    position: tuple[int, int]
    existing_color: str
    new_color: str
    source: str  # "face_overlap" or "edge_mismatch"


@dataclass
class CaptureStep:
    """Configuration for a capture step in the predefined sequence."""
    name: str
    instruction: str
    position_to_face: dict[str, str]  # Camera position (U/F/R) -> actual face
    transforms: dict[str, int]  # Face -> rotation degrees (0, 90, 180, 270)


# Predefined capture sequence: 2 captures with x2 rotation
CAPTURE_SEQUENCE = [
    CaptureStep(
        name='initial',
        instruction='Place cube with White face up, Red toward camera',
        position_to_face={'U': 'U', 'F': 'F', 'R': 'R'},
        transforms={'U': 0, 'F': 0, 'R': 0},
    ),
    CaptureStep(
        name='after_x2',
        instruction='Flip cube toward yourself (x2) - Yellow should be on top',
        position_to_face={'U': 'D', 'F': 'B', 'R': 'L'},
        transforms={'D': 180, 'B': 180, 'L': 180},
    ),
]


class CaptureSession:
    """Manages multi-capture workflow with rotation tracking.

    Tracks cube state across multiple captures, validating consistency
    by comparing overlapping stickers and adjacent edge stickers.
    Uses a predefined capture sequence (x2 rotation) for guided workflow.
    """

    # Map center sticker color to face name
    # Based on actual cube: White=U, Red=F, Blue=R (from CLAUDE.md)
    CENTER_TO_FACE = {
        'W': 'U',  # White center = Up
        'Y': 'D',  # Yellow center = Down
        'R': 'F',  # Red center = Front
        'O': 'B',  # Orange center = Back
        'B': 'R',  # Blue center = Right
        'G': 'L',  # Green center = Left
    }

    # Reverse mapping for hints
    FACE_TO_COLOR_NAME = {
        'U': 'White', 'D': 'Yellow', 'F': 'Red',
        'B': 'Orange', 'R': 'Blue', 'L': 'Green',
    }

    # Expected center colors for validation
    FACE_TO_CENTER = {
        'U': 'W', 'D': 'Y', 'F': 'R', 'B': 'O', 'R': 'B', 'L': 'G',
    }

    # Edge adjacency map: maps (face1, face2) to list of ((row1, col1), (row2, col2))
    # showing which stickers on face1 edge touch which stickers on face2 edge
    EDGE_ADJACENCIES = {
        # U face edges
        ('U', 'F'): [((2, 0), (0, 0)), ((2, 1), (0, 1)), ((2, 2), (0, 2))],
        ('U', 'R'): [((0, 2), (0, 0)), ((1, 2), (1, 0)), ((2, 2), (2, 0))],
        ('U', 'B'): [((0, 0), (0, 2)), ((0, 1), (0, 1)), ((0, 2), (0, 0))],
        ('U', 'L'): [((0, 0), (0, 2)), ((1, 0), (1, 2)), ((2, 0), (2, 2))],
        # D face edges
        ('D', 'F'): [((0, 0), (2, 0)), ((0, 1), (2, 1)), ((0, 2), (2, 2))],
        ('D', 'R'): [((0, 2), (2, 0)), ((1, 2), (2, 1)), ((2, 2), (2, 2))],
        ('D', 'B'): [((2, 0), (2, 2)), ((2, 1), (2, 1)), ((2, 2), (2, 0))],
        ('D', 'L'): [((0, 0), (2, 2)), ((1, 0), (2, 1)), ((2, 0), (2, 0))],
        # F face edges (non-U/D)
        ('F', 'R'): [((0, 2), (0, 0)), ((1, 2), (1, 0)), ((2, 2), (2, 0))],
        ('F', 'L'): [((0, 0), (0, 2)), ((1, 0), (1, 2)), ((2, 0), (2, 2))],
        # B face edges (non-U/D)
        ('B', 'R'): [((0, 0), (0, 2)), ((1, 0), (1, 2)), ((2, 0), (2, 2))],
        ('B', 'L'): [((0, 2), (0, 0)), ((1, 2), (1, 0)), ((2, 2), (2, 0))],
    }

    # Capture sequence
    SEQUENCE = CAPTURE_SEQUENCE

    def __init__(self):
        self.snapshots: list[CaptureSnapshot] = []
        self.global_state: dict[str, list[list[str]] | None] = {
            f: None for f in 'UDFBRL'
        }
        self.global_confidences: dict[str, list[list[float]] | None] = {
            f: None for f in 'UDFBRL'
        }
        self.inconsistencies: list[Inconsistency] = []
        self.current_step = 0

    def get_current_step(self) -> CaptureStep | None:
        """Get the current step in the capture sequence."""
        if self.current_step >= len(self.SEQUENCE):
            return None
        return self.SEQUENCE[self.current_step]

    @staticmethod
    def transform_grid(grid: list[list[str]], rotation: int) -> list[list[str]]:
        """Transform a 3x3 grid based on rotation degrees (clockwise).

        Args:
            grid: 3x3 color grid
            rotation: Degrees of rotation (0, 90, 180, 270)

        Returns:
            Transformed 3x3 grid
        """
        if rotation == 0:
            return [row[:] for row in grid]  # Deep copy
        elif rotation == 90:
            return [[grid[2-j][i] for j in range(3)] for i in range(3)]
        elif rotation == 180:
            return [[grid[2-i][2-j] for j in range(3)] for i in range(3)]
        elif rotation == 270:
            return [[grid[j][2-i] for j in range(3)] for i in range(3)]
        return [row[:] for row in grid]

    def validate_step_centers(self, detected: dict[str, list[list[str]]]) -> tuple[bool, str]:
        """Validate that detected centers match expected faces for current step.

        Args:
            detected: Dict with camera position keys (U/F/R) and 3x3 grids

        Returns:
            (is_valid, message)
        """
        step = self.get_current_step()
        if step is None:
            return True, "All steps complete"

        for camera_pos, actual_face in step.position_to_face.items():
            if camera_pos not in detected:
                continue
            grid = detected[camera_pos]
            if not grid or len(grid) < 3 or len(grid[1]) < 3:
                continue
            center = grid[1][1]
            expected = self.FACE_TO_CENTER.get(actual_face)

            if center != expected and center != '?':
                expected_name = self.FACE_TO_COLOR_NAME.get(actual_face, actual_face)
                return False, f"Expected {expected_name} ({expected}) center, got {center}. Check rotation."

        return True, "OK"

    def identify_faces(self, positional_grids: dict[str, list[list[str]]]) -> dict[str, list[list[str]]]:
        """Map positional face names to actual face names by center color.

        Args:
            positional_grids: Dict with keys like 'U', 'F', 'R' (positional)
                             mapping to 3x3 color grids.

        Returns:
            Dict with keys as actual face names based on center sticker color.
        """
        result = {}
        for _, grid in positional_grids.items():
            center_color = grid[1][1]
            actual_face = self.CENTER_TO_FACE.get(center_color)
            if actual_face:
                result[actual_face] = grid
            # If center color unknown (e.g., '?'), skip this face
        return result

    def validate_consistency(self, new_faces: dict[str, list[list[str]]]) -> list[Inconsistency]:
        """Check new capture against existing state for inconsistencies.

        Args:
            new_faces: Dict mapping face names to 3x3 grids (already identified).

        Returns:
            List of inconsistencies found.
        """
        issues = []

        for face_name, new_grid in new_faces.items():
            existing_grid = self.global_state.get(face_name)

            # Check face overlap - same face captured before
            if existing_grid is not None:
                for row in range(3):
                    for col in range(3):
                        if existing_grid[row][col] != new_grid[row][col]:
                            # Allow if either is unknown
                            if existing_grid[row][col] != '?' and new_grid[row][col] != '?':
                                issues.append(Inconsistency(
                                    face=face_name,
                                    position=(row, col),
                                    existing_color=existing_grid[row][col],
                                    new_color=new_grid[row][col],
                                    source="face_overlap"
                                ))

            # Check edge consistency with adjacent captured faces
            for (f1, f2), adjacencies in self.EDGE_ADJACENCIES.items():
                if face_name == f1 and self.global_state.get(f2) is not None:
                    other_grid = self.global_state[f2]
                    for (pos1, pos2) in adjacencies:
                        color1 = new_grid[pos1[0]][pos1[1]]
                        color2 = other_grid[pos2[0]][pos2[1]]
                        # Edge stickers should have consistent colors
                        # (This checks the relationship, not equality)
                        # For now, we just log if both are captured
                elif face_name == f2 and self.global_state.get(f1) is not None:
                    # TODO(PRD-07): Implement edge consistency validation
                    # Requires domain knowledge about valid cube states.
                    # See EDGE_ADJACENCIES dict for sticker pair mappings.
                    pass

        return issues

    def process_capture(self, detected: dict[str, list[list[str]]]) -> dict[str, Any]:
        """Process new capture, validate, and merge into global state.

        Args:
            detected: Dict from pipeline with positional face names and grids.

        Returns:
            Result dict with capture info, progress, and any inconsistencies.
        """
        step = self.get_current_step()

        # 1. Identify faces by center color
        identified_faces = self.identify_faces(detected)

        if not identified_faces:
            return {
                'success': False,
                'error': 'No faces could be identified by center color',
                'detected_faces': [],
                'new_faces': [],
                'captured': self.get_captured_faces(),
                'missing': self.get_missing_faces(),
                'progress': {'count': len(self.get_captured_faces()), 'total': 6},
                'is_complete': self.is_complete,
                'inconsistencies': [],
                'hint': self.get_rotation_hint(),
                'current_step': self.current_step,
                'total_steps': len(self.SEQUENCE),
            }

        # 2. Validate centers match expected step (informational, don't block)
        step_valid, step_msg = self.validate_step_centers(detected)
        validation_warning = None if step_valid else step_msg

        # 3. Determine corner (sorted face names)
        corner = ''.join(sorted(identified_faces.keys()))

        # 4. Validate against existing state
        new_inconsistencies = self.validate_consistency(identified_faces)
        self.inconsistencies.extend(new_inconsistencies)

        # 5. Record snapshot
        snapshot = CaptureSnapshot(
            timestamp=time.time(),
            detected_faces=identified_faces,
            corner=corner,
        )
        self.snapshots.append(snapshot)

        # 6. Merge into global state (new faces only, keep existing on conflict)
        new_faces = []
        for face_name, grid in identified_faces.items():
            if self.global_state[face_name] is None:
                self.global_state[face_name] = grid
                new_faces.append(face_name)
            # If face already exists and has inconsistencies, keep existing

        # 7. Advance step if we captured expected faces
        step_completed = None
        if step is not None and new_faces:
            expected_faces = set(step.position_to_face.values())
            captured_faces = set(self.get_captured_faces())
            if expected_faces.issubset(captured_faces):
                step_completed = step.name
                self.current_step += 1

        # 8. Build result
        result = {
            'success': True,
            'detected_faces': list(identified_faces.keys()),
            'new_faces': new_faces,
            'captured': self.get_captured_faces(),
            'missing': self.get_missing_faces(),
            'progress': {'count': len(self.get_captured_faces()), 'total': 6},
            'is_complete': self.is_complete,
            'inconsistencies': [
                {
                    'face': i.face,
                    'position': i.position,
                    'existing': i.existing_color,
                    'new': i.new_color,
                    'source': i.source,
                }
                for i in new_inconsistencies
            ],
            'hint': self.get_rotation_hint(),
            'current_step': self.current_step,
            'total_steps': len(self.SEQUENCE),
            'step_completed': step_completed,
        }

        if validation_warning:
            result['validation_warning'] = validation_warning

        return result

    def get_captured_faces(self) -> list[str]:
        """Return list of captured face names."""
        return [f for f, grid in self.global_state.items() if grid is not None]

    def get_missing_faces(self) -> list[str]:
        """Return list of uncaptured face names."""
        return [f for f, grid in self.global_state.items() if grid is None]

    def get_rotation_hint(self) -> str:
        """Generate hint text for user about which faces to show next."""
        # Use sequence-based hints
        step = self.get_current_step()
        if step is not None:
            return step.instruction

        missing = self.get_missing_faces()
        if not missing:
            return "All faces captured! Cube state is complete."

        # Fallback for non-sequence mode
        hints = [f"{self.FACE_TO_COLOR_NAME[f]} ({f})" for f in missing[:3]]
        return f"Rotate to show {', '.join(hints)}"

    @property
    def is_complete(self) -> bool:
        """True if all 6 faces have been captured."""
        return all(grid is not None for grid in self.global_state.values())

    def to_cube_state(self) -> CubeState:
        """Convert current global state to CubeState for 3D visualization."""
        return CubeState.from_detected(
            {k: v for k, v in self.global_state.items() if v is not None},
            confidence=len(self.get_captured_faces()) / 6.0
        )

    def to_json(self) -> dict[str, Any]:
        """Export session state as JSON-serializable dict."""
        step = self.get_current_step()
        return {
            'captured': self.get_captured_faces(),
            'missing': self.get_missing_faces(),
            'progress': {'count': len(self.get_captured_faces()), 'total': 6},
            'is_complete': self.is_complete,
            'faces': self.global_state,
            'snapshot_count': len(self.snapshots),
            'inconsistencies': [
                {
                    'face': i.face,
                    'position': i.position,
                    'existing': i.existing_color,
                    'new': i.new_color,
                }
                for i in self.inconsistencies
            ],
            'hint': self.get_rotation_hint(),
            'current_step': self.current_step,
            'total_steps': len(self.SEQUENCE),
            'step_name': step.name if step else None,
        }

    def reset(self):
        """Clear all captured state."""
        self.snapshots = []
        self.global_state = {f: None for f in 'UDFBRL'}
        self.global_confidences = {f: None for f in 'UDFBRL'}
        self.inconsistencies = []
        self.current_step = 0
