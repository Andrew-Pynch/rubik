"""Logging configuration for Rubik's Cube CV pipeline."""
import logging
import sys


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Set up and return a logger for the rubik application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("rubik")
    logger.setLevel(getattr(logging, level.upper()))

    # Avoid duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S"
        ))
        logger.addHandler(handler)

    return logger


logger = setup_logging()
