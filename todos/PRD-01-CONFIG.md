# PRD-01: Foundation & Configuration

**Status:** ✅ Complete (T1)
**Dependencies:** None
**Estimated effort:** Small

## Goal

Set up project structure, calibration config, and CLAUDE.md conventions.

## Deliverables

### 1. `config.py` - Camera calibration and color ranges

```python
# Camera configuration
CAMERA_URL = "http://192.168.1.237:8081/video"
CAMERA_DISTANCE_MM = 150
CAMERA_PITCH_DEG = 53.5   # Downward tilt
CAMERA_ROLL_DEG = -21.5   # Rightward tilt
CAMERA_ROTATION = cv2.ROTATE_90_CLOCKWISE

# Cube dimensions
CUBE_SIZE_MM = 57  # Standard 3x3

# Paths
OUTPUT_DIR = Path(__file__).parent / "output"

# HSV color ranges for detection
COLOR_RANGES = {
    'white':  {'h': (0, 180), 's': (0, 30),   'v': (200, 255)},
    'yellow': {'h': (20, 40), 's': (100, 255), 'v': (100, 255)},
    'orange': {'h': (10, 20), 's': (100, 255), 'v': (100, 255)},
    'red':    {'h': [(0, 10), (170, 180)], 's': (100, 255), 'v': (100, 255)},
    'green':  {'h': (40, 80), 's': (100, 255), 'v': (100, 255)},
    'blue':   {'h': (100, 130), 's': (100, 255), 'v': (100, 255)},
}
```

### 2. `CLAUDE.md` - Project conventions

Should include:
- Project overview (Rubik's cube CV with web debugger)
- File structure explanation
- Coding conventions (Python 3.11+, type hints, docstrings)
- How to run: capture, pipeline, server
- Testing approach
- Key libraries and their usage

### 3. `requirements.txt`

```
opencv-python>=4.8.0
numpy>=1.24.0
fastapi>=0.100.0
uvicorn>=0.23.0
watchdog>=3.0.0
kociemba>=1.2.1
```

### 4. Directory structure

```
rubik/
├── output/          # gitignored
├── static/
└── todos/
```

### 5. Update `.gitignore`

Add:
```
output/
snapshot.jpg
__pycache__/
*.pyc
.env
```

## Acceptance Criteria

- [ ] `python -c "import config"` succeeds
- [ ] CLAUDE.md exists and is comprehensive
- [ ] output/ directory exists and is gitignored
- [ ] requirements.txt lists all dependencies
- [ ] .gitignore updated

## Notes

- Color ranges are initial estimates - will need calibration
- Consider adding a calibration mode later
