# PRD-06: Technical Debt & Bug Fixes

**Status:** Pending
**Dependencies:** None (can be implemented incrementally)
**Estimated effort:** ~3 hours total

## Overview

This PRD addresses accumulated technical debt, security vulnerabilities, and code quality issues identified during development phases T1-T6. Issues are prioritized by severity (security/stability, code quality, maintainability) to enable incremental resolution.

---

## HIGH PRIORITY - Security/Stability

### 1. Directory Traversal Vulnerability

**Location:** `server.py:149-164`
**Severity:** HIGH - Security vulnerability

**Issue:** The `/output/{filename}` endpoint directly joins user-provided filename with OUTPUT_DIR without path validation. An attacker could access arbitrary files using path traversal sequences like `../../../etc/passwd`.

**Current Code:**
```python
@app.get("/output/{filename}")
async def get_output_file(filename: str):
    file_path = OUTPUT_DIR / filename  # VULNERABLE
    if file_path.exists() and file_path.is_file():
        # ...
```

**Fix:**
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
        # ... existing code
```

**Estimated Effort:** 15 minutes

---

### 2. Race Condition in Stream Frame Buffer

**Location:** `server.py:621-623`
**Severity:** HIGH - Data consistency

**Issue:** Two separate copy operations without atomicity. Should create copies before acquiring lock.

**Current Code:**
```python
with _stream_lock:
    _stream_frame = (bgr.copy(), hsv.copy())  # Two non-atomic copies
```

**Fix:**
```python
# Create copies before acquiring lock
bgr_copy = bgr.copy()
hsv_copy = hsv.copy()

# Atomic assignment under lock
with _stream_lock:
    _stream_frame = (bgr_copy, hsv_copy)
```

**Estimated Effort:** 10 minutes

---

### 3. Hardcoded Camera IP Address

**Location:** `config.py:7`
**Severity:** HIGH - Deployment/portability

**Issue:** Camera URL is hardcoded, requiring code changes to switch cameras.

**Current Code:**
```python
CAMERA_URL = "http://192.168.1.102:8081/video"
```

**Fix:**
```python
import os

CAMERA_URL = os.environ.get("RUBIK_CAMERA_URL", "http://192.168.1.102:8081/video")
```

**Additional Files:**
Create `.env.example`:
```
# Rubik's Cube CV Configuration
RUBIK_CAMERA_URL=http://192.168.1.102:8081/video
```

**Estimated Effort:** 15 minutes

---

## MEDIUM PRIORITY - Code Quality

### 4. Code Duplication: Polygon Utilities

**Locations:**
- `pipeline.py:151-223`
- `experiments/test_lighting_normalization.py:146-184`

**Issue:** `order_polygon_corners()` and `perspective_grid_point()` are duplicated.

**Fix:** Update `experiments/test_lighting_normalization.py` to import from pipeline:
```python
from pipeline import order_polygon_corners, perspective_grid_point
```

Remove duplicated function definitions.

**Estimated Effort:** 10 minutes

---

### 5. No Logging Framework

**Location:** Throughout `server.py`, `pipeline.py`
**Issue:** Uses `print()` statements instead of proper logging.

**Fix:** Create `logging_config.py`:
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

Update modules to use logger:
```python
from logging_config import logger
logger.info("Capturing frame...")
```

**Estimated Effort:** 45 minutes

---

### 6. Magic Numbers in Detection

**Location:** `detection.py` throughout
**Issue:** Hardcoded constants scattered through code.

**Fix:** Add `DETECTION_SAMPLING` config dict to `config.py`:
```python
DETECTION_SAMPLING = {
    'region_size': 30,
    'grid_points': 5,
    'spread_normalization': 36.0,
    'histogram_min_coverage': 0.30,
    'low_confidence_threshold': 0.25,
    'min_samples_required': 3,
}
```

Update `detection.py` to import and use these values.

**Estimated Effort:** 30 minutes

---

### 7. Legacy detect.py Module

**Location:** `detect.py` (316 lines)
**Issue:** Superseded by `detection.py`, causes confusion.

**Fix:** Move to experiments folder:
```bash
mv detect.py experiments/legacy_detect.py
```

Add header comment:
```python
"""LEGACY: Original single-point color detection.

Superseded by detection.py which uses multi-point sampling.
Kept for reference.
"""
```

**Estimated Effort:** 10 minutes

---

## LOW PRIORITY - Maintainability

### 8. Incomplete Edge Validation

**Location:** `capture_session.py:224-235`
**Issue:** `EDGE_ADJACENCIES` defined but validation is a no-op.

**Fix:** Document as intentional deferral:
```python
# TODO(PRD-07): Implement edge consistency validation
# Requires domain knowledge about valid cube states.
pass
```

**Estimated Effort:** 5 minutes

---

### 9. Global State in server.py

**Location:** `server.py:36-47`
**Issue:** Module-level globals make testing difficult.

**Fix:** Document for future refactor:
```python
# ==============================================================================
# Global State (Future: Refactor to Dependency Injection)
# ==============================================================================
# Consider using FastAPI Depends() or AppState class.
# ==============================================================================
```

**Estimated Effort:** 10 minutes

---

### 10. Stream Generator Cleanup

**Location:** `server.py:608-633`
**Issue:** Infinite loop with no cleanup on client disconnect.

**Fix:**
```python
def generate_stream_frames():
    try:
        while True:
            # ... existing code
            yield (...)
    except GeneratorExit:
        with _stream_lock:
            _stream_frame = None
        logger.info("Stream client disconnected")
```

**Estimated Effort:** 15 minutes

---

### 11. NOP Functions in cube3d.js

**Location:** `static/cube3d.js:637-649`
**Issue:** Stub functions that do nothing.

**Fix:**
```javascript
export function showFaceLabels(faceName) {
    throw new Error('showFaceLabels not implemented in dual cube mode');
}

export function enableFaceClickMode(callback) {
    throw new Error('enableFaceClickMode not implemented in dual cube mode');
}

export function disableFaceClickMode() {
    // No-op: Face click mode not supported
}
```

**Estimated Effort:** 10 minutes

---

## Files to Modify

| File | Changes | Priority |
|------|---------|----------|
| `server.py` | Path validation, race condition, generator cleanup | HIGH |
| `config.py` | Environment variable, detection config | HIGH/MED |
| `detection.py` | Use config constants | MEDIUM |
| `capture_session.py` | Document edge validation | LOW |
| `static/cube3d.js` | Fix NOP functions | LOW |
| `experiments/test_lighting_normalization.py` | Import from pipeline | MEDIUM |

## New Files to Create

| File | Purpose |
|------|---------|
| `.env.example` | Document configurable environment variables |
| `logging_config.py` | Centralized logging configuration |
| `experiments/legacy_detect.py` | Relocated from `detect.py` |

## Acceptance Criteria

### Security
- [ ] `/output/../../etc/passwd` returns error, not file contents
- [ ] Path traversal attempts logged as warnings
- [ ] No race condition between frame copy and assignment

### Configuration
- [ ] `RUBIK_CAMERA_URL` environment variable overrides default
- [ ] `.env.example` documents all configurable values
- [ ] Detection magic numbers moved to `DETECTION_SAMPLING`

### Code Quality
- [ ] No duplicate `order_polygon_corners()` implementations
- [ ] All `print()` statements replaced with `logger.*()` calls
- [ ] `detect.py` moved to `experiments/legacy_detect.py`

### Maintainability
- [ ] Generator cleanup on client disconnect
- [ ] NOP functions throw or are documented
- [ ] Global state documented with refactor guidance

## Estimated Total Effort

| Priority | Items | Time |
|----------|-------|------|
| HIGH | 3 | ~40 minutes |
| MEDIUM | 4 | ~1 hour 35 minutes |
| LOW | 4 | ~40 minutes |
| **Total** | **11** | **~3 hours** |
