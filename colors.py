from enum import Enum


class Color(Enum):
    WHITE = 1
    YELLOW = 2
    RED = 3
    ORANGE = 4
    GREEN = 5
    BLUE = 6

    def __str__(self):
        code = ANSI_COLOR_CODES[self]
        symbol = SYMBOLS[self]
        return f"{code}{symbol}{ANSI_RESET}"


ANSI_RESET = "\033[0m"

ANSI_COLOR_CODES = {
    Color.WHITE:  "\033[38;2;255;255;255m",
    Color.YELLOW: "\033[38;2;255;255;0m",
    Color.RED:    "\033[38;2;255;80;80m",
    Color.ORANGE: "\033[38;2;255;165;0m",
    Color.GREEN:  "\033[38;2;0;255;0m",
    Color.BLUE:   "\033[38;2;80;160;255m",
}

SYMBOLS = {
    Color.WHITE: "■",
    Color.YELLOW: "■",
    Color.RED: "■",
    Color.ORANGE: "■",
    Color.GREEN: "■",
    Color.BLUE: "■",
}
