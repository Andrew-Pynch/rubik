from enum import Enum

from colors import Color


class Face(Enum):
    FRONT = 0
    RIGHT = 1
    BACK = 2
    LEFT = 3
    TOP = 4
    BOTTOM = 5

    def __str__(self):
        return self.name

FACE_OFFSETS = {
    Face.FRONT: (0, 0),
    Face.TOP: (-4, 0),
    Face.BOTTOM: (4, 0),
    Face.LEFT: (0, -4),
    Face.RIGHT: (0, 4),
    Face.BACK: (0, 8)
}

SOLVED_FACES = {
    Face.FRONT: [
        [Color.GREEN, Color.GREEN, Color.GREEN],
        [Color.GREEN, Color.GREEN, Color.GREEN],
        [Color.GREEN, Color.GREEN, Color.GREEN],
    ],
    Face.BACK: [
        [Color.BLUE, Color.BLUE, Color.BLUE],
        [Color.BLUE, Color.BLUE, Color.BLUE],
        [Color.BLUE, Color.BLUE, Color.BLUE],
    ],
    Face.LEFT: [
        [Color.ORANGE, Color.ORANGE, Color.ORANGE],
        [Color.ORANGE, Color.ORANGE, Color.ORANGE],
        [Color.ORANGE, Color.ORANGE, Color.ORANGE],
    ],
    Face.RIGHT: [
        [Color.RED, Color.RED, Color.RED],
        [Color.RED, Color.RED, Color.RED],
        [Color.RED, Color.RED, Color.RED],
    ],
    Face.TOP: [
        [Color.WHITE, Color.WHITE, Color.WHITE],
        [Color.WHITE, Color.WHITE, Color.WHITE],
        [Color.WHITE, Color.WHITE, Color.WHITE],
    ],
    Face.BOTTOM: [
        [Color.YELLOW, Color.YELLOW, Color.YELLOW],
        [Color.YELLOW, Color.YELLOW, Color.YELLOW],
        [Color.YELLOW, Color.YELLOW, Color.YELLOW],
    ],
}
