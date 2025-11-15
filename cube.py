from enum import Enum
from typing import List

class Face(Enum):
    FRONT = 0
    RIGHT = 1
    BACK = 2
    LEFT = 3
    TOP = 4
    BOTTOM = 5

    def __str__(self):
        return self.name

class Color(Enum):
    WHITE = 1
    YELLOW = 2
    RED = 3
    ORANGE = 4
    GREEN = 5
    BLUE = 6

    def __str__(self):
        # show a colored block for each sticker
        code = ANSI_COLOR_CODES[self]
        symbol = SYMBOLS[self]
        reset = ANSI_RESET
        return f"{code}{symbol}{reset}"


ANSI_RESET = "\033[0m"

ANSI_COLOR_CODES = {
    Color.WHITE:  "\033[97m",  # bright white
    Color.YELLOW: "\033[93m",  # bright yellow
    Color.RED:    "\033[91m",  # bright red
    Color.ORANGE: "\033[33m",  # normal yellow-ish
    Color.GREEN:  "\033[92m",  # bright green
    Color.BLUE:   "\033[94m",  # bright blue
}

SYMBOLS = {
    Color.WHITE:  "■",
    Color.YELLOW: "■",
    Color.RED:    "■",
    Color.ORANGE: "■",
    Color.GREEN:  "■",
    Color.BLUE:   "■",
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

WORLD_WIDTH = 30
WORLD_HEIGHT = 30

class World:
    def __init__(self):
        self.width = WORLD_WIDTH
        self.height = WORLD_HEIGHT
        self.grid = [" " for _ in range(WORLD_WIDTH * WORLD_HEIGHT)]

class CubeState:
    def __init__(self):
        self.faces = self.init_faces(SOLVED_FACES)

    def init_faces(self, initial_faces):
        faces = {}

        # Loop over each face (FRONT, BACK, etc.)
        for face in initial_faces:
            original_grid = initial_faces[face]

            # make a new 3x3 grid for this face
            new_grid = []

            # Loop over each row of the original grid
            for row in original_grid:
                new_row = []
                for color in row:
                    new_row.append(color)
                new_grid.append(new_row)

            # after copying all rows, store the new grid
            faces[face] = new_grid

        return faces

    def render_face(self, face: Face):
        for row in self.faces[face]:
            for cell in row:
                print(cell, end=" ")
            print("")

# init 1 cube and print the front face
cube = CubeState()
cube.render_face(Face.FRONT)
