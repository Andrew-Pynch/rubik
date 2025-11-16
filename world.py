WORLD_WIDTH = 45
WORLD_HEIGHT = 40


class World:
    def __init__(self):
        self.width = WORLD_WIDTH
        self.height = WORLD_HEIGHT
        self.grid = [" " for _ in range(self.width * self.height)]

    def index(self, row: int, col: int) -> int: 
        """Conver (row, col) to 1D index."""
        return row * self.width + col

    def set_cell(self, row: int, col: int, char: str) -> None:
        """Set a single cell if it's inside the bounds."""
        if 0 <= row < self.height and 0 <= col < self.width:
            self.grid[self.index(row, col)] = char

    def get_cell(self, row: int, col: int) -> str:
        """Get a single cell (or a space if its out of bounds)."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.grid[self.index(row, col)]
        return " "

    def render(self) -> None:
        """Print the whole world."""
        for row in range(self.height):
            start = row * self.width
            end = start + self.width
            line = "".join(self.grid[start:end])
            print(line)


