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
├── config.py              # Camera calibration, HSV color ranges, paths
├── pipeline.py            # Main CV processing (capture → detect → output)
├── detect.py              # Color detection and classification
├── preprocess.py          # Image preprocessing (rotation, filtering)
├── cube_model.py          # CubeState class for cube representation
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
│   └── sample_hsv.py
│
└── todos/                 # Project phase documents and handoffs
    ├── PRD-01-CONFIG.md   # ✅ Complete - Foundation
    ├── PRD-02-PIPELINE.md # ✅ Complete - CV Pipeline
    ├── PRD-03-WEBDEBUGGER.md # ✅ Complete - Web UI
    ├── PRD-04-CUBE3D.md   # ✅ Complete - 3D Visualization
    ├── PRD-05-INTEGRATION.md # 🔄 In Progress - Multi-capture
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
- **URL**: `http://192.168.1.237:8081/video` (MJPEG stream)
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

## Known Issues (Current Sprint)

1. **3D mapping mismatch**: Grid indexing in cube3d.js doesn't match pipeline.py sticker ordering
2. **Inconsistent detection**: Need multi-point sampling per sticker cell instead of single-point
