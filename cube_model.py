"""Rubik's cube state representation."""
from __future__ import annotations

from datetime import datetime
from typing import Any


class CubeState:
    """Represents the state of a Rubik's cube.

    Face names follow standard notation:
    - U (Up), D (Down), L (Left), R (Right), F (Front), B (Back)

    Each face is a 3x3 grid of color letters:
    - W (White), Y (Yellow), O (Orange), R (Red), G (Green), B (Blue)
    """

    FACE_NAMES = ('U', 'D', 'L', 'R', 'F', 'B')

    # Kociemba solver expects faces in this order: U R F D L B
    KOCIEMBA_ORDER = ('U', 'R', 'F', 'D', 'L', 'B')

    # Map color letters to Kociemba face letters (center color defines face)
    # Standard orientation: W=U, Y=D, O=L, R=R, G=F, B=B
    COLOR_TO_FACE = {
        'W': 'U',
        'Y': 'D',
        'O': 'L',
        'R': 'R',
        'G': 'F',
        'B': 'B',
    }

    def __init__(self, faces: dict[str, list[list[str]] | None]):
        """Initialize cube state.

        Args:
            faces: Dict mapping face names to 3x3 color grids.
                   Use None for faces that haven't been detected.
        """
        self.faces = faces
        self.timestamp = datetime.now()
        self.confidence = 0.0

    def to_kociemba(self) -> str:
        """Convert to 54-character Kociemba solver format.

        Returns:
            54-char string in URFDLB order, or empty string if incomplete.

        The Kociemba format uses face letters (not colors):
        - Each position contains the letter of the face that color belongs to
        - Reading order: U face (row by row), R face, F face, D face, L face, B face
        """
        result = []

        for face_name in self.KOCIEMBA_ORDER:
            face = self.faces.get(face_name)
            if face is None:
                return ""  # Incomplete state

            for row in face:
                for color in row:
                    face_letter = self.COLOR_TO_FACE.get(color, '?')
                    result.append(face_letter)

        return ''.join(result)

    def to_json(self) -> dict[str, Any]:
        """Export as JSON-serializable dict.

        Returns:
            Dict with timestamp, visible_faces, faces, and confidence.
        """
        visible = [name for name, face in self.faces.items() if face is not None]

        return {
            'timestamp': self.timestamp.isoformat(),
            'visible_faces': visible,
            'faces': self.faces,
            'confidence': self.confidence,
        }

    @classmethod
    def from_detected(
        cls,
        colors: dict[str, list[list[str]]],
        confidence: float = 0.0,
    ) -> CubeState:
        """Create CubeState from CV-detected colors.

        Args:
            colors: Dict mapping face names (U, L, R, etc.) to 3x3 color grids.
            confidence: Detection confidence score (0.0 to 1.0).

        Returns:
            New CubeState instance.
        """
        # Initialize all faces as None
        faces: dict[str, list[list[str]] | None] = {
            name: None for name in cls.FACE_NAMES
        }

        # Fill in detected faces
        for face_name, grid in colors.items():
            if face_name in cls.FACE_NAMES:
                faces[face_name] = grid

        state = cls(faces)
        state.confidence = confidence
        return state

    def __repr__(self) -> str:
        visible = [name for name, face in self.faces.items() if face is not None]
        return f"CubeState(visible={visible}, confidence={self.confidence:.2f})"
