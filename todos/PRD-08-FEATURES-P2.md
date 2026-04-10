# PRD-08: New Features (Phase 2)

**Status:** Pending
**Dependencies:** PRD-07 (Solver Integration, 3D Mapping Fix)
**Estimated Effort:** 4-6 days total

## Overview

This PRD covers four new features to enhance the Rubik's Cube CV project:

1. **Solve Sequence Visualization** (L) - Animate solution moves on 3D cube
2. **Color Calibration Wizard** (M) - Per-color HSV range tuning
3. **Confidence-Based Re-Detection** (S) - Second-pass for low-confidence stickers
4. **Export Cube State** (S) - Multiple export formats

---

## 2.1 Solve Sequence Visualization

**Complexity:** Large (2-3 days)
**Dependencies:** PRD-07 Solver Integration, 3D Mapping Fix

### Current State
- Dual cube architecture in `cube3d.js`: estimationCube and groundTruthCube
- Stickers stored as `stickers[faceName][row][col]`
- No animation infrastructure

### Requirements

#### 2.1.1 Core Animation System
Add to `cube3d.js`:

```javascript
const MOVE_CONFIG = {
    'R': { axis: 'x', layer: 1, direction: -1 },
    'L': { axis: 'x', layer: -1, direction: 1 },
    'U': { axis: 'y', layer: 1, direction: -1 },
    'D': { axis: 'y', layer: -1, direction: 1 },
    'F': { axis: 'z', layer: 1, direction: -1 },
    'B': { axis: 'z', layer: -1, direction: 1 },
};

async function animateMove(move) {
    // Parse move: R, R', R2
    // Create temp group with affected cubies
    // Animate 90/180/270 degree rotation
    // Update sticker references after animation
}
```

#### 2.1.2 Playback Controller
```javascript
let playbackState = {
    moves: [],
    currentIndex: 0,
    isPlaying: false,
    isPaused: false,
    speed: 1.0,
    originalState: null,
};

function playSolution(moves) { ... }
function pausePlayback() { ... }
function resumePlayback() { ... }
function stepForward() { ... }
function stepBackward() { ... }
function resetToOriginal() { ... }
```

#### 2.1.3 UI Controls
Add to `index.html`:
```html
<div id="solution-controls" class="hidden">
    <button id="play-btn">Play</button>
    <button id="pause-btn">Pause</button>
    <button id="step-btn">Step</button>
    <button id="reset-solution-btn">Reset</button>
    <input type="range" id="speed-slider" min="0.5" max="3" step="0.5" value="1">
    <span id="speed-value">1x</span>
</div>
```

### Acceptance Criteria
- [ ] Single move animation plays smoothly
- [ ] Layer selection correct for all 6 faces
- [ ] Play/Pause/Step/Reset controls work
- [ ] Speed slider affects animation tempo
- [ ] Current move highlighted in list
- [ ] Double moves (R2) animate correctly

---

## 2.2 Color Calibration Wizard

**Complexity:** Medium (1-2 days)

### Current State
- HSV offset sliders affect all colors uniformly
- `COLOR_RANGES` in config.py are hardcoded

### Requirements

#### 2.2.1 Wizard UI
Add to `index.html`:
```html
<div id="color-wizard-overlay" class="hidden">
    <div class="wizard-panel">
        <h3>Color Calibration</h3>
        <span class="color-indicator" id="wizard-color"></span>
        <span id="wizard-instruction">Click stickers that are WHITE</span>
        <span id="sample-count">0 samples</span>
        <button id="wizard-next">Next Color</button>
        <button id="wizard-skip">Skip</button>
        <div>Step <span id="wizard-step">1</span> of 6</div>
        <button id="wizard-cancel">Cancel</button>
        <button id="wizard-finish" disabled>Finish & Save</button>
    </div>
</div>
```

Color sequence: White → Yellow → Orange → Red → Green → Blue

#### 2.2.2 Sampling Endpoints
Add to `server.py`:
```python
@app.post("/api/calibrate/sample")
async def sample_color_region(x: int, y: int, radius: int = 15):
    """Sample HSV from region around (x, y)."""
    # Return {h_mean, h_std, s_mean, s_std, v_mean, v_std, sample_count}

@app.post("/api/calibrate/preview")
async def preview_calibration(ranges: dict):
    """Run detection with proposed ranges."""
    # Return detection results for comparison

@app.post("/api/calibrate/color")
async def save_color_calibration(data: dict):
    """Save per-color ranges to color_calibration.json."""
```

#### 2.2.3 Range Calculation
```python
def compute_color_range(samples: list[dict]) -> dict:
    h_values = [s['h_mean'] for s in samples]
    s_values = [s['s_mean'] for s in samples]
    v_values = [s['v_mean'] for s in samples]

    return {
        'h': (min(h_values) - 5, max(h_values) + 5),
        's': (min(s_values) - 20, max(s_values) + 20),
        'v': (min(v_values) - 20, max(v_values) + 20),
    }
```

Handle red's hue wraparound (values near 0 and 180).

#### 2.2.4 Persistence
Save to `output/color_calibration.json`:
```json
{
  "version": "1.0",
  "created": "2026-01-21T12:00:00Z",
  "ranges": {
    "white": {"h": [0, 180], "s": [0, 80], "v": [180, 255]},
    ...
  }
}
```

Load custom ranges on startup in `config.py`.

### Acceptance Criteria
- [ ] Wizard guides through all 6 colors
- [ ] Clicking debug image samples HSV
- [ ] Suggested ranges computed with margins
- [ ] Preview shows detection with new ranges
- [ ] Calibration persists across restarts
- [ ] Reset to defaults option works
- [ ] Red hue wraparound handled

---

## 2.3 Confidence-Based Re-Detection

**Complexity:** Small (0.5-1 day)

### Current State
- `compute_confidence()` scores each sticker
- Histogram fallback at confidence < 0.25
- No second-pass retry mechanism

### Requirements

#### 2.3.1 Second Pass Detection
Modify `detection.py`:
```python
REDETECTION_CONFIG = {
    'enabled': True,
    'confidence_threshold': 0.4,
    'region_size': 40,      # Larger than default 30
    'inward_bias': 0.20,    # More aggressive
    'histogram_threshold': 0.20,
    'grid_points': 7,       # Larger grid (7x7 = 49 points)
}
```

After first pass, identify stickers with confidence < 0.4, retry with adjusted parameters.

#### 2.3.2 Track Re-Detection
Extend `StickerSample`:
```python
@dataclass
class StickerSample:
    # ... existing fields ...
    redetected: bool = False
    original_confidence: float | None = None
```

#### 2.3.3 Debug Output
Include in `/debug/state`:
```python
"redetected": sample.redetected,
"original_confidence": sample.original_confidence,
```

### Acceptance Criteria
- [ ] Stickers below 0.4 trigger second-pass
- [ ] Second pass uses larger region/more points
- [ ] Original confidence preserved
- [ ] Debug shows which stickers re-detected
- [ ] Can be disabled via config
- [ ] No significant performance regression

---

## 2.4 Export Cube State

**Complexity:** Small (0.5 day)

### Requirements

#### 2.4.1 ASCII Diagram
Add to `cube_model.py`:
```python
def to_ascii(self) -> str:
    """Generate ASCII diagram.

          [U]
          W W W
          W W W
          W W W
    [L]   [F]   [R]   [B]
    G G G R R R B B B O O O
    G G G R R R B B B O O O
    G G G R R R B B B O O O
          [D]
          Y Y Y
          Y Y Y
          Y Y Y
    """
```

#### 2.4.2 Export Endpoint
Add to `server.py`:
```python
@app.get("/api/export")
async def export_cube_state(
    format: str = Query("json", regex="^(json|kociemba|ascii)$")
):
    """Export cube state in specified format."""
    cube_state = capture_session.to_cube_state()

    if format == "kociemba":
        return PlainTextResponse(cube_state.to_kociemba())
    elif format == "ascii":
        return PlainTextResponse(cube_state.to_ascii())
    else:
        return cube_state.to_json_export()
```

#### 2.4.3 UI Integration
Add export dropdown:
```html
<div class="export-dropdown">
    <button id="export-btn">Export</button>
    <div class="dropdown-content">
        <a href="/api/export?format=json" download="cube-state.json">JSON</a>
        <a href="#" onclick="copyKociemba()">Kociemba (copy)</a>
        <a href="#" onclick="showAscii()">ASCII Diagram</a>
    </div>
</div>
```

### Acceptance Criteria
- [ ] Kociemba string is valid 54-char format
- [ ] ASCII diagram renders correctly
- [ ] JSON includes all metadata
- [ ] Copy to clipboard works
- [ ] Partial state shows '?' placeholders

---

## Files to Create

| File | Purpose |
|------|---------|
| `static/animation.js` | TWEEN-based animation utilities |
| `output/color_calibration.json` | User's calibrated ranges |

## Files to Modify

| File | Changes |
|------|---------|
| `static/cube3d.js` | `animateMove()`, `playSolution()`, playback controls |
| `static/app.js` | Solution controls, wizard, export UI |
| `static/index.html` | Controls, wizard overlay, export dropdown |
| `static/style.css` | New UI element styles |
| `server.py` | Calibration and export endpoints |
| `config.py` | `load_color_ranges()` |
| `detection.py` | Re-detection pass logic |
| `cube_model.py` | `to_ascii()` method |

## Implementation Notes

### Animation Library
Use TWEEN.js via CDN:
```html
<script src="https://unpkg.com/@tweenjs/tween.js@23/dist/tween.umd.js"></script>
```

### Face Rotation Permutation
```javascript
// Clockwise 90° rotation indices
// [0,1,2]    [6,3,0]
// [3,4,5] -> [7,4,1]
// [6,7,8]    [8,5,2]
const CLOCKWISE_PERMUTATION = [6, 3, 0, 7, 4, 1, 8, 5, 2];
```

## Estimated Effort

| Feature | Complexity | Estimate |
|---------|------------|----------|
| 2.1 Solve Visualization | Large | 2-3 days |
| 2.2 Color Wizard | Medium | 1-2 days |
| 2.3 Re-Detection | Small | 0.5-1 day |
| 2.4 Export State | Small | 0.5 day |
| **Total** | | **4-6 days** |
