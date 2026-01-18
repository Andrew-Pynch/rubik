# Rubik's Cube CV Project - Agent Handoff

## Project Overview

Computer vision pipeline that detects Rubik's cube state from an iPhone camera feed, with web-based debugger and 3D visualization.

**Location:** `~/personal/rubik`

## How to Run

```bash
./run.sh                    # Starts server with auto-reload at http://localhost:8000
.venv/bin/python pipeline.py  # Run single detection
```

## Architecture

```
Camera (iPhone MJPEG) → pipeline.py (CV detection) → state.json → Web UI + 3D cube
                                ↓
                          debug.jpg (overlay)
```

**Key Files:**
| File | Purpose |
|------|---------|
| `server.py` | FastAPI server, `/stream` MJPEG endpoint, HSV settings |
| `pipeline.py` | CV detection, grid sampling, color classification |
| `cube_model.py` | CubeState class |
| `config.py` | Camera calibration, HSV color ranges |
| `static/cube3d.js` | Three.js 3D visualization |
| `static/app.js` | UI logic, stream toggle, HSV sliders |
| `output/calibration.json` | Face polygon coordinates |

## Current Capabilities

✅ **Working:**
- Grid-based sticker detection (perspective transform, 3x3 sampling per face)
- MJPEG live streaming with detection overlay (`/stream`)
- HSV offset sliders for lighting adjustment
- Grid lines showing sticker edges on debug overlay
- 3D cube visualization (Three.js)
- WebSocket auto-refresh
- Calibration UI for face polygons

## Known Issues (Priority Order)

### 1. Debug vs 3D View Position Mismatch
**Problem:** A sticker missing in the debug image shows up in a different wrong position on the 3D cube.

**Example:** Debug shows top-middle white missing, but 3D shows edge between right/red missing instead.

**Root Cause:** Grid position mapping in `cube3d.js` doesn't match `pipeline.py` sticker ordering.

**Fix Needed:** Align `updateFaceColors()` in `cube3d.js` with the grid indexing in `pipeline.py:detect_colors()`.

### 2. Inconsistent Detection Under Same Lighting
**Problem:** Same physical cube setup produces different detection results between captures.

**Causes:**
- Single-point HSV sampling is noise-sensitive
- iPhone auto-exposure causes subtle brightness shifts
- Orange/red HSV overlap, green detection edge cases

**Fix Needed:** Multi-point sampling within each sticker cell with outlier rejection (sample 5-9 points per cell, take majority).

### 3. Multi-Capture Workflow (T5 - Not Started)
**Goal:** Guide user through capturing all 6 faces across multiple orientations.

**Requirements:**
- Identify faces by center sticker color (white=U, red=F, blue=R, etc.)
- Accumulate state across captures
- Show which faces still need capturing
- Suggest rotation instructions

See `todos/T5-HANDOFF.md` for full spec.

## Camera Setup

- iPhone in 3D printed mount at 150mm from cube
- URL: `http://192.168.1.237:8081/video`
- Pitch: 53.5° down, Roll: -21.5° right
- Sees 3 adjacent faces: U (white/top), F (red/front-left), R (blue/front-right)

## Color Detection (HSV Ranges in config.py)

```
White:  S < 50, V > 150
Yellow: H 20-35, S > 100
Orange: H 5-20, S > 150
Red:    H 0-5 or 170-180, S > 150
Green:  H 50-85, S > 80
Blue:   H 100-130, S > 80
```

**HSV Offsets:** Global adjustments via `/settings/hsv` endpoint and UI sliders.

## Recent Changes (T6)

- Added `/stream` MJPEG endpoint for live preview
- Added `grid_edge_point()` for accurate grid line rendering (separate from cell-center sampling)
- Added HSV offset sliders in UI
- Made header sticky
- Created `run.sh` startup script

## Next Steps

1. **Fix 3D mapping** - Compare sticker indices between `pipeline.py` and `cube3d.js`
2. **Multi-point sampling** - Sample 5+ points per sticker, use majority vote
3. **Multi-capture workflow** - Per T5 spec
