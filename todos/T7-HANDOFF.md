# T7 Handoff - PRD-06 Technical Debt Implementation

## Mission

Implement all 11 items from **PRD-06: Technical Debt & Bug Fixes**. Work through items in priority order (HIGH → MEDIUM → LOW). Estimated time: ~3 hours.

## Quick Start

```bash
cd ~/personal/rubik
./run.sh  # Verify server works before starting
```

## Context

This is a Rubik's Cube CV project with:
- FastAPI server (`server.py`) serving MJPEG stream and WebSocket updates
- OpenCV pipeline (`pipeline.py`, `detection.py`) for color detection
- Three.js 3D visualization (`static/cube3d.js`)
- Multi-capture workflow (`capture_session.py`)

See `CLAUDE.md` for full documentation.

---

## Tasks (in order)

### HIGH PRIORITY (Do First)

#### 1. Fix Directory Traversal Vulnerability
**File:** `server.py` around line 149-164

Find the `/output/{filename}` endpoint and add path sanitization:
```python
@app.get("/output/{filename}")
async def get_output_file(filename: str):
    # Sanitize filename - strip path components
    safe_filename = Path(filename).name
    file_path = (OUTPUT_DIR / safe_filename).resolve()

    # Verify resolved path is within OUTPUT_DIR
    if not str(file_path).startswith(str(OUTPUT_DIR.resolve())):
        return {"error": "Invalid filename"}

    if file_path.exists() and file_path.is_file():
        # ... keep existing code
```

**Test:** `curl http://localhost:8000/output/../config.py` should return error, not file contents.

#### 2. Fix Race Condition in Stream Buffer
**File:** `server.py` around line 621-623

Find where `_stream_frame` is assigned and move copies outside the lock:
```python
# Before (bad):
with _stream_lock:
    _stream_frame = (bgr.copy(), hsv.copy())

# After (good):
bgr_copy = bgr.copy()
hsv_copy = hsv.copy()
with _stream_lock:
    _stream_frame = (bgr_copy, hsv_copy)
```

#### 3. Add Environment Variable for Camera URL
**File:** `config.py` line 7

Change:
```python
CAMERA_URL = "http://192.168.1.102:8081/video"
```
To:
```python
import os
CAMERA_URL = os.environ.get("RUBIK_CAMERA_URL", "http://192.168.1.102:8081/video")
```

**Also create** `.env.example`:
```
# Rubik's Cube CV Configuration
RUBIK_CAMERA_URL=http://192.168.1.102:8081/video
```

---

### MEDIUM PRIORITY

#### 4. Remove Code Duplication
**File:** `experiments/test_lighting_normalization.py`

Find duplicated `order_polygon_corners()` and `perspective_grid_point()` functions (around lines 146-184) and replace with imports:
```python
from pipeline import order_polygon_corners, perspective_grid_point
```
Delete the local function definitions.

#### 5. Add Logging Framework
**Create new file:** `logging_config.py`
```python
"""Logging configuration for Rubik's Cube CV pipeline."""
import logging
import sys

def setup_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("rubik")
    logger.setLevel(getattr(logging, level.upper()))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(handler)

    return logger

logger = setup_logging()
```

**Then update** `server.py` and `pipeline.py`:
- Add `from logging_config import logger` at top
- Replace all `print(...)` with `logger.info(...)` or `logger.debug(...)`

#### 6. Move Magic Numbers to Config
**File:** `config.py` - Add at end:
```python
# Detection sampling configuration
DETECTION_SAMPLING = {
    'region_size': 30,
    'grid_points': 5,
    'spread_normalization': 36.0,
    'histogram_min_coverage': 0.30,
    'low_confidence_threshold': 0.25,
    'min_samples_required': 3,
}
```

**File:** `detection.py` - Update functions to use config values:
```python
from config import DETECTION_SAMPLING

# Replace hardcoded values like region_size=30 with:
# DETECTION_SAMPLING['region_size']
```

#### 7. Legacy detect.py Already Moved
**SKIP** - Already completed. `detect.py` was moved to `experiments/legacy_detect.py` in planning session.

---

### LOW PRIORITY

#### 8. Document Edge Validation Stub
**File:** `capture_session.py` around line 224-235

Find the `pass` statement in edge validation and add TODO comment:
```python
# TODO(PRD-07): Implement edge consistency validation
# Requires domain knowledge about valid cube states.
# See EDGE_ADJACENCIES dict for sticker pair mappings.
pass
```

#### 9. Document Global State
**File:** `server.py` around lines 36-47

Add comment block above globals:
```python
# ==============================================================================
# Global State (Future: Refactor to Dependency Injection)
# ==============================================================================
# These globals manage server state across requests. For production:
# - Consider using FastAPI Depends() for dependency injection
# - Create an AppState class to encapsulate all state
# - Use Starlette's State object on app instance
# ==============================================================================
connected_clients: Set[WebSocket] = set()
# ... rest of globals
```

#### 10. Add Stream Generator Cleanup
**File:** `server.py` - Find `generate_stream_frames()` function

Wrap in try/except:
```python
def generate_stream_frames():
    global _stream_frame
    from pipeline import capture_frame, preprocess, process_frame_for_stream

    try:
        while True:
            # ... existing loop code ...
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    except GeneratorExit:
        # Client disconnected, clean up
        with _stream_lock:
            _stream_frame = None
        logger.info("Stream client disconnected, cleaned up frame buffer")
```

#### 11. Fix NOP Functions in cube3d.js
**File:** `static/cube3d.js` around lines 637-649

Find stub functions and make them throw:
```javascript
export function showFaceLabels(faceName) {
    throw new Error('showFaceLabels not implemented in dual cube mode');
}

export function enableFaceClickMode(callback) {
    throw new Error('enableFaceClickMode not implemented in dual cube mode');
}

export function disableFaceClickMode() {
    // No-op: Face click mode not supported in dual cube mode
}
```

---

## Verification Checklist

After completing all tasks:

- [ ] `./run.sh` starts server without errors
- [ ] `curl http://localhost:8000/output/../config.py` returns error
- [ ] `curl http://localhost:8000/output/state.json` works normally
- [ ] Stream at http://localhost:8000 works
- [ ] No `print()` statements remain in server.py/pipeline.py (use `grep -n "print(" server.py pipeline.py`)
- [ ] `.env.example` exists with RUBIK_CAMERA_URL
- [ ] `RUBIK_CAMERA_URL=http://test:8080/video ./run.sh` uses custom URL (check logs)

## Files Summary

| Action | File |
|--------|------|
| Modify | `server.py` (security fix, race condition, generator cleanup, logging, globals doc) |
| Modify | `config.py` (env var, DETECTION_SAMPLING) |
| Modify | `detection.py` (use DETECTION_SAMPLING) |
| Modify | `capture_session.py` (TODO comment) |
| Modify | `static/cube3d.js` (NOP functions) |
| Modify | `experiments/test_lighting_normalization.py` (remove duplication) |
| Create | `logging_config.py` |
| Create | `.env.example` |

## Next Session

After completing PRD-06, the next agent should work on **PRD-07: Complete Existing Features**:
1. Fix 3D mapping mismatch
2. Implement edge validation
3. Integrate Kociemba solver

See `todos/PRD-07-FEATURES-P1.md` for details.
