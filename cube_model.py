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

    Each face also has a 3x3 grid of confidence scores (0.0-1.0).
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

    def __init__(
        self,
        faces: dict[str, list[list[str]] | None],
        face_confidences: dict[str, list[list[float]] | None] | None = None,
    ):
        """Initialize cube state.

        Args:
            faces: Dict mapping face names to 3x3 color grids.
                   Use None for faces that haven't been detected.
            face_confidences: Dict mapping face names to 3x3 confidence grids.
                   Use None for faces without confidence data.
        """
        self.faces = faces
        self.face_confidences = face_confidences or {name: None for name in self.FACE_NAMES}
        self.timestamp = datetime.now()
        self.confidence = 0.0  # Overall detection confidence

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
            Dict with timestamp, visible_faces, faces, face_confidences,
            confidence, and low_confidence_stickers.
        """
        visible = [name for name, face in self.faces.items() if face is not None]

        # Convert face_confidences to plain Python floats for JSON serialization
        serializable_confidences: dict[str, list[list[float]] | None] = {}
        for face_name in self.FACE_NAMES:
            conf_grid = self.face_confidences.get(face_name)
            if conf_grid is not None:
                serializable_confidences[face_name] = [
                    [float(c) for c in row] for row in conf_grid
                ]
            else:
                serializable_confidences[face_name] = None

        # Find low-confidence stickers for UI highlighting
        low_confidence_stickers = []
        for face_name in visible:
            face = self.faces.get(face_name)
            face_conf = self.face_confidences.get(face_name) if self.face_confidences else None

            if face and face_conf:
                for row in range(3):
                    for col in range(3):
                        conf = float(face_conf[row][col])
                        if conf < 0.5:  # Low confidence threshold
                            low_confidence_stickers.append({
                                'face': face_name,
                                'row': row,
                                'col': col,
                                'color': face[row][col],
                                'confidence': round(conf, 3),
                            })

        return {
            'timestamp': self.timestamp.isoformat(),
            'visible_faces': visible,
            'faces': self.faces,
            'face_confidences': serializable_confidences,
            'confidence': self.confidence,
            'low_confidence_stickers': low_confidence_stickers,
        }

    @classmethod
    def from_detected(
        cls,
        colors: dict[str, list[list[str]]],
        confidence: float = 0.0,
        confidences: dict[str, list[list[float]]] | None = None,
    ) -> CubeState:
        """Create CubeState from CV-detected colors.

        Args:
            colors: Dict mapping face names (U, L, R, etc.) to 3x3 color grids.
            confidence: Overall detection confidence score (0.0 to 1.0).
            confidences: Dict mapping face names to 3x3 confidence grids.

        Returns:
            New CubeState instance.
        """
        # Initialize all faces as None
        faces: dict[str, list[list[str]] | None] = {
            name: None for name in cls.FACE_NAMES
        }

        # Initialize all face confidences as None
        face_confidences: dict[str, list[list[float]] | None] = {
            name: None for name in cls.FACE_NAMES
        }

        # Fill in detected faces
        for face_name, grid in colors.items():
            if face_name in cls.FACE_NAMES:
                faces[face_name] = grid

        # Fill in confidence grids if provided
        if confidences:
            for face_name, conf_grid in confidences.items():
                if face_name in cls.FACE_NAMES:
                    face_confidences[face_name] = conf_grid

        state = cls(faces, face_confidences)
        state.confidence = confidence
        return state

    def __repr__(self) -> str:
        visible = [name for name, face in self.faces.items() if face is not None]
        return f"CubeState(visible={visible}, confidence={self.confidence:.2f})"
