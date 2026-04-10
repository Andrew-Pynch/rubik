# PRD-09: Optimizations (Phase 3)

**Status:** Pending
**Dependencies:** PRD-05 (Integration) should be complete
**Estimated Effort:** 4-5.5 days total

## Overview

This PRD covers optimization features for improving detection accuracy, performance, and user experience:

1. **CLAHE Parameter Tuning** (S) - Document optimal lighting settings, add UI toggle
2. **Adaptive Detection Thresholds** (M) - Adjust thresholds based on lighting
3. **Calibration Caching** (S) - Reduce file I/O
4. **Auto-Rotation Detection** (L) - Accept any cube orientation

---

## 3.1 CLAHE Parameter Tuning

**Complexity:** Small (0.5 day)

### Current State
- `preprocess.py` has `apply_adaptive_clahe()` implementation
- `LIGHTING_NORMALIZATION` config in `config.py`:
  - `clahe_enabled`: True
  - `clahe_clip_limit`: 2.0
  - `clahe_tile_grid`: (4, 4)
- Test harness exists: `experiments/test_lighting_normalization.py`

### Requirements

#### 3.1.1 Document Optimal Parameters
Run test matrix under various lighting conditions and document results in code comments.

#### 3.1.2 Add UI Toggle
Add checkbox in HSV settings panel:
```html
<label>
    <input type="checkbox" id="clahe-enabled" checked>
    Enable CLAHE (lighting normalization)
</label>
```

#### 3.1.3 Create CLAHE Endpoint
Add to `server.py`:
```python
@app.get("/settings/clahe")
async def get_clahe_settings():
    return {
        'enabled': LIGHTING_NORMALIZATION['clahe_enabled'],
        'clip_limit': LIGHTING_NORMALIZATION['clahe_clip_limit'],
        'tile_grid': LIGHTING_NORMALIZATION['clahe_tile_grid'],
    }

@app.post("/settings/clahe")
async def update_clahe_settings(data: dict):
    LIGHTING_NORMALIZATION['clahe_enabled'] = bool(data.get('enabled', True))
    return {"status": "ok"}
```

#### 3.1.4 Enhance Debug Lighting Endpoint
Add before/after comparison:
```python
{
    "faces_before": {
        "U": {"median_v": 85.2, "std_v": 12.3},
        ...
    },
    "faces_after": {
        "U": {"median_v": 120.5, ...},
        ...
    },
    "clahe_applied_to": ["U", "R"]
}
```

### Acceptance Criteria
- [ ] CLAHE parameters documented in code
- [ ] UI toggle to enable/disable CLAHE
- [ ] `/settings/clahe` GET/POST endpoints work
- [ ] `/debug/lighting` shows before/after stats
- [ ] Detection accuracy maintains in low-light

---

## 3.2 Adaptive Detection Thresholds

**Complexity:** Medium (1-1.5 days)

### Current State
`DETECTION_CONFIG` in `config.py` defines thresholds but they're **not used**:
```python
DETECTION_CONFIG = {
    'base_confidence_threshold': 0.15,
    'low_light_v_threshold': 120,
    'low_light_threshold_boost': -0.05,
}
```

`FaceLightingProfile` classifies brightness but only used for CLAHE decision.

### Requirements

#### 3.2.1 Create Adaptive Thresholds Function
Add to `detection.py` or `config.py`:
```python
def get_adaptive_thresholds(lighting_profile: FaceLightingProfile | None) -> dict:
    base = DETECTION_CONFIG['base_confidence_threshold']

    if lighting_profile is None:
        return {
            'confidence_threshold': base,
            'white_sat_max': WHITE_SAT_MAX,
            'white_val_min': WHITE_VAL_MIN,
        }

    if lighting_profile.brightness_level == 'low':
        return {
            'confidence_threshold': base + DETECTION_CONFIG['low_light_threshold_boost'],
            'white_sat_max': WHITE_SAT_MAX + 20,
            'white_val_min': WHITE_VAL_MIN - 30,
        }
    elif lighting_profile.brightness_level == 'high':
        return {
            'confidence_threshold': base + 0.05,
            'white_sat_max': WHITE_SAT_MAX,
            'white_val_min': WHITE_VAL_MIN,
        }
    else:
        return {
            'confidence_threshold': base,
            'white_sat_max': WHITE_SAT_MAX,
            'white_val_min': WHITE_VAL_MIN,
        }
```

#### 3.2.2 Update classify_sticker()
Modify signature to accept thresholds:
```python
def classify_sticker(
    sample: StickerSample,
    hsv_offsets: dict | None = None,
    is_center: bool = False,
    thresholds: dict | None = None,
) -> StickerSample:
    conf_threshold = thresholds.get('confidence_threshold', 0.15) if thresholds else 0.15
    # ... use thresholds
```

#### 3.2.3 Pass Thresholds Through Pipeline
Update `detect_face_grid_robust()` and `detect_from_frames()` to compute and pass lighting-based thresholds.

#### 3.2.4 Show Applied Thresholds
Add to `/debug/state` response:
```python
"thresholds_applied": {
    "U": {"confidence_threshold": 0.10, "white_sat_max": 100},
    "F": {"confidence_threshold": 0.15},
    "R": {"confidence_threshold": 0.10}
}
```

### Acceptance Criteria
- [ ] `get_adaptive_thresholds()` implemented
- [ ] `classify_sticker()` uses thresholds parameter
- [ ] Pipeline passes lighting-based thresholds
- [ ] Low-light triggers more lenient thresholds
- [ ] `/debug/state` shows applied thresholds
- [ ] Detection accuracy improves in challenging lighting

---

## 3.3 Calibration Caching

**Complexity:** Small (0.5 day)

### Current State
`load_face_polygons()` reads calibration.json on every call. Called multiple times per request during streaming.

### Requirements

#### 3.3.1 Add Module-Level Cache
Update `config.py`:
```python
_calibration_cache: dict | None = None
_calibration_mtime: float = 0.0

def load_face_polygons() -> dict | None:
    global _calibration_cache, _calibration_mtime

    # Determine path
    if CALIBRATION_PATH.exists():
        path = CALIBRATION_PATH
    elif DEFAULT_CALIBRATION_PATH.exists():
        path = DEFAULT_CALIBRATION_PATH
    else:
        _calibration_cache = None
        return None

    # Check cache validity
    current_mtime = path.stat().st_mtime
    if _calibration_cache is not None and current_mtime == _calibration_mtime:
        return _calibration_cache

    # Re-read file
    with open(path) as f:
        data = json.load(f)

    face_polygons = data.get('face_polygons')
    if not face_polygons:
        _calibration_cache = None
        return None

    _calibration_cache = {
        face: [tuple(pt) for pt in points]
        for face, points in face_polygons.items()
    }
    _calibration_mtime = current_mtime

    return _calibration_cache
```

#### 3.3.2 Add Cache Invalidation
```python
def invalidate_calibration_cache():
    global _calibration_cache, _calibration_mtime
    _calibration_cache = None
    _calibration_mtime = 0.0
```

#### 3.3.3 Call Invalidation on Save
Update `/calibrate` endpoint in `server.py`:
```python
@app.post("/calibrate")
async def save_calibration(data: CalibrationData):
    # ... save logic ...

    from config import invalidate_calibration_cache
    invalidate_calibration_cache()

    return {"status": "ok"}
```

### Acceptance Criteria
- [ ] Cache checks file mtime before returning
- [ ] `invalidate_calibration_cache()` exists
- [ ] `/calibrate` calls invalidation after saving
- [ ] No file reads when calibration unchanged
- [ ] Streaming performance unaffected or improved

---

## 3.4 Auto-Rotation Detection

**Complexity:** Large (2-3 days)

### Current State
`capture_session.py` enforces specific 2-step sequence:
```python
CAPTURE_SEQUENCE = [
    CaptureStep(name='initial', ...),      # UFR corner
    CaptureStep(name='after_x2', ...),     # DBL corner
]
```

`auto_match.py` already has `compute_auto_match()` that can identify any 3-face combination by center colors.

### Requirements

#### 3.4.1 Remove Sequence Enforcement
Make CaptureSession rotation-agnostic:
- Remove `current_step` tracking
- Remove `validate_step_centers()`
- Keep `identify_faces()` which uses center colors

#### 3.4.2 Integrate auto_match
```python
def process_capture(self, detected: dict) -> dict:
    from auto_match import compute_auto_match

    match_result = compute_auto_match(detected)

    if not match_result['valid']:
        return {'success': False, 'error': match_result['error']}

    identified_faces = {}
    for roi, grid in detected.items():
        actual_face = match_result['roi_to_face'].get(roi)
        if actual_face:
            rotation = match_result['face_rotations'].get(actual_face, 0)
            rotated_grid = self.transform_grid(grid, rotation)
            identified_faces[actual_face] = rotated_grid

    # ... merge logic
```

#### 3.4.3 Smart Rotation Hints
```python
VALID_CORNERS = {
    frozenset(['U', 'F', 'R']): "White up, Red front",
    frozenset(['U', 'F', 'L']): "White up, Red front, Green right",
    frozenset(['U', 'B', 'R']): "White up, Orange front",
    frozenset(['U', 'B', 'L']): "White up, Orange front, Green right",
    frozenset(['D', 'F', 'R']): "Yellow up, Red front",
    frozenset(['D', 'F', 'L']): "Yellow up, Red front, Green right",
    frozenset(['D', 'B', 'R']): "Yellow up, Orange front",
    frozenset(['D', 'B', 'L']): "Yellow up, Orange front, Green right",
}

def get_rotation_hint(self) -> str:
    missing = set(self.get_missing_faces())
    if not missing:
        return "All faces captured!"

    # Find corner showing most missing faces
    best_corner = None
    best_count = 0
    for corner_faces, instruction in VALID_CORNERS.items():
        new_faces = corner_faces & missing
        if len(new_faces) > best_count:
            best_count = len(new_faces)
            best_corner = corner_faces
            best_instruction = instruction

    return f"Rotate to show {', '.join(sorted(best_corner & missing))}: {best_instruction}"
```

#### 3.4.4 Corner Validation
```python
ADJACENT_PAIRS = {
    ('U', 'F'), ('U', 'R'), ('U', 'B'), ('U', 'L'),
    ('D', 'F'), ('D', 'R'), ('D', 'B'), ('D', 'L'),
    ('F', 'R'), ('F', 'L'), ('B', 'R'), ('B', 'L'),
}

def is_valid_corner(faces: set[str]) -> bool:
    if len(faces) != 3:
        return False
    face_list = list(faces)
    for i in range(3):
        for j in range(i+1, 3):
            pair = tuple(sorted([face_list[i], face_list[j]]))
            if pair not in ADJACENT_PAIRS:
                return False
    return True
```

#### 3.4.5 Update UI
Remove step indicators, show captured faces:
- Replace `.step-indicator` with "Captured: U F R" display
- Or hide step indicators in "auto" mode

### Acceptance Criteria
- [ ] Accepts any valid 3-face corner combination
- [ ] `compute_auto_match()` integrated into capture
- [ ] Grid transforms applied based on detected corner
- [ ] Rotation hints suggest optimal next position
- [ ] All 8 corners work (UFR, UFL, UBR, UBL, DFR, DFL, DBR, DBL)
- [ ] Invalid face combinations rejected
- [ ] UI shows captured faces without step sequence

---

## Files to Modify

| File | Changes |
|------|---------|
| `config.py` | Caching, thresholds config, CLAHE settings |
| `detection.py` | Adaptive thresholds, classify_sticker |
| `preprocess.py` | No changes needed |
| `pipeline.py` | Pass adaptive thresholds |
| `server.py` | CLAHE endpoint, cache invalidation |
| `capture_session.py` | Remove sequence, integrate auto-rotation |
| `auto_match.py` | Corner validation, VALID_CORNERS |
| `static/index.html` | CLAHE toggle, update step indicators |
| `static/app.js` | Wire CLAHE toggle, update progress display |

## Estimated Effort

| Feature | Complexity | Effort |
|---------|------------|--------|
| 3.1 CLAHE Tuning | S | 0.5 day |
| 3.2 Adaptive Thresholds | M | 1-1.5 days |
| 3.3 Calibration Caching | S | 0.5 day |
| 3.4 Auto-Rotation | L | 2-3 days |
| **Total** | | **4-5.5 days** |

## Testing Notes

### 3.1 CLAHE
- Run `experiments/test_lighting_normalization.py`
- Test in low/normal/high light conditions

### 3.2 Adaptive Thresholds
- Test with face lighting at various V values
- Verify white detection in dim conditions

### 3.3 Caching
- Enable debug logging to verify cache hits
- Profile file read reduction

### 3.4 Auto-Rotation
- Test all 8 corner positions manually
- Verify 6/6 completion from any start
