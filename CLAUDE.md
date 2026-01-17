# Rubik's Cube CV Project

Computer vision pipeline for detecting Rubik's cube state from camera feed, with web-based debugger and 3D visualization.

## Project Structure

```
rubik/
├── config.py           # Camera calibration, color ranges, paths
├── capture.py          # Capture single frame from IP camera
├── pipeline.py         # CV processing pipeline
├── cube_model.py       # CubeState class for cube representation
├── output/             # Generated outputs (gitignored)
│   ├── raw.jpg         # Original captured frame
│   ├── debug.jpg       # Frame with CV overlays
│   └── state.json      # Detected cube state
├── static/             # Web UI assets (future)
└── todos/              # Project phase documents
```

## How to Run

```bash
# Capture single frame from camera
python capture.py

# Run full CV pipeline (capture + detect + output)
python pipeline.py

# Future: Start web debugger
python server.py
```

## Conventions

- Python 3.11+
- Type hints for function signatures
- Docstrings for public functions
- OpenCV for image processing
- HSV color space for color detection

## Camera Setup

- iPhone in 3D printed mount
- URL: http://192.168.1.237:8081/video (MJPEG stream)
- Distance: 150mm from cube center
- Pitch: 53.5° downward
- Roll: -21.5° rightward
- Image requires 90° clockwise rotation

## Cube Orientation

When viewing through camera (after rotation):
- **U (Up)**: White face (top)
- **L (Left)**: Red face
- **R (Right)**: Blue face
- **D, F, B**: Not visible from this angle

## Key Libraries

- `opencv-python`: Image capture and CV processing
- `numpy`: Array operations
- `kociemba`: Rubik's cube solver algorithm
- `fastapi` + `uvicorn`: Web server (future)
- `watchdog`: File watching for live updates (future)
- ultrathink
● The raw.jpg is already rotated (1920 height x 1080 width). My debug script was
  double-rotating! The calibration should work - let me fix the sampling:

● Bash(.venv/bin/python << 'EOF'
      import cv2…)
  ⎿  raw.jpg shape: (1920, 1080, 3) (H x W)

     Sampling HSV at face polygon centers (from calibration):
     … +5 lines (ctrl+o to expand)


instead of doing EOF scripts in cli like this, can you just have a /experiments folder with simple little python scripts that you can just run? I dont want to have to keep waiting to approve everytime you need to ask to write to cli like this instead of writing code and running it in auto accept edits.

when code is useful enough bring it into the main root of the repo and integrate in appropriate place