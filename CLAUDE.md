# Rubik's Cube CV Project

Computer vision pipeline for detecting Rubik's cube state from camera feed, with web-based debugger and 3D visualization.

## Quick Start

```bash
./run.sh                    # Start server at localhost:8000 (auto-reload enabled)
```

Open http://localhost:8000 to see:
- Live MJPEG stream with detection overlay
- HSV offset sliders for color tuning
- Interactive 3D cube visualization

## Project Structure

```
rubik/
├── config.py              # Camera calibration, HSV color ranges, detection thresholds
├── pipeline.py            # Main CV processing (capture → detect → output)
├── detection.py           # Robust multi-point detection with confidence scoring
├── preprocess.py          # Image preprocessing (rotation, CLAHE, filtering)
├── cube_model.py          # CubeState class for cube representation
├── capture_session.py     # Multi-capture workflow session management
├── auto_match.py          # Automatic face orientation matching for 3D view
├── server.py              # FastAPI server with WebSocket + MJPEG streaming
├── capture.py             # Standalone frame capture utility
├── run.sh                 # Server startup script
│
├── static/                # Web UI assets
│   ├── index.html         # Main page layout
│   ├── app.js             # WebSocket client, stream toggle, controls
│   ├── cube3d.js          # Three.js 3D cube visualization
│   └── style.css          # Dark theme styling
│
├── output/                # Generated outputs (gitignored)
│   ├── raw.jpg            # Captured frame (rotated)
│   ├── debug.jpg          # Frame with CV overlays and grid lines
│   ├── calibration.json   # Face polygon vertices from calibration
│   └── state.json         # Detected cube state
│
├── experiments/           # Debugging and testing scripts
│   ├── grid_detection.py
│   ├── debug_detection.py
│   ├── sample_hsv.py
│   └── test_lighting_normalization.py  # CLAHE parameter testing
│
├── defaults/              # Default configuration files
│   └── calibration.json   # Default face polygon vertices
│
└── todos/                 # Project phase documents and handoffs
    ├── PRD-01-CONFIG.md   # ✅ Complete - Foundation
    ├── PRD-02-PIPELINE.md # ✅ Complete - CV Pipeline
    ├── PRD-03-WEBDEBUGGER.md # ✅ Complete - Web UI
    ├── PRD-04-CUBE3D.md   # ✅ Complete - 3D Visualization
    ├── PRD-05-INTEGRATION.md # 🔄 ~70% Complete - Multi-capture
    └── T*-HANDOFF.md      # Session handoff documents
```

## How to Run

```bash
# Start web server with auto-reload
./run.sh

# Or manually:
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# Run pipeline once (saves to output/)
.venv/bin/python pipeline.py

# Capture single frame only
.venv/bin/python capture.py
```

## Web UI Features

- **Live Stream**: Toggle MJPEG stream at `/stream` endpoint
- **HSV Sliders**: Adjust Hue/Saturation/Value offsets for color detection
- **3D Cube**: Interactive Three.js visualization with OrbitControls
- **Auto-refresh**: WebSocket pushes updates when output files change

## Camera Setup

- **Device**: iPhone with IP Camera Lite app
- **URL**: `http://192.168.1.102:8081/video` (MJPEG stream)
- **Mount**: 3D printed holder, 150mm from cube center
- **Orientation**: 53.5° pitch (downward), -21.5° roll (rightward)
- **Rotation**: Image rotated 90° clockwise to correct orientation

## Cube Face Mapping

Camera sees 3 faces meeting at a corner vertex:

```
        [U - White]
           /\
          /  \
    [F-Red]  [R-Blue]
         \  /
          \/
```

| Face | Color | Position in Camera View |
|------|-------|------------------------|
| U | White | Top |
| F | Red | Bottom-left |
| R | Blue | Bottom-right |
| D, L, B | — | Not visible (need cube rotation) |

**Note**: Face labels use standard Rubik's notation where F/R are adjacent faces (share an edge), not opposite.

## Key Libraries

- `opencv-python` - Image capture and CV processing
- `numpy` - Array operations
- `fastapi` + `uvicorn` - Web server with WebSocket support
- `watchdog` - File watching for live updates
- `kociemba` - Rubik's cube solver algorithm (for future integration)

## Coding Conventions

- Python 3.11+
- Type hints for function signatures
- Docstrings for public functions
- HSV color space for color detection
- Experiments in `experiments/` folder, promote useful code to root

## Detection System

The detection pipeline uses robust multi-point sampling with several fallback mechanisms:

### Multi-Point Sampling (`detection.py`)
- **25-point grid** (5x5) per sticker with Gaussian center weighting
- **MAD outlier rejection** on hue values to handle noise
- **Confidence scoring** based on sample consistency, color distance, and classification margin

### Logo Handling
White center stickers with logos (e.g., GAN cube's blue logo) are handled via:
- **White pixel percentage detection**: If 35%+ of samples have low saturation (s<80) and high value (v>180), classify as white
- Uses lower threshold (35%) for center stickers where logos appear, 50% for others

### Histogram Fallback
When point sampling has low confidence (<0.25), falls back to histogram analysis:
- Counts pixels matching each color range in the sticker region
- Requires 30%+ pixel coverage for a dominant color

### Configuration (`config.py`)
```python
WHITE_DETECTION_THRESHOLD = 0.50        # For non-center stickers
WHITE_DETECTION_CENTER_THRESHOLD = 0.35 # For center stickers (logos)
WHITE_SAT_MAX = 80   # Max saturation for "white-like"
WHITE_VAL_MIN = 180  # Min value for "white-like"
```

## Debug API

### `GET /debug/state`
Comprehensive debug endpoint for troubleshooting detection issues:

```bash
curl http://localhost:8000/debug/state | jq .
```

Returns:
- **camera**: Connection status, frame dimensions, lighting analysis
- **detection.stickers**: Per-sticker data with:
  - `position`: [row, col]
  - `color`: Letter (W/Y/O/R/G/B/?)
  - `hsv`: {h, s, v} values
  - `confidence`: 0.0-1.0 score
  - `spread`: Sample consistency (lower = better)
  - `alternatives`: Runner-up colors
  - `reason`: Why "?" (`insufficient_samples`, `high_spread`, `boundary_case`, `no_color_match`)
- **detection.summary**: Totals for confident/uncertain/unknown stickers
- **session**: Capture session state (captured/missing faces)
- **hints**: Actionable debugging suggestions

### Other Debug Endpoints
- `GET /debug/hsv` - HSV samples at face polygon centers
- `GET /debug/lighting` - Per-face lighting analysis with CLAHE status
- `GET /camera/status` - Camera connection health

## Complete API Reference

### Capture & Session Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/capture` | POST | Trigger capture, merge into session |
| `/reset` | POST | Reset capture session |
| `/session` | GET | Get current session state (captured/missing faces) |
| `/sequence` | GET | Get capture sequence configuration |

### Streaming & Settings
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/stream` | GET | MJPEG live stream with detection overlay |
| `/settings/hsv` | GET/POST | Read/update HSV offset values |

### Debug Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/debug/state` | GET | Comprehensive per-sticker debug info |
| `/debug/hsv` | GET | HSV samples at face polygon centers |
| `/debug/lighting` | GET | Per-face lighting analysis |
| `/camera/status` | GET | Camera connection health |

### Calibration & Ground Truth
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/calibrate` | POST | Save face calibration data |
| `/save-calibration-defaults` | POST | Copy calibration to defaults |
| `/ground-truth` | GET/POST | Read/save ground truth for testing |

### File Serving
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/output/{filename}` | GET | Serve files from output directory |
| `/static/{path}` | GET | Serve static web assets |

## Multi-Capture Workflow

The system uses a 2-step capture sequence to capture all 6 faces:

### Step 1: Initial Capture
- **Position**: White face up, Red toward camera
- **Captures**: U (White/top), F (Red/front-left), R (Blue/front-right)
- **Corner visible**: UFR corner vertex

### Step 2: After x2 Rotation
- **Position**: Flip cube toward yourself (Yellow now on top)
- **Captures**: D (Yellow), B (Orange), L (Green)
- **Corner visible**: DBL corner vertex (with 180° grid transform)

### Session State
The capture session tracks:
- `captured_faces`: List of faces successfully detected
- `missing_faces`: Faces still needed
- `global_state`: Accumulated sticker colors
- `is_complete`: True when all 6 faces captured
- `rotation_hint`: Suggestion for next orientation

### Endpoints
- `POST /capture` - Triggers detection and merges into session
- `POST /reset` - Clears session state
- `GET /session` - Returns current session state

## Troubleshooting

### Camera Connection Issues
1. Check camera URL in `config.py` (CAMERA_URL)
2. Verify iPhone IP Camera app is running
3. Test connectivity: `curl http://192.168.1.102:8081/video --head`
4. Check `/camera/status` endpoint for diagnostics

### Detection Issues
1. Use `/debug/state` to see per-sticker confidence scores
2. Check lighting with `/debug/lighting`
3. Adjust HSV sliders in UI or via `/settings/hsv`
4. Look for stickers with confidence < 0.25 (triggers histogram fallback)

### 3D Mapping Issues
1. Verify `auto_match` data in `state.json`
2. Check browser console for Three.js errors
3. Grid indexing: `cube3d.js` must match `pipeline.py` ordering

### Common Problems
| Symptom | Cause | Fix |
|---------|-------|-----|
| "?" stickers | Low confidence detection | Adjust lighting, HSV offsets |
| Wrong colors | HSV thresholds misaligned | Use `/debug/hsv` to tune |
| 3D mismatch | Grid ordering inconsistent | Check `updateFaceColors()` |
| White as yellow | Saturation threshold too high | Lower WHITE_SAT_MAX |
| Logo detection fails | Center threshold too strict | Adjust WHITE_DETECTION_CENTER_THRESHOLD |

## Known Issues (Current Sprint)

1. **3D mapping mismatch**: Grid indexing in cube3d.js doesn't match pipeline.py sticker ordering
