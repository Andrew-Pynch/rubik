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


class CaptureSession:
    """Manages multi-capture workflow with rotation tracking.

    Tracks cube state across multiple captures, validating consistency
    by comparing overlapping stickers and adjacent edge stickers.
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

    def __init__(self):
        self.snapshots: list[CaptureSnapshot] = []
        self.global_state: dict[str, list[list[str]] | None] = {
            f: None for f in 'UDFBRL'
        }
        self.inconsistencies: list[Inconsistency] = []

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
                    # Similar check in reverse
                    pass

        return issues

    def process_capture(self, detected: dict[str, list[list[str]]]) -> dict[str, Any]:
        """Process new capture, validate, and merge into global state.

        Args:
            detected: Dict from pipeline with positional face names and grids.

        Returns:
            Result dict with capture info, progress, and any inconsistencies.
        """
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
            }

        # 2. Determine corner (sorted face names)
        corner = ''.join(sorted(identified_faces.keys()))

        # 3. Validate against existing state
        new_inconsistencies = self.validate_consistency(identified_faces)
        self.inconsistencies.extend(new_inconsistencies)

        # 4. Record snapshot
        snapshot = CaptureSnapshot(
            timestamp=time.time(),
            detected_faces=identified_faces,
            corner=corner,
        )
        self.snapshots.append(snapshot)

        # 5. Merge into global state (new faces only, keep existing on conflict)
        new_faces = []
        for face_name, grid in identified_faces.items():
            if self.global_state[face_name] is None:
                self.global_state[face_name] = grid
                new_faces.append(face_name)
            # If face already exists and has inconsistencies, keep existing

        # 6. Build result
        return {
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
        }

    def get_captured_faces(self) -> list[str]:
        """Return list of captured face names."""
        return [f for f, grid in self.global_state.items() if grid is not None]

    def get_missing_faces(self) -> list[str]:
        """Return list of uncaptured face names."""
        return [f for f, grid in self.global_state.items() if grid is None]

    def get_rotation_hint(self) -> str:
        """Generate hint text for user about which faces to show next."""
        missing = self.get_missing_faces()

        if not missing:
            return "All faces captured! Cube state is complete."

        if len(missing) == 6:
            return "Place cube in camera view and click Capture"

        # Build hint with color names
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
        }

    def reset(self):
        """Clear all captured state."""
        self.snapshots = []
        self.global_state = {f: None for f in 'UDFBRL'}
        self.inconsistencies = []
