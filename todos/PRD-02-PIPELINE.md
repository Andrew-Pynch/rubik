# PRD-02: CV Processing Pipeline

**Status:** 🔄 85% Complete (T1 + T2)

**Progress Notes (T1):**
- ✅ Core files created: config.py, preprocess.py, detect.py, process.py, cube_model.py, calibrate.py

**Progress Notes (T2):**
- ✅ Interactive calibration tool (click 8 vertices to define cube faces)
- ✅ Polygon-based ROI masks for U, L, R faces (replaces single rectangle)
- ✅ calibration.json saved with face polygons
- ✅ config.py loads calibration at runtime
- ✅ pipeline.py uses polygon masks for per-face detection
- 🔄 Detection accuracy not yet verified after calibration

**Remaining:**
1. Test detection with saved calibration
2. Tune HSV color ranges (warm lighting shifts red/blue)
3. Verify >80% sticker detection per face
**Dependencies:** PRD-01 complete
**Estimated effort:** Medium-Large

## Goal

Implement computer vision pipeline that detects cube faces and extracts colors from camera feed.

## Context

- Camera is fixed at 150mm from cube center
- Pitch: 53.5° downward, Roll: -21.5° right
- Cube is currently in SOLVED state
- Visible faces: U (white top), L (red left), R (blue right)

## Deliverables

### 1. `pipeline.py` - Main CV processing module

```python
def capture_frame() -> np.ndarray:
    """Capture single frame from IP camera."""

def preprocess(frame: np.ndarray) -> np.ndarray:
    """Rotate and filter frame for CV processing."""

def detect_cube_contours(frame: np.ndarray) -> list:
    """Find cube face contours using edge/contour detection."""

def extract_face_colors(frame: np.ndarray, contours: list) -> dict:
    """Extract 9 colors per visible face."""

def draw_debug_overlay(frame: np.ndarray, detections: dict) -> np.ndarray:
    """Draw detected contours and color labels on frame."""

def run_pipeline() -> None:
    """Main entry point - captures, processes, saves outputs."""
```

**Output files:**
- `output/raw.jpg` - Original frame (rotated)
- `output/debug.jpg` - Frame with CV overlays
- `output/state.json` - Detected cube state

### 2. `cube_model.py` - Cube state representation

```python
class CubeState:
    """Represents the state of a Rubik's cube."""

    faces: dict[str, list[list[str]]]  # U, D, L, R, F, B

    def to_kociemba(self) -> str:
        """Convert to 54-char Kociemba solver format."""

    def to_json(self) -> dict:
        """Export for state.json."""

    @classmethod
    def from_detected(cls, colors: dict) -> 'CubeState':
        """Create from CV-detected colors."""
```

### 3. Update `capture.py`

Integrate with config.py for URL and rotation settings.

## CV Pipeline Details

### Step 1: Preprocessing
1. Capture frame from MJPEG stream
2. Rotate 90° clockwise (fix camera orientation)
3. Apply bilateral filter (reduce noise, preserve edges)
4. Convert to HSV color space

### Step 2: Cube Detection
1. Edge detection (Canny) or color-based segmentation
2. Find contours with `cv2.findContours()`
3. Filter by:
   - Square-ish shape (aspect ratio ~1.0)
   - Similar sizes (all stickers same size)
   - Spatial clustering (9 squares in 3x3 pattern)
4. Group into faces based on position

### Step 3: Color Extraction
1. For each detected sticker:
   - Sample center region (avoid edges)
   - Calculate mean HSV values
   - Classify using COLOR_RANGES from config
2. Build face color arrays

### Step 4: Output
1. Save raw.jpg (input frame)
2. Draw debug overlay:
   - Contour outlines
   - Color labels
   - Face boundaries
3. Save debug.jpg
4. Export state.json with detected colors

## state.json Format

```json
{
  "timestamp": "2026-01-17T12:30:00",
  "visible_faces": ["U", "L", "R"],
  "faces": {
    "U": [["W","W","W"], ["W","W","W"], ["W","W","W"]],
    "L": [["R","R","R"], ["R","R","R"], ["R","R","R"]],
    "R": [["B","B","B"], ["B","B","B"], ["B","B","B"]],
    "D": null,
    "F": null,
    "B": null
  },
  "confidence": 0.95
}
```

## Acceptance Criteria

- [ ] `python pipeline.py` captures frame and saves to output/
- [ ] raw.jpg shows correctly rotated camera frame
- [ ] debug.jpg shows detected contours with color labels
- [ ] state.json contains detected colors for 3 visible faces
- [ ] Colors correctly identified for solved cube (white top, red left, blue right)

## References

- qbr (GitHub): kkoomen/qbr - webcam cube detection
- OpenCV contour detection tutorial
- HSV color space for robust color detection
